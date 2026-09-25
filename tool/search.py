"""search — ask the search daemon. The hook calls `ask`; the wiki chat runs this.

    python tool/search.py "<query>" --project <repo> [--k 8]

One daemon per machine (`searchd.py`). This side stays light: the hook
imports it on every turn, so nothing here loads a model or starts a server.

Everything that goes wrong is "no answer" — no state file, a refused or slow
connection, a server that cannot prove it holds the token, a different
version, broken JSON. The hook carries on with its regex alone —
`craft/hooks-fail-open`.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Next to the chat's 8787 and the mirror's 9090.
PORT = 8790


def cache_dir() -> Path:
    """Where the state file, the model and the vectors live. `WIKI_USER_HOME`
    stands in for the home in tests, as it does for `apply`."""

    return Path(os.environ.get("WIKI_USER_HOME") or Path.home()) / ".cache/ai-coding-agent-wiki"


def state_path() -> Path:
    return cache_dir() / "searchd.json"


def version() -> str:
    """The daemon's version is its file's hash. After a `git pull` the hook's
    copy differs from what the running daemon reports, and it is replaced."""

    return hashlib.sha256((HERE / "searchd.py").read_bytes()).hexdigest()[:12]


def proof(token: str, nonce: str) -> str:
    """What the daemon answers to a nonce. Only the process that wrote the
    state file knows the token, so a stranger holding the port cannot answer —
    and it is asked before the query, which carries the utterance, is sent."""

    return hashlib.sha256(f"{token}:{nonce}".encode()).hexdigest()[:16]


def spawn() -> None:
    """Start the daemon detached, and do not wait for it.

    Two hooks starting it at once is fine: binding the port is the lock, and
    the second one fails to bind and exits quietly.
    """

    flags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, and out of the hook's
        # job so the host collecting the hook does not collect the daemon.
        flags = 0x00000008 | 0x00000200 | 0x01000000
    options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, close_fds=True)
    command = [sys.executable, str(HERE / "searchd.py")]
    try:
        if sys.platform == "win32":
            try:
                subprocess.Popen(command, creationflags=flags, **options)
            except OSError:
                # A job that forbids breaking away. The daemon may then die
                # with the hook; the next turn starts it again.
                subprocess.Popen(command, creationflags=flags & ~0x01000000, **options)
        else:
            subprocess.Popen(command, start_new_session=True, **options)
    except OSError as error:
        print(f"searchd not started: {type(error).__name__}", file=sys.stderr)


def ask(query: str, project: str | Path | None, pool: str, timeout: float,
        k: int = 8, wait: float = 0.0, start: bool = True) -> list[dict] | None:
    """The daemon's answer, or `None`.

    `None` for anything short of a proper answer. When no daemon is there it
    is started and this turn goes without. No state file means no connection
    attempt at all: a refused connection to localhost takes two seconds on
    Windows, and the hook has 150 ms. A stale state file costs one timed-out
    connect, once.

    `wait` asks the daemon to hold the answer until the pool's vectors are
    complete, up to that many seconds. Only the chat uses it.
    """

    if os.environ.get("WIKI_SEARCH") == "off":
        return None
    try:
        state = json.loads(state_path().read_text(encoding="utf-8"))
        port, token = int(state["port"]), str(state["token"])
    except Exception:  # noqa: BLE001
        if start:
            spawn()
        return None

    deadline = time.monotonic() + timeout
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        try:
            conn.connect()
        except OSError:
            # Nothing listening: the daemon died and left its file behind.
            if start:
                spawn()
            return None
        nonce = secrets.token_hex(8)
        conn.request("GET", "/health", headers={"X-Wiki-Nonce": nonce})
        health = json.loads(conn.getresponse().read())
        if health.get("proof") != proof(token, nonce):
            # Somebody else holds the port. Starting another daemon would not
            # get it back, and the utterance is not sent to a stranger.
            return None
        if health.get("version") != version():
            conn.request("POST", "/quit", body=b"{}", headers={"X-Wiki-Token": token})
            conn.getresponse().read()
            if start:
                spawn()
            return None
        body = json.dumps({"query": query, "project": str(project) if project else None,
                           "pool": pool, "k": k, "wait": wait}, ensure_ascii=False)
        conn.sock.settimeout(max(0.001, deadline - time.monotonic()) + wait)
        conn.request("POST", "/search", body=body.encode("utf-8"),
                     headers={"X-Wiki-Token": token, "Content-Type": "application/json"})
        answer = json.loads(conn.getresponse().read())
        results = answer.get("results")
        return results if isinstance(results, list) else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="위키와 저장소 문서를 검색한다")
    parser.add_argument("query")
    parser.add_argument("--project", default=None, help="대상 저장소. 없으면 허브 규칙만")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--pool", default="chat", choices=("chat", "hook"))
    args = parser.parse_args()
    project = str(Path(args.project).expanduser().resolve()) if args.project else None

    # The chat may be slow — the plan's condition. Start the daemon if it is
    # not there and wait for it, rather than answering with nothing.
    results = None
    for _attempt in range(60):
        results = ask(args.query, project, args.pool, timeout=5.0, k=args.k, wait=60.0)
        if results is not None:
            break
        time.sleep(1.0)
    if results is None:
        print("검색 데몬이 응답하지 않는다", file=sys.stderr)
        return 1
    for hit in results:
        where = Path(hit["path"])
        try:
            where = where.relative_to(project) if project else where
        except ValueError:
            pass
        print(f"## {where.as_posix()}:{hit['line']} — {hit['heading']}\n\n{hit['text'].strip()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
