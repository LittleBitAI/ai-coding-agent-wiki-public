"""mirror — the Korean half of an English-first session.

The agent writes English; this tails the session log the host is already
writing and hands the same turns back in Korean. Nothing here feeds back into
the session, so a mirror that lags, stalls or dies costs reading comfort and
nothing else.

Two ways to read it. The screen is a tab in the wiki app —
`web/src/components/Mirror.tsx` over `chat.py`'s `/api/mirror/*`, which is
where the repository picker lives. Running this file directly tails one
repository to the terminal instead, which needs nothing built and is the
fastest way to answer "is it seeing anything at all".

Two hosts, one shape. Claude Code writes `~/.claude/projects/<slug>/*.jsonl`,
one record per line; Codex writes `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
and stamps the cell's `cwd` into the first record, which is the only thing
that ties a rollout file to a repository. Both are append-only, so both are
read the same way: seek to where the last read stopped, take whole lines, keep
the partial tail for next time.

What gets translated is the short list: the agent's prose, and the one-line
description it writes for a tool call. Commands, patches, file contents and
tool output are code — translating them would be both expensive and wrong.
Anything the person typed is printed exactly as typed, whatever language it
is in. The input path renders their Korean into English for the agent; the
overlay is where they check what was understood, and a round trip of their own
sentence is what makes that check worthless.

A translation failure prints the English original. An empty mirror is worse
than an English one: the person can read English, they just prefer not to.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import translate as T  # noqa: E402
from census import INJECTED, transcript_dir  # noqa: E402
from transcript import SESSIONS, human_text  # noqa: E402

# Where Codex writes its rollouts. Not one place.
#
# The default is `~/.codex`, and `CODEX_HOME` moves it. Orca sets that per
# account, so every Codex cell launched from Orca writes under
# `%APPDATA%/orca/codex-accounts/<id>/home` and none of it appears in the
# default. A mirror that reads only the default sees no session the person
# actually runs, and says "no session" while one is running in front of them —
# which is exactly what it did.
def codex_homes() -> list[Path]:
    """Every session directory this machine's Codex could be writing into."""

    roots = [Path(os.environ["CODEX_HOME"])] if os.environ.get("CODEX_HOME") else []
    roots.append(Path.home() / ".codex")
    accounts = Path(
        os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    ) / "orca" / "codex-accounts"
    if accounts.is_dir():
        roots += [account / "home" for account in accounts.iterdir() if account.is_dir()]
    found = [root / "sessions" for root in roots]
    return [path for path in dict.fromkeys(found) if path.is_dir()]


# How many rollout files back to look before giving up on finding this repo's
# Codex cell. They are one per session and dated, so the answer is always in
# the newest handful unless the cell has been idle for weeks.
CODEX_DEPTH = 60

POLL = 1.0

# Markers, not labels. `SELF` is what the person typed and is printed as
# typed — the mark decides that, not the language, because the person writes
# both. `SAID` and `DID` get translated. `CODE` is the call itself — the command, the
# patch — and is the one thing here that must arrive byte for byte, so it never
# goes near the translator. `SEEN` is the mirror talking about itself.
SELF = "▶"
SAID = ""
DID = "·"
CODE = "$"
SEEN = "──"

# How much of one command or patch to carry. A `Write` of a whole file is not
# something anyone reads in a mirror; the first screenful says what changed and
# the rest is already on disk.
CAP = 4000


def clock(record: dict) -> str:
    """`HH:MM` in the person's own zone, or `""`.

    Both hosts stamp the record in UTC with a trailing `Z`, which `fromisoformat`
    refuses before 3.11 and which nobody reading a mirror at 23:31 KST wants to
    see as 14:31. The conversion is the point; the string is not.
    """

    raw = record.get("timestamp")
    if not isinstance(raw, str):
        return ""
    try:
        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return when.astimezone().strftime("%H:%M")


def now() -> str:
    return dt.datetime.now().strftime("%H:%M")


def parse(line: str) -> dict | None:
    """A JSONL line, or `None` for anything that is not one.

    The last line of a file being written is routinely half a record. It comes
    back `None` here and arrives whole on the next read.
    """

    line = line.strip()
    if not line:
        return None
    try:
        record = json.loads(line)
    except Exception:
        return None
    return record if isinstance(record, dict) else None


