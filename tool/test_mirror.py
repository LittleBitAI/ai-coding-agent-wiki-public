"""What has to stay true about `mirror.py`.

Nothing here touches the network or a real session directory. The translator
is a fake that marks what it was given, so every test asserts on *which*
strings reached it — the mirror's whole job is the difference between prose
and code, and that difference is invisible once a real translation comes back.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from itertools import islice
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mirror as M  # noqa: E402


def fake(texts, direction=None, deadline=None):
    return [f"[ko]{t}" for t in texts]


def claude(kind: str, content) -> dict:
    return {"type": kind, "message": {"role": kind, "content": content}}


def codex(item: dict) -> dict:
    return {"type": "event_msg", "payload": {"type": "item_completed", "item": item}}


# --------------------------------------------------------------------------
# What is printed and what is not
# --------------------------------------------------------------------------


def test_claude_prints_prose_description_and_the_call_itself():
    records = [
        claude("assistant", [
            {"type": "text", "text": "Reading the plan first."},
            {"type": "tool_use", "name": "Bash", "input": {
                "command": "rg -n 'korean_progress' tool/",
                "description": "Find the old hook name",
            }},
        ]),
        # `tool_result` comes back as a user record. It is output, not prose.
        claude("user", [{"type": "tool_result", "content": "tool/lint.py:12: ..."}]),
    ]

    lines = M.render(records, "claude", fake)

    assert lines == [
        "[ko]Reading the plan first.",
        "· [ko]Find the old hook name",
        "$ rg -n 'korean_progress' tool/",
    ]


def test_a_command_is_never_translated():
    """The description says what is happening; the command has to still run."""

    seen: list[str] = []

    def watched(texts, direction=None, deadline=None):
        seen.extend(texts)
        return fake(texts)

    records = [claude("assistant", [
        {"type": "tool_use", "name": "Bash", "input": {
            "command": "npm --prefix web run build",
            "description": "Build the page",
        }},
    ])]

    lines = M.render(records, "claude", watched)

    assert lines[-1] == "$ npm --prefix web run build"
    assert seen == ["Build the page"]


def test_an_edit_arrives_as_the_two_sides():
    records = [claude("assistant", [
        {"type": "tool_use", "name": "Edit", "input": {
            "file_path": "tool/lint.py",
            "old_string": "def ends_adnominal(word):",
            "new_string": "def orphan_tail(word):",
        }},
    ])]

    parts = M.translated(records, "claude", fake)

    assert parts == [(
        M.CODE,
        "tool/lint.py\n- def ends_adnominal(word):\n+ def orphan_tail(word):",
        "",
        "Edit",
    )]


def test_a_huge_write_is_cut_instead_of_flooding_the_mirror():
    records = [claude("assistant", [
        {"type": "tool_use", "name": "Write", "input": {
            "file_path": "web/dist/bundle.js", "content": "x" * 20_000,
        }},
    ])]

    body = M.translated(records, "claude", fake)[0][1]

    assert len(body) < M.CAP + 60
    assert body.endswith("자)")


def test_a_read_carries_no_block_of_its_own():
    """Its one-line description already says everything. Two rows would repeat."""

    records = [claude("assistant", [
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "tool/lint.py", "description": "Read the linter"}},
    ])]

    assert M.render(records, "claude", fake) == ["· [ko]Read the linter"]


def test_claude_leaves_the_person_alone_and_drops_injections():
    records = [
        claude("user", "훅이 조용히 죽는다"),
        claude("user", "<system-reminder>\nPONYTAIL MODE ACTIVE\n</system-reminder>"),
    ]

    assert M.render(records, "claude", fake) == ["▶ 훅이 조용히 죽는다"]


def test_a_message_typed_mid_turn_still_reaches_the_mirror():
    """It never becomes a `user` record, so nine of ten turns went missing.

    Claude Code queues a mid-turn message and absorbs it into the running
    turn. The `enqueue` holds the text as typed; after that it only exists
    wrapped in a `<system-reminder>` inside a tool envelope.
    """

    records = [
        {"type": "queue-operation", "operation": "enqueue",
         "timestamp": "2026-09-22T05:51:34.991Z", "content": "디자인 스킬을 쓰고는 있는거야?"},
        # The same text again when the turn takes it. Printing both doubles it.
        {"type": "queue-operation", "operation": "remove",
         "content": "디자인 스킬을 쓰고는 있는거야?", "reason": "absorbed_mid_turn"},
        # A background task finishing is queued the same way and is not a person.
        {"type": "queue-operation", "operation": "enqueue",
         "content": "<task-notification>\n<task-id>bd0mjjpt7</task-id>"},
    ]

    parts = M.translated(records, "claude", fake)

    assert [(mark, text) for mark, text, _, _ in parts] == [
        (M.SELF, "디자인 스킬을 쓰고는 있는거야?")
    ]


def test_the_persons_own_words_are_never_translated_in_either_language():
    """The overlay prints what was typed. Not a rendering of it.

    The input path hands the agent an English rendering of a Korean
    utterance, and that is what it is for. The overlay runs the other way:
    the person reads it to check what was understood, so a round-tripped
    version of their own sentence is the one thing that makes that check
    worthless. English in, English out — the mark decides this, never the
    language, because the person types both.
    """

    typed = [
        claude("user", [{"type": "text", "text": "point the mirror at codex"}]),
        {"type": "queue-operation", "operation": "enqueue",
         "content": "and keep my input verbatim"},
    ]
    said = [text for _, text, _, _ in M.translated(typed, "claude", fake)]
    said += [
        text
        for _, text, _, _ in M.translated(
            [codex({"type": "UserMessage",
                    "content": [{"type": "text", "text": "read the plan and go"}]})],
            "codex", fake,
        )
    ]

    assert said == [
        "point the mirror at codex",
        "and keep my input verbatim",
        "read the plan and go",
    ]


def test_english_prose_holding_a_protected_korean_term_still_gets_translated():
    """A glossary term is why English prose is allowed Hangul at all.

    `english_progress.py` permits `keep_korean` words inside an English
    description — they name a Korean thing and have no English form. A mirror
    that skipped any line with a Hangul character in it therefore skipped
    exactly the lines the glossary exists for, and showed them in English.
    `translate.worth_translating` already draws this line: English present,
    translate; no English, leave it alone.
    """

    records = [
        claude("assistant", [
            {"type": "text", "text": "Check 나라장터 rules before editing."},
            # No English at all: an old log line from before the flip. The
            # translator leaves this one alone by itself.
            {"type": "text", "text": "훅이 조용히 죽는다"},
        ]),
    ]
    sent: list[str] = []

    def gate(texts, direction=None, deadline=None):
        sent.extend(texts)
        return [
            f"[ko]{t}" if M.T.worth_translating(t, direction) else t for t in texts
        ]

    said = [text for _, text, _, _ in M.translated(records, "claude", gate)]

    assert "Check 나라장터 rules before editing." in sent
    assert said == ["[ko]Check 나라장터 rules before editing.", "훅이 조용히 죽는다"]


def test_a_feed_can_be_told_apart_from_another_feed():
    """The index is a position. Only the id says a position in *what*.

    `gen` and the part index both count from the bottom again in a new
    process, so a tab holding `gen 1, index 200` across a server restart meets
    a feed calling itself the same thing and throws away its first two hundred
    lines as already seen. Two feeds never share an id, whichever process made
    them, which is what lets the tab notice.
    """

    assert M.Feed().id != M.Feed().id

    station = M.Station("claude", poll=0.01)
    first = station.feed.id
    station.point("claude", Path("/one"))
    second = station.feed.id
    station.point("claude", Path("/two"))

    assert len({first, second, station.feed.id}) == 3


def test_a_read_that_lands_inside_a_korean_character_does_not_break_it(tmp_path):
    """The poll stops wherever the writer was, which is routinely mid-character.

    `가` is three bytes. Decoding each chunk as it arrives turns a read that
    took one of them into `�` permanently — the damage is already in the
    string being carried over when the rest lands. What the person typed is
    the one thing the mirror must not alter, so the tail stays bytes and only
    whole lines are decoded.
    """

    line = json.dumps({"type": "queue-operation", "operation": "enqueue",
                       "content": "가"}, ensure_ascii=False).encode("utf-8") + b"\n"
    cut = line.index("가".encode("utf-8")) + 1  # inside the character
    log = tmp_path / "session.jsonl"
    log.write_bytes(line[:cut])

    steps = M.follow(lambda: log, log, poll=0, announce=lambda _p: None)
    first = next(steps)
    log.write_bytes(line)
    second = next(steps)

    assert first == []
    assert [record["content"] for record in second] == ["가"]


def test_a_file_rewritten_larger_between_polls_is_read_from_the_top(tmp_path):
    """A grown size is not proof the file grew.

    Rotation and a rewrite at the same path both replace what was already
    read. If the replacement is longer than the old offset the size says
    "appended", the read resumes in the middle of content it has never seen,
    and everything before that point is gone with nothing to say so. The
    opening bytes do not move while a log is appended to, which is what makes
    them the answer the size cannot give.
    """

    log = tmp_path / "session.jsonl"
    said = lambda text: json.dumps(  # noqa: E731
        {"type": "queue-operation", "operation": "enqueue", "content": text}
    ) + "\n"

    log.write_text(said("old"), encoding="utf-8")
    steps = M.follow(lambda: log, log, poll=0, announce=lambda _p: None)
    first = next(steps)

    log.write_text(said("replaced, and deliberately much longer than what was there"),
                   encoding="utf-8")
    second = next(steps)

    assert [r["content"] for r in first] == ["old"]
    assert [r["content"] for r in second] == [
        "replaced, and deliberately much longer than what was there"
    ]


def test_a_rewrite_that_ends_the_same_way_is_still_caught(tmp_path):
    """Padded so the last 64 bytes match. Two samples of bytes both coincided.

    The opening bytes coincide because every record starts with the same
    keys. The trailing bytes coincide when the records are padded, as they are
    here. What does not coincide is the session: both hosts put an id in the
    first record and neither rewrites it while appending. The samples answered
    "do these bytes differ"; this answers "is this the same session".
    """

    log = tmp_path / "session.jsonl"
    pad = "x" * 100
    said = lambda text: json.dumps(  # noqa: E731
        {"type": "queue-operation", "operation": "enqueue",
         "content": text, "padding": pad}
    ) + "\n"

    was, now = said("old").encode(), said("new").encode()
    # The precondition: the seam alone cannot see this rewrite.
    assert len(was) == len(now) and was[-M.SEAM:] == now[-M.SEAM:]

    log.write_bytes(was)
    steps = M.follow(lambda: log, log, poll=0, announce=lambda _p: None)
    next(steps)

    log.write_bytes(now + said("later").encode())
    second = next(steps)

    assert [r["content"] for r in second] == ["new", "later"]


def test_codex_prints_the_same_things():
    records = [
        codex({"type": "UserMessage", "content": [{"type": "text", "text": "진행해라"}]}),
        codex({"type": "AgentMessage", "content": [
            {"type": "Text", "text": "Checking both hosts."}]}),
        codex({"type": "McpToolCall", "server": "node_repl", "tool": "js",
               "arguments": {"title": "Open the rollout file", "code": "await x()"}}),
        codex({"type": "CommandExecution", "command": ["pytest", "tool/"]}),
        codex({"type": "FileChange", "changes": {
            "a.py": {"type": "update", "unified_diff": "@@\n-old\n+new"}}}),
        codex({"type": "Reasoning", "summary_text": ["**Inspecting the parser**"]}),
    ]

    lines = M.render(records, "codex", fake)

    assert lines == [
        "▶ 진행해라",
        "[ko]Checking both hosts.",
        "· [ko]Open the rollout file",
        "$ await x()",
        "$ pytest tool/",
        "$ a.py\n@@\n-old\n+new",
    ]
    assert not any("Inspecting the parser" in line for line in lines)


def test_korean_prose_is_not_round_tripped():
    """A line with no English comes back as itself, reworded by nobody.

    The mirror does not decide this — `translate.worth_translating` does, and
    it is asserted here through the real function rather than a fake, because
    a fake deciding it would be the fake under test. The mirror's own job is
    the line above: it hands prose over and keeps `SELF` and `CODE` back.
    """

    line = "계획서를 먼저 읽었다."
    assert not M.T.worth_translating(line, M.T.EN_KO)

    seen: list[str] = []

    def watched(texts, direction=None, deadline=None):
        seen.extend(texts)
        return list(texts)  # what the real one returns for these

    records = [claude("assistant", [{"type": "text", "text": line}])]

    assert M.render(records, "claude", watched) == [line]
    assert seen == [line]


def test_a_failed_translation_prints_the_english():
    def gives_up(texts, direction=None, deadline=None):
        return list(texts)  # exactly what translate.py does when it fails open

    records = [claude("assistant", [{"type": "text", "text": "Reading the plan."}])]

    assert M.render(records, "claude", gives_up) == ["Reading the plan."]


# --------------------------------------------------------------------------
# Tailing a file that is being written
# --------------------------------------------------------------------------


def test_a_half_written_line_waits_instead_of_dying(tmp_path):
    log = tmp_path / "session.jsonl"
    whole = json.dumps(claude("assistant", [{"type": "text", "text": "One"}]))
    rest = json.dumps(claude("assistant", [{"type": "text", "text": "Two"}]))
    log.write_text(whole + "\n" + rest[:20], encoding="utf-8")

    passes = M.follow(lambda: log, log, poll=0)
    first = next(passes)
    assert len(first) == 1
    assert M.render(first, "claude", fake) == ["[ko]One"]

    log.write_text(whole + "\n" + rest + "\n", encoding="utf-8")
    second = next(pass_ for pass_ in islice(passes, 3) if pass_)
    assert M.render(second, "claude", fake) == ["[ko]Two"]


def test_truncation_reads_from_the_top_again(tmp_path):
    log = tmp_path / "session.jsonl"
    long = json.dumps(claude("assistant", [{"type": "text", "text": "Before the clear"}]))
    log.write_text(long + "\n", encoding="utf-8")

    passes = M.follow(lambda: log, log, poll=0)
    assert M.render(next(passes), "claude", fake) == ["[ko]Before the clear"]

    short = json.dumps(claude("assistant", [{"type": "text", "text": "After"}]))
    log.write_text(short + "\n", encoding="utf-8")
    batch = next(pass_ for pass_ in islice(passes, 3) if pass_)
    assert M.render(batch, "claude", fake) == ["[ko]After"]


def test_a_new_session_file_is_picked_up(tmp_path):
    first = tmp_path / "one.jsonl"
    second = tmp_path / "two.jsonl"
    first.write_text(
        json.dumps(claude("assistant", [{"type": "text", "text": "Old"}])) + "\n",
        encoding="utf-8",
    )
    current = {"path": first}

    passes = M.follow(lambda: current["path"], None, poll=0)
    assert M.render(next(passes), "claude", fake) == ["[ko]Old"]

    second.write_text(
        json.dumps(claude("assistant", [{"type": "text", "text": "New"}])) + "\n",
        encoding="utf-8",
    )
    current["path"] = second
    batch = next(pass_ for pass_ in islice(passes, 4) if pass_)
    assert M.render(batch, "claude", fake) == ["[ko]New"]


def test_garbage_lines_never_stop_the_mirror(tmp_path):
    log = tmp_path / "session.jsonl"
    log.write_text(
        "not json at all\n"
        "[1, 2, 3]\n"
        + json.dumps(claude("assistant", [{"type": "text", "text": "Still here"}]))
        + "\n",
        encoding="utf-8",
    )

    batch = next(M.follow(lambda: log, log, poll=0))
    assert M.render(batch, "claude", fake) == ["[ko]Still here"]


# --------------------------------------------------------------------------
# The page's feed
# --------------------------------------------------------------------------


def test_a_reconnecting_tab_does_not_redraw_what_it_has(tmp_path):
    """`EventSource` reconnects on its own and the server replays from the top.

    The index is what stops that from doubling the visible session. It is
    absolute, not per-connection, so a tab that dropped mid-stream can tell
    which of the replayed parts it has already drawn.
    """

    feed = M.Feed()
    for text in ("하나", "둘", "셋"):
        feed.add((M.SAID, text, "14:31", ""))

    cursor, first = feed.since(0)
    assert [p["text"] for p in first] == ["하나", "둘", "셋"]
    assert [p["i"] for p in first] == [0, 1, 2]

    # The tab drops and comes back; the server starts over at zero.
    _, replay = feed.since(0)
    drawn = [p for p in replay if p["i"] > first[-1]["i"]]
    assert drawn == []

    feed.add((M.SELF, "넷", "14:32", ""))
    _, more = feed.since(cursor)
    assert [p["text"] for p in more] == ["넷"]
    assert more[0]["at"] == "14:32"


def test_the_feed_forgets_the_far_past_without_losing_its_place():
    feed = M.Feed(keep=2)
    for text in ("하나", "둘", "셋"):
        feed.add((M.SAID, text, "14:31", ""))

    _, parts = feed.since(0)
    assert [p["text"] for p in parts] == ["둘", "셋"]
    # Indices stay absolute, so a tab holding `i == 0` is not sent the second
    # part twice.
    assert [p["i"] for p in parts] == [1, 2]


def test_the_page_says_which_file_it_followed(tmp_path):
    log = tmp_path / "session.jsonl"
    log.write_text(
        json.dumps(claude("assistant", [{"type": "text", "text": "One"}])) + "\n",
        encoding="utf-8",
    )
    feed = M.Feed()

    passes = M.follow(lambda: log, None, 0, lambda p: feed.add((M.SEEN, p.name, "", "")))
    next(passes)

    _, parts = feed.since(0)
    assert parts == [
        {"i": 0, "mark": M.SEEN, "text": "session.jsonl", "at": "", "name": ""}
    ]


def test_the_clock_is_the_reader_s_own():
    """Both hosts stamp UTC with a `Z`. Slicing the string gives the wrong hour.

    `transcript.py` slices, because a retrospective does not care. A mirror
    read at 23:31 KST that says 14:31 is a mirror nobody reads twice, so the
    guard here is that the answer is *not* the slice whenever the machine has
    an offset at all.
    """

    raw = "2026-09-22T14:31:07.921Z"
    offset = dt.datetime.now().astimezone().utcoffset()

    assert M.clock({"timestamp": raw}) != (raw[11:16] if offset else "")
    assert M.clock({"timestamp": "쓰레기"}) == ""
    assert M.clock({}) == ""
    assert len(M.now()) == 5


def test_switching_repos_retires_the_feed_the_old_one_was_filling():
    """A translation is a round trip, so a switch lands mid-flight routinely.

    Without the generation check the answer for the old repo arrives in the
    new repo's feed, and it arrives looking exactly like a real line.
    """

    station = M.Station(host="claude", poll=0)
    station.point("claude", Path("/one"))
    first_gen, first_feed, _, project = station.now()
    assert project == str(Path("/one"))

    station.point("claude", Path("/two"))
    second_gen, second_feed, _, _ = station.now()

    assert second_gen > first_gen
    assert second_feed is not first_feed
    # The retired pump asks this before it appends, and the answer is now no.
    assert station.gen != first_gen

    # Pointing at the same place twice is not a switch. A stream that reset on
    # every poll would clear the screen forever.
    station.point("claude", Path("/two"))
    assert station.now()[0] == second_gen


def test_codex_finds_its_rollout_by_cwd(tmp_path, monkeypatch):
    day = tmp_path / "2026" / "09" / "22"
    day.mkdir(parents=True)
    other = day / "rollout-a.jsonl"
    mine = day / "rollout-b.jsonl"
    for path, cwd in ((other, tmp_path / "elsewhere"), (mine, tmp_path / "repo")):
        path.write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": str(cwd)}}) + "\n",
            encoding="utf-8",
        )
    (tmp_path / "repo").mkdir()
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setattr(M, "codex_homes", lambda: [tmp_path])

    assert M.codex_session((tmp_path / "repo").resolve()) == mine
    assert M.codex_session((tmp_path / "nowhere").resolve()) is None


def test_codex_sessions_are_not_only_under_the_default_home(tmp_path, monkeypatch):
    """Orca gives every Codex cell its own `CODEX_HOME`, per account.

    Reading only `~/.codex/sessions` found none of the sessions the person
    actually runs, and the mirror said "no session" while one was running in
    front of them. Measured, with a live cell open.
    """

    default = tmp_path / "home" / ".codex"
    account = tmp_path / "roaming" / "orca" / "codex-accounts" / "acc-1" / "home"
    moved = tmp_path / "moved"
    for root in (default, account, moved):
        (root / "sessions").mkdir(parents=True)

    monkeypatch.setattr(M.Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("CODEX_HOME", str(moved))

    found = M.codex_homes()

    assert moved / "sessions" in found          # CODEX_HOME wins, and comes first
    assert default / "sessions" in found        # the default is still read
    assert account / "sessions" in found        # and so is every Orca account
    assert found[0] == moved / "sessions"
    assert len(found) == len(set(found))        # a home named twice is read once


def test_a_cell_opened_in_a_subfolder_still_belongs_to_the_repo(tmp_path):
    """Cells get opened in `web/` all the time. `==` reports no session at all."""

    repo = (tmp_path / "repo").resolve()

    assert M.under(repo, repo)
    assert M.under(repo / "web" / "src", repo)
    assert not M.under(repo.parent, repo)
    assert not M.under((tmp_path / "other").resolve(), repo)
    assert not M.under(None, repo)


def test_every_repo_with_a_session_is_offered(tmp_path, monkeypatch):
    """The picker's whole list. A repo appears once, under its latest session."""

    day = tmp_path / "2026" / "09" / "22"
    day.mkdir(parents=True)
    for name, cwd in (
        ("rollout-a.jsonl", tmp_path / "work"),
        ("rollout-b.jsonl", tmp_path / "work" / "web"),  # 같은 저장소의 하위 폴더
        ("rollout-c.jsonl", tmp_path / "other"),
    ):
        (day / name).write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": str(cwd)}}) + "\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(M, "codex_homes", lambda: [tmp_path])

    found = {row["path"] for row in M.repos("codex")}

    assert found == {
        str(tmp_path / "work"),
        str(tmp_path / "work" / "web"),
        str(tmp_path / "other"),
    }
    assert all(row["name"] for row in M.repos("codex"))
