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
import threading
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

    `timeout + wait` bounds the whole call, not each read. A socket timeout
    restarts on every byte, so a peer trickling its answer held a 0.15 s ask
    for 12 s (review round 1). The exchange runs in a daemon thread and is
    abandoned at the deadline; the hook's process exits under it.
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
        # Here, not in the thread: connect is one bounded operation, and a
        # spawn left to a thread the join gave up on dies with the hook.
        conn.connect()
    except OSError:
        # Nothing listening: the daemon died and left its file behind.
        if start:
            spawn()
        return None
    answer: list = []
    worker = threading.Thread(
        target=lambda: answer.append(exchange(conn, token, query, project, pool, deadline, k, wait, start)),
        daemon=True)
    worker.start()
    worker.join(max(0.0, deadline - time.monotonic()) + wait)
    return answer[0] if answer else None


def exchange(conn: http.client.HTTPConnection, token: str, query: str, project, pool: str,
             deadline: float, k: int, wait: float, start: bool) -> list[dict] | None:
    """One health check and one search on a connected socket. `ask` bounds its time."""

    try:
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


def node_of(path: Path, project: Path | None) -> str:
    """A hit's id in the graphs: `scope/name` for a hub rule, the repository
    path otherwise — what `graph.json` and `.wiki/graph.json` call it."""

    hub = HERE.parent
    if path.parent.parent == hub and path.parent.name in ("operator", "craft"):
        return f"{path.parent.name}/{path.stem}"
    for root in (project, hub):
        try:
            return path.relative_to(root).as_posix() if root else path.as_posix()
        except ValueError:
            continue
    return path.as_posix()


def graph(project: Path | None) -> tuple[dict[str, set[str]], dict[str, str]]:
    """`(neighbours, gist)` from the hub's `graph.json` and the repository's
    `.wiki/graph.json` — generated files, so either may be missing.

    The gist is a title and a first paragraph: the hub node's headline and
    rule line, the repository document's title and lead from `corpus.json`.
    """

    near: dict[str, set[str]] = {}
    gist: dict[str, str] = {}

    def load(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    hub = load(HERE.parent / "graph.json")
    for node in hub.get("nodes") or []:
        gist[node["id"]] = f"{node.get('headline', '')} — {node.get('rule', '')}".strip(" —")
    edges = list(hub.get("links") or [])
    if project:
        edges += load(project / ".wiki/graph.json").get("edges") or []
        for doc in load(project / ".wiki/corpus.json").get("docs") or []:
            gist[doc["path"]] = f"{doc.get('title', '')} — {doc.get('lead', '')}".strip(" —")
    for edge in edges:
        near.setdefault(edge["a"], set()).add(edge["b"])
        near.setdefault(edge["b"], set()).add(edge["a"])
    return near, gist


def local(query: str, project: str | None, pool: str, k: int) -> list[dict]:
    """BM25 in this process, for when no daemon can be reached — a sandbox
    that forbids the connection, say. No vectors: loading the model here
    would cost more than the question."""

    import searchd

    index = searchd.Pool(Path(project) if project else None, pool, searchd.Embedder(None))
    index.refresh()
    return index.search(query, k)


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
    for _attempt in range(20):
        results = ask(args.query, project, args.pool, timeout=5.0, k=args.k, wait=60.0)
        if results is not None:
            break
        time.sleep(1.0)
    if results is None:
        print("검색 데몬에 닿지 않아 이 프로세스에서 BM25 만으로 찾았다", file=sys.stderr)
        results = local(args.query, project, args.pool, args.k)

    root = Path(project) if project else None
    near, gist = graph(root)
    shown = {node_of(Path(hit["path"]), root) for hit in results}
    for hit in results:
        path = Path(hit["path"])
        node = node_of(path, root)
        # Relative inside the repository; a hub page outside it keeps its
        # absolute path, so `Read` can open what is printed.
        try:
            where = path.relative_to(root).as_posix() if root else path.as_posix()
        except ValueError:
            where = path.as_posix()
        print(f"## {where}:{hit['line']} — {hit['heading']}\n\n{hit['text'].strip()}\n")
        linked = sorted(near.get(node, set()) - shown)
        shown |= set(linked)
        if linked:
            print("Linked from or to this page:")
            for other in linked:
                print(f"- `{other}` — {gist.get(other, '')}".rstrip(" —"))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