# --------------------------------------------------------------------------
# What each host's records say
# --------------------------------------------------------------------------


def clip(text: str) -> str:
    text = text.rstrip()
    if len(text) <= CAP:
        return text
    return text[:CAP] + f"\n…(+{len(text) - CAP}자)"


def diff(old: str, new: str) -> str:
    """The edit itself, as the two sides. Not a real unified diff on purpose.

    `Edit` hands over the exact strings it matched and wrote, which is already
    the whole change. Running a differ over them would reorder and re-chunk
    what the agent actually sent, and the point of this block is that it is
    what was sent.
    """

    return "\n".join(
        [f"- {line}" for line in old.splitlines()]
        + [f"+ {line}" for line in new.splitlines()]
    )


def claude_payload(name: str, given: dict) -> str:
    """The verbatim half of a tool call: the command, or the change.

    Only the calls whose body is the work. A `Read` or a `Glob` is fully
    described by its one-line description, and printing its arguments under
    that line would be the mirror repeating itself in two languages.
    """

    if name == "Bash":
        return str(given.get("command") or "")
    if name in ("Edit", "NotebookEdit"):
        where = str(given.get("file_path") or given.get("notebook_path") or "")
        body = diff(
            str(given.get("old_string") or given.get("old_source") or ""),
            str(given.get("new_string") or given.get("new_source") or ""),
        )
        return f"{where}\n{body}".strip()
    if name == "Write":
        return f"{given.get('file_path') or ''}\n{given.get('content') or ''}".strip()
    return ""


def claude_parts(record: dict) -> list[tuple[str, str, str]]:
    # A message typed while the agent is mid-turn never becomes a `user`
    # record. It is queued, absorbed into the running turn, and the only place
    # its text survives intact is the `enqueue` — afterwards it lives inside a
    # `<system-reminder>` wrapper in a tool envelope, which is not the person's
    # words any more. Without this the mirror shows one turn out of nine.
    if record.get("type") == "queue-operation":
        if record.get("operation") != "enqueue":
            return []  # `remove` repeats the same text when the turn absorbs it
        body = str(record.get("content") or "").strip()
        if not body or any(mark in body for mark in INJECTED):
            return []
        return [(SELF, body, "")]

    typed = human_text(record)
    if typed is not None:
        return [(SELF, typed, "")]
    if record.get("type") != "assistant":
        return []  # `tool_result` arrives as a `user` record and stops here
    content = (record.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    out: list[tuple[str, str, str]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                out.append((SAID, text, ""))
        elif block.get("type") == "tool_use":
            given = block.get("input")
            if not isinstance(given, dict):
                continue
            name = str(block.get("name") or "")
            note = given.get("description")
            if isinstance(note, str) and note.strip():
                out.append((DID, note.strip(), name))
            body = claude_payload(name, given)
            if body:
                out.append((CODE, clip(body), name))
    return out


def codex_parts(record: dict) -> list[tuple[str, str, str]]:
    """Only `item_completed`, which is Codex's already-filtered view.

    The raw `response_item` records carry the same turns plus the developer
    preamble, the skills catalogue and the environment block — every injection
    this mirror must not print. `item_completed` has none of that, and its
    `McpToolCall.arguments.title` is the same one-line description Claude
    writes on a tool call.
    """

    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "item_completed":
        return []
    item = payload.get("item")
    if not isinstance(item, dict):
        return []
    kind = item.get("type")

    if kind == "McpToolCall":
        given = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        name = str(item.get("tool") or "")
        out: list[tuple[str, str, str]] = []
        note = given.get("title")
        if isinstance(note, str) and note.strip():
            out.append((DID, note.strip(), name))
        body = given.get("code") or given.get("command") or given.get("input")
        if isinstance(body, str) and body.strip():
            out.append((CODE, clip(body), name))
        return out

    if kind == "CommandExecution":
        command = item.get("command")
        line = " ".join(command) if isinstance(command, list) else str(command or "")
        return [(CODE, clip(line), "shell")] if line.strip() else []

    if kind == "FileChange":
        # Codex hands over a unified diff it already built. Carry it across.
        changes = item.get("changes")
        return [
            (CODE, clip(f"{where}\n{body.get('unified_diff') or ''}"), "apply_patch")
            for where, body in (changes or {}).items()
            if isinstance(body, dict) and body.get("unified_diff")
        ]

    if kind not in ("UserMessage", "AgentMessage"):
        return []
    content = item.get("content")
    body = "\n".join(
        str(block.get("text") or "")
        for block in (content if isinstance(content, list) else [])
        if isinstance(block, dict) and str(block.get("type", "")).lower() == "text"
    ).strip()
    if not body:
        return []
    return [(SELF if kind == "UserMessage" else SAID, body, "")]


# --------------------------------------------------------------------------
# Which file to tail
# --------------------------------------------------------------------------


def newest(paths) -> Path | None:
    def when(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return -1.0

    return max(paths, key=when, default=None)


def claude_session(project: Path) -> Path | None:
    folder = transcript_dir(project, SESSIONS)
    return newest(folder.glob("*.jsonl")) if folder.is_dir() else None


def codex_cwd(path: Path) -> Path | None:
    """The `cwd` out of the first record. Nothing else ties a rollout to a repo."""

    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            record = parse(fh.readline())
    except OSError:
        return None
    payload = (record or {}).get("payload")
    raw = payload.get("cwd") if isinstance(payload, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        return Path(raw).resolve()
    except OSError:
        return None


def codex_rollouts() -> list[Path]:
    """The newest rollouts across every session directory, merged and sorted."""

    found: list[Path] = []
    for root in codex_homes():
        found += root.rglob("rollout-*.jsonl")
    return sorted(
        found,
        key=lambda p: p.stat().st_mtime if p.exists() else -1.0,
        reverse=True,
    )[:CODEX_DEPTH]


def under(cwd: Path | None, project: Path) -> bool:
    """Is that cell working inside this repository?

    Not `==`. A cell is routinely opened in a subdirectory — `web/`, a package
    folder — and an exact match silently reports "no session" for a repo whose
    mirror is sitting right there.
    """

    return cwd is not None and (cwd == project or project in cwd.parents)


def claude_cwd(path: Path) -> Path | None:
    """The checkout this session ran in, read out of the log.

    The directory name is that path with every separator flattened to `-`,
    which is lossy: a repo whose own name contains a hyphen cannot be told
    from a nested one. The records carry the real thing, so read it instead of
    trying to undo the flattening. It is not on the first line — the first few
    records are bookkeeping — so a handful get checked.
    """

    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for _ in range(8):
                record = parse(fh.readline())
                if record is None:
                    continue
                raw = record.get("cwd")
                if isinstance(raw, str) and raw:
                    return Path(raw).resolve()
    except OSError:
        return None
    return None


def repos(host: str) -> list[dict]:
    """Every checkout this host has a session for, newest first.

    Both hosts stamp the real path into the log, so neither list is a guess.
    A repo appears once, under its most recent session.
    """

    seen: dict[str, float] = {}
    if host == "codex":
        for path in codex_rollouts():
            where = codex_cwd(path)
            if where is None:
                continue
            when = path.stat().st_mtime if path.exists() else 0.0
            seen[str(where)] = max(seen.get(str(where), 0.0), when)
    elif SESSIONS.is_dir():
        for folder in SESSIONS.iterdir():
            if not folder.is_dir():
                continue
            latest = newest(folder.glob("*.jsonl"))
            if latest is None:
                continue
            where = claude_cwd(latest)
            if where is None:
                continue
            when = latest.stat().st_mtime
            seen[str(where)] = max(seen.get(str(where), 0.0), when)

    return [
        {"path": path, "name": Path(path).name, "at": when}
        for path, when in sorted(seen.items(), key=lambda row: -row[1])
    ]


def codex_session(project: Path) -> Path | None:
    for path in codex_rollouts():
        if under(codex_cwd(path), project):
            return path
    return None


HOSTS = {
    "claude": (claude_session, claude_parts),
    "codex": (codex_session, codex_parts),
}


# --------------------------------------------------------------------------
# Tail and print
# --------------------------------------------------------------------------


def translated(records: list[dict], host: str, translator=T.translate):
    """Records in, `(marker, Korean, HH:MM)` out. One request for the batch.

    Which of those are worth a request is `translate.worth_translating`'s
    answer, not one made again here. It skips a line with no English in it, so
    an old Korean log line is not round-tripped into a reworded version of
    itself — and it does *not* skip an English line that carries a protected
    Korean term, which a second "has any Hangul" test here did. The glossary
    holds those terms precisely so they can stand inside English prose.
    """

    _, parts_of = HOSTS[host]
    parts = [
        (mark, text, clock(record), name)
        for record in records
        for mark, text, name in parts_of(record)
    ]
    # `SELF` is what the person typed and `CODE` is a command or a patch.
    # Translating either is the one thing this mirror must never do: the
    # person's own words come back reworded — and they came in here to read
    # what was understood, not a rewording of what they said — while a
    # translated command is a command that no longer runs.
    wanted = [
        i for i, (mark, _, _, _) in enumerate(parts) if mark not in (SELF, CODE)
    ]
    if wanted:
        done = translator([parts[i][1] for i in wanted], T.EN_KO)
        for i, text in zip(wanted, done):
            parts[i] = (parts[i][0], text, parts[i][2], parts[i][3])
    return parts


def render(records: list[dict], host: str, translator=T.translate) -> list[str]:
    return [
        " ".join(word for word in (at, mark, text) if word)
        for mark, text, at, _ in translated(records, host, translator)
    ]


def follow(pick, session: Path | None = None, poll: float = POLL, announce=None):
    """Yield one batch of records per pass, `[]` when there is nothing new.

    Yielding on an empty pass is what makes this testable: a caller can take a
    fixed number of passes instead of waiting for an infinite loop to feel
    like stopping.

    Three things go wrong with the file and all three land here. It gets
    truncated — read from the top again. It disappears — find another. A new
    session file appears beside it (`/clear` does this, and so does a second
    cell) — switch, but only while idle, so a switch can never eat a batch
    that was about to be printed. `--session` pins the file and turns all of
    that off except truncation. `announce` is how the caller learns which file
    that ended up being — the terminal prints it, the page draws a divider.
    """

    if announce is None:
        announce = lambda path: print(f"── {path.name}", flush=True)  # noqa: E731
    path, offset, tail = session, 0, ""
    while True:
        if path is None or not path.exists():
            found = pick()
            if found != path:
                path, offset, tail = found, 0, ""
                if path is not None:
                    announce(path)
        if path is None:
            yield []
            time.sleep(poll)
            continue

        try:
            size = path.stat().st_size
        except OSError:
            path = None
            yield []
            continue

        if size < offset:
            offset, tail = 0, ""
        if size == offset:
            if session is None:
                found = pick()
                if found is not None and found != path:
                    path, offset, tail = found, 0, ""
                    announce(path)
                    continue
            yield []
            time.sleep(poll)
            continue

        try:
            with path.open("rb") as fh:
                fh.seek(offset)
                chunk = fh.read()
                offset = fh.tell()
        except OSError:
            path = None
            yield []
            continue

        tail += chunk.decode("utf-8", errors="replace")
        *whole, tail = tail.split("\n")
        yield [r for r in (parse(line) for line in whole) if r is not None]


# --------------------------------------------------------------------------
# What the screen reads
#
# One tail, one translation, many tabs. The producer runs once in a thread and
# writes into `Feed`; every tab reading the stream replays from the same list.
# Two tabs must not mean two tails — that is two of every translation, and the
# second one is also a second answer to "which file is current".
#
# The screen itself is `web/src/components/Mirror.tsx`, served by `chat.py`
# with the rest of the wiki app. This file holds no HTTP: a second server on a
# second port was a second stack to keep in step, and the mirror wants the same
# tokens, the same components and the same `/api/translate` as its neighbours.
# --------------------------------------------------------------------------

# How much of the session a tab that opens late gets to read. The whole file
# would be honest and useless: the person opens the mirror to see what is
# happening now.
KEEP = 400

BEAT = 0.4


class Feed:
    """What the mirror has said, with an index so a tab can catch up once.

    The index is absolute and travels with each part. A dropped connection is
    reconnected and the server starts replaying from the top when it is, so
    without the index that reconnect duplicates the whole visible session.

    `id` is what makes the index mean anything to a tab. Both the index and
    the generation number start again from the bottom when this process does,
    so a tab holding `gen 1, index 200` across a server restart meets a new
    feed calling itself the same thing and silently discards its first two
    hundred lines. The number says where in a feed; only this says which feed.
    """

    def __init__(self, keep: int = KEEP) -> None:
        self.items: deque = deque(maxlen=keep)
        self.count = 0
        self.id = uuid.uuid4().hex
        self.lock = threading.Lock()

    def add(self, part: tuple[str, str, str, str]) -> None:
        with self.lock:
            self.items.append(part)
            self.count += 1

    def since(self, cursor: int) -> tuple[int, list[dict]]:
        with self.lock:
            start = self.count - len(self.items)
            begin = max(cursor, start)
            rows = list(self.items)[begin - start:]
            return self.count, [
                {"i": begin + n, "mark": mark, "text": text, "at": at, "name": name}
                for n, (mark, text, at, name) in enumerate(rows)
            ]


def pump(feed: Feed, pick, session: Path | None, poll: float, host: str, mine) -> None:
    """Tail, translate, append — until this feed stops being the current one.

    `mine()` is the ownership question, asked once per pass. A translation is
    a network call, so a switch lands mid-flight more often than not; without
    the check the answer to the old repo arrives in the new repo's feed, and
    it arrives looking exactly like a real line.
    """

    def seen(path: Path) -> None:
        feed.add((SEEN, path.name, now(), ""))

    try:
        for batch in follow(pick, session, poll, seen):
            if not mine():
                return
            parts = translated(batch, host)
            if not mine():
                return  # the switch happened while the batch was being translated
            for part in parts:
                feed.add(part)
    except Exception as error:  # noqa: BLE001 -- a dead thread has to say so
        feed.add((SAID, f"미러가 멈췄다: {type(error).__name__}", now(), ""))


class Station:
    """What the mirror is pointed at, and the right to change it.

    Switching repositories is the one thing the page asks the server to *do*,
    so the generation counter is decided here rather than bolted on later. The
    number goes up on every switch, it travels out with every payload, and the
    tab throws away anything that does not carry the number it is showing.
    """

    def __init__(self, host: str, poll: float, session: Path | None = None) -> None:
        self.lock = threading.Lock()
        self.poll = poll
        self.session = session
        self.gen = 0
        self.host = host
        self.project: Path | None = None
        self.feed = Feed()

    def now(self) -> tuple[int, Feed, str, str]:
        with self.lock:
            return self.gen, self.feed, self.host, str(self.project or "")

    def point(self, host: str, project: Path) -> None:
        with self.lock:
            if host == self.host and project == self.project:
                return
            self.gen += 1
            self.host, self.project, self.feed = host, project, Feed()
            gen, feed = self.gen, self.feed
            # A pinned file belongs to the repo it was pinned for. Once the
            # person picks another one, "follow the newest" is what they meant.
            session = self.session if self.project == project else None

        find, _ = HOSTS[host]
        threading.Thread(
            target=pump,
            args=(feed, lambda: find(project), session, self.poll, host,
                  lambda: self.gen == gen),
            daemon=True,
        ).start()


def main() -> int:
    """The terminal tail. The screen is a tab in the wiki app, not this.

    Kept because it needs nothing built: no npm, no venv, no server. When the
    question is "is the parser seeing anything at all", this answers it in one
    command, and that is the question every time the mirror looks empty.
    """

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="세션 로그를 한국어로 옮겨 찍는다.")
    ap.add_argument("--host", choices=sorted(HOSTS), default="claude")
    ap.add_argument(
        "--project", type=Path, default=Path.cwd(),
        help="비출 저장소. 미러가 어디서 도는지와 무관하다",
    )
    ap.add_argument("--session", type=Path, default=None, help="따라갈 jsonl 경로")
    ap.add_argument("--poll", type=float, default=POLL)
    args = ap.parse_args()

    project = args.project.expanduser().resolve()
    find, _ = HOSTS[args.host]

    def pick() -> Path | None:
        return find(project)

    if args.session is None and pick() is None:
        print(f"{project} 의 {args.host} 세션 로그를 아직 못 찾았다.", file=sys.stderr)
        others = [r["path"] for r in repos(args.host) if r["path"] != str(project)]
        if others:
            print("세션이 있는 저장소는 이것들이다:", file=sys.stderr)
            for where in others[:8]:
                print(f"  --project {where}", file=sys.stderr)
        else:
            print("그 호스트로 한 번 말을 걸면 파일이 생긴다.", file=sys.stderr)
        print("계속 기다린다.", file=sys.stderr, flush=True)

    try:
        for batch in follow(pick, args.session, args.poll):
            for line in render(batch, args.host):
                print(line, end="\n\n", flush=True)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
