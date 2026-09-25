"""Keep-alive — plan bundle 3, step 7f.

The daemon's half runs on a fake clock and a fake `orca`; nothing here types
into a real cell or binds the real port.
"""

import io
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import keepalive  # noqa: E402
import search  # noqa: E402
import searchd  # noqa: E402

HANDLE = "term_cell"
CHECKOUT = str(Path(tempfile.mkdtemp()).resolve())
MIN = 60

# What an idle Claude cell in Orca showed on 2026-09-25, cut to its bottom.
IDLE_SCREEN = [
    "✻ Crunched for 51s · done 5:18 PM",
    "                                                  ✔ Update installed · Restart to update",
    "─" * 120,
    "❯\xa0",
    "─" * 120,
    "  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← 1 agent",
    "",
]


def project(keep_alive: str | None) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / ".wiki").mkdir()
    if keep_alive is not None:
        (root / ".wiki" / "adapter.toml").write_text(
            f'{keep_alive}\nagents = ["claude"]\n\n[slots]\ngate_cmd = "x"\n', encoding="utf-8")
    return root


class Sent:
    """`search.notify` replaced by a list of what would have gone out."""

    def __init__(self, handle: str | None = HANDLE):
        self.calls: list[tuple[str, dict]] = []
        self.was = search.notify, os.environ.get("ORCA_TERMINAL_HANDLE")
        search.notify = lambda path, body, spawn_wait=None: self.calls.append((path, body)) or True
        if handle:
            os.environ["ORCA_TERMINAL_HANDLE"] = handle
        else:
            os.environ.pop("ORCA_TERMINAL_HANDLE", None)

    def close(self):
        search.notify = self.was[0]
        if self.was[1] is None:
            os.environ.pop("ORCA_TERMINAL_HANDLE", None)
        else:
            os.environ["ORCA_TERMINAL_HANDLE"] = self.was[1]


def hook(event: str, repo: Path, host: str = "claude", session: str = "s1") -> int:
    payload = {"hook_event_name": event, "session_id": session, "source": "startup"}
    was = sys.stdin, sys.stdout, sys.argv
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")))
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    sys.argv = ["keepalive.py", "--project", str(repo), "--checkout", CHECKOUT, "--host", host]
    try:
        return keepalive.main()
    finally:
        sys.stdin, sys.stdout, sys.argv = was


# ---- the hooks ----------------------------------------------------------------


def test_the_hooks_send_nothing_unless_claude_in_an_orca_cell_of_a_repository_that_opted_in():
    on = project("keep_alive = 2")
    cases = [
        ("Codex", on, "codex", HANDLE),
        ("no Orca cell", on, "claude", None),
        ("no keep_alive", project(""), "claude", HANDLE),
        ("keep_alive = 0", project("keep_alive = 0"), "claude", HANDLE),
        ("keep_alive = true", project("keep_alive = true"), "claude", HANDLE),
        ("no adapter", project(None), "claude", HANDLE),
    ]
    for name, repo, host, handle in cases:
        sent = Sent(handle)
        try:
            for event in ("SessionStart", "Stop", "SessionEnd"):
                assert hook(event, repo, host) == 0
            assert not keepalive.on_prompt("사람 발화", host, str(repo), "s1")
            assert not keepalive.on_prompt(keepalive.PING, host, str(repo), "s1")
        finally:
            sent.close()
        assert sent.calls == [], (name, sent.calls)

    sent = Sent()
    try:
        for event in ("SessionStart", "Stop", "SessionEnd"):
            hook(event, on)
    finally:
        sent.close()
    assert [p for p, _b in sent.calls] == ["/own", "/idle", "/gone"], sent.calls
    assert sent.calls[1][1] == {"session": "s1", "handle": HANDLE, "checkout": CHECKOUT, "limit": 2}


class Home:
    """No daemon, no state file, the search switch on."""

    def __init__(self):
        self.was = os.environ.pop("WIKI_SEARCH", None), search.spawn, search.SPAWN_WAIT
        search.state_path().unlink(missing_ok=True)

    def close(self):
        search.state_path().unlink(missing_ok=True)
        os.environ["WIKI_SEARCH"] = self.was[0] or "off"
        search.spawn, search.SPAWN_WAIT = self.was[1], self.was[2]


def test_a_notice_starts_the_missing_daemon_waits_for_it_and_is_delivered():
    home = Home()
    daemon = searchd.Daemon("secret", searchd.Embedder(None))
    servers = []

    def start():
        def later():
            time.sleep(0.3)
            server = searchd.serve(0, daemon)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            search.state_path().parent.mkdir(parents=True, exist_ok=True)
            search.state_path().write_text(json.dumps(
                {"port": server.server_address[1], "token": "secret"}), encoding="utf-8")
        threading.Thread(target=later, daemon=True).start()

    search.spawn = start
    try:
        assert search.notify("/own", {"session": "s1", "handle": HANDLE})
        assert daemon.keeper.owners == {HANDLE: "s1"}
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        home.close()


def test_a_notice_is_dropped_when_no_daemon_comes_up_and_the_hook_still_passes():
    home = Home()
    started = []
    search.spawn = lambda: started.append(1)
    search.SPAWN_WAIT = 0.4
    try:
        began = time.perf_counter()
        assert not search.notify("/own", {"session": "s1", "handle": HANDLE})
        assert started == [1]
        assert time.perf_counter() - began < 1.5
        os.environ["ORCA_TERMINAL_HANDLE"], was = HANDLE, os.environ.get("ORCA_TERMINAL_HANDLE")
        try:
            assert hook("Stop", project("keep_alive = 2")) == 0
        finally:
            if was is None:
                os.environ.pop("ORCA_TERMINAL_HANDLE", None)
            else:
                os.environ["ORCA_TERMINAL_HANDLE"] = was
    finally:
        home.close()


# ---- inject.py ----------------------------------------------------------------


def utter(prompt: str, repo: Path) -> str:
    import inject
    import translate

    was = (translate.translate, translate.ko_to_en, sys.stdin, sys.stdout, sys.argv)
    translate.translate = lambda texts, direction=None, deadline=None: list(texts)
    translate.ko_to_en = lambda text, deadline=None: text
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(
        {"prompt": prompt, "session_id": "s1"}, ensure_ascii=False).encode("utf-8")))
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    sys.argv = ["inject.py", "--host", "claude", "--project", str(repo)]
    try:
        inject.main()
        sys.stdout.seek(0)
        return sys.stdout.read()
    finally:
        translate.translate, translate.ko_to_en, sys.stdin, sys.stdout, sys.argv = was


def test_the_ping_turn_carries_nothing_records_nothing_and_says_so():
    repo = project("keep_alive = 2")
    sent = Sent()
    try:
        assert utter(keepalive.PING, repo) == ""
        assert not (repo / ".wiki" / "trajectory.jsonl").exists(), "the ping went into the trajectory"
        utter("<task-notification>\n<task-id>x</task-id>", repo)
        utter("이어서 해라", repo)
    finally:
        sent.close()
    assert sent.calls == [
        ("/ping-turn", {"session": "s1", "handle": HANDLE}),
        ("/busy", {"session": "s1", "handle": HANDLE, "reset": False}),
        ("/busy", {"session": "s1", "handle": HANDLE, "reset": True}),
    ], sent.calls
    rows = (repo / ".wiki" / "trajectory.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2, "the two utterances that are not the ping are recorded as before"


def test_the_ping_turn_answered_ok_is_not_a_promise_to_continue():
    from declared_continuation import verdict

    transcript = Path(tempfile.mkdtemp()) / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(row) for row in [
        {"type": "user", "message": {"content": keepalive.PING}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
    ]), encoding="utf-8")
    assert verdict({"transcript_path": str(transcript)}) is None


# ---- the daemon ---------------------------------------------------------------


class Orca:
    """What the daemon asks Orca, answered from fields a test can change."""

    def __init__(self):
        self.cell = {"connected": True, "writable": True, "worktreePath": CHECKOUT}
        self.screen = list(IDLE_SCREEN)
        self.sent: list[str] = []

    def __call__(self, *args):
        if args[:2] == ("terminal", "show"):
            return {"terminal": dict(self.cell)} if self.cell else None
        if args[:2] == ("terminal", "read"):
            return {"terminal": {"tail": list(self.screen)}}
        if args[:2] == ("terminal", "send"):
            self.sent.append(args[args.index("--text") + 1])
            return {}
        raise AssertionError(args)


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now

    def at(self, minutes: float) -> None:
        self.now = 1_000_000.0 + minutes * MIN


def keeper(orca=None, clock=None):
    clock = clock or Clock()
    return searchd.Keeper(clock, orca or Orca()), clock


def person(k, session="s1", handle=HANDLE):
    k.notice("busy", {"session": session, "handle": handle, "reset": True})


def stop(k, session="s1", handle=HANDLE, limit=2):
    k.notice("idle", {"session": session, "handle": handle, "checkout": CHECKOUT, "limit": limit})


def ping_turn(k, session="s1", handle=HANDLE):
    k.notice("ping-turn", {"session": session, "handle": handle})


def test_one_ping_at_55_minutes_and_none_past_the_cap():
    k, clock = keeper()
    person(k)
    stop(k)
    clock.at(54)
    k.tick()
    assert k.call.sent == []
    clock.at(55)
    k.tick()
    assert k.call.sent == [keepalive.PING]
    ping_turn(k)
    clock.at(56)
    stop(k)
    clock.at(111)
    k.tick()
    assert len(k.call.sent) == 2
    ping_turn(k)
    clock.at(112)
    stop(k)
    for minute in range(113, 240, 5):
        clock.at(minute)
        k.tick()
    assert len(k.call.sent) == 2, "past the cap"


def test_a_harness_utterance_after_a_ping_does_not_reset_the_count():
    k, clock = keeper()
    person(k)
    stop(k)
    clock.at(55)
    k.tick()
    ping_turn(k)
    stop(k)
    k.notice("busy", {"session": "s1", "handle": HANDLE, "reset": False})
    stop(k)
    for minute in range(56, 400, 5):
        clock.at(minute)
        k.tick()
        if k.sessions.get("s1", {}).get("state") == "sent":
            ping_turn(k)
            stop(k)
    assert len(k.call.sent) == 2, k.call.sent


def test_another_session_in_the_same_cell_takes_it_over():
    """The shape of `/clear`: the old session can say nothing more."""

    k, clock = keeper()
    person(k)
    stop(k)
    k.notice("own", {"session": "s2", "handle": HANDLE})
    assert "s1" not in k.sessions and k.owners == {HANDLE: "s2"}
    clock.at(60)
    k.tick()
    assert k.call.sent == []


def test_after_a_restart_the_owner_comes_back_but_the_count_does_not():
    k, clock = keeper()
    stop(k)
    assert k.owners == {HANDLE: "s1"}, "the owner comes back from any notice"
    clock.at(60)
    k.tick()
    assert k.call.sent == [], "first seen at Stop: the count is at the cap"

    k, clock = keeper()
    person(k)
    stop(k)
    clock.at(55)
    k.tick()
    assert k.call.sent == [keepalive.PING], "a person spoke, so the timer is set"


def test_restarts_after_each_ping_never_take_a_session_past_two():
    orca, clock, sent = Orca(), Clock(), 0
    for restart_after in (1, 2):
        k, _ = keeper(orca, clock)
        clock.at(0)
        person(k)
        stop(k)
        for n in range(restart_after):
            clock.at(55 * (n + 1) + n)
            k.tick()
            ping_turn(k)
            stop(k)
        k, _ = keeper(orca, clock)  # the daemon started again
        for source in ("compact", "resume"):
            k.notice("own", {"session": "s1", "handle": HANDLE, "source": source})
            ping_turn(k)
            stop(k)
        for minute in range(0, 600, 5):
            clock.now += 5 * MIN
            k.tick()
            if k.sessions.get("s1", {}).get("state") == "sent":
                ping_turn(k)
                stop(k)
        assert len(orca.sent) - sent <= 2, (restart_after, orca.sent)
        sent = len(orca.sent)


def test_nothing_is_sent_and_the_session_goes_when_the_look_before_sending_fails():
    def run(change, last_is_stop=True):
        orca = Orca()
        change(orca)
        k, clock = keeper(orca)
        person(k)
        stop(k)
        if not last_is_stop:
            k.notice("busy", {"session": "s1", "handle": HANDLE, "reset": False})
        clock.at(55)
        k.tick()
        return orca.sent, k

    sent, k = run(lambda o: None, last_is_stop=False)
    assert sent == [] and k.sessions["s1"]["due"] is None, "the last notice was not Stop"
    cases = {
        "cell gone": lambda o: setattr(o, "cell", None),
        "not writable": lambda o: o.cell.update(writable=False),
        "another repository": lambda o: o.cell.update(worktreePath=str(Path(CHECKOUT).parent)),
        "half-written message": lambda o: o.screen.__setitem__(3, "❯ 이어서 하"),
        "fell back to the shell": lambda o: o.screen.extend(["PS C:\\work> "]),
        "unknown screen": lambda o: setattr(o, "screen", ["$ "]),
    }
    for name, change in cases.items():
        sent, k = run(change)
        assert sent == [], name
        assert "s1" not in k.sessions, name


def test_no_reply_within_ten_minutes_and_expiry_both_drop_the_session():
    k, clock = keeper()
    person(k)
    stop(k)
    clock.at(55)
    k.tick()
    clock.at(64)
    k.tick()
    assert "s1" in k.sessions
    clock.at(65)
    k.tick()
    assert "s1" not in k.sessions, "no ping turn ten minutes after the ping"

    k, clock = keeper()
    person(k)
    stop(k, limit=1)
    clock.at(55)
    k.tick()
    ping_turn(k)
    clock.at(56)
    stop(k, limit=1)
    assert k.sessions["s1"]["expires"] == clock() + 65 * MIN
    clock.at(56 + 65)
    k.tick()
    assert "s1" not in k.sessions, "past its expiry with no notice"


def test_the_idle_shutdown_waits_for_the_last_expiry_and_no_longer():
    daemon = searchd.Daemon("t", searchd.Embedder(None))
    clock = Clock()
    daemon.keeper = searchd.Keeper(clock, Orca())
    daemon.last = time.monotonic() - searchd.IDLE - 1
    assert daemon.finished()
    person(daemon.keeper)
    stop(daemon.keeper)
    assert not daemon.finished()
    clock.at(55 * 2 + 10)
    assert daemon.finished()


def test_the_input_box_reads_empty_only_in_its_own_shape():
    assert searchd.input_empty(IDLE_SCREEN)
    assert searchd.input_empty([*IDLE_SCREEN[:5]]), "no footer"
    assert not searchd.input_empty(IDLE_SCREEN[:3] + ["❯ half"] + IDLE_SCREEN[4:])
    assert not searchd.input_empty(IDLE_SCREEN[:3] + ["❯ first line", "  second"] + IDLE_SCREEN[4:])
    assert not searchd.input_empty(IDLE_SCREEN + ["PS C:\\work> "])
    assert not searchd.input_empty([])


def test_the_daemon_takes_notices_only_with_the_token():
    import http.client

    daemon = searchd.Daemon("secret", searchd.Embedder(None))
    server = searchd.serve(0, daemon)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for token, status in (("wrong", 403), ("secret", 200)):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.request("POST", "/own", body=json.dumps({"session": "s1", "handle": HANDLE}),
                         headers={"X-Wiki-Token": token})
            assert conn.getresponse().status == status
            conn.close()
        assert daemon.keeper.owners == {HANDLE: "s1"}
    finally:
        server.shutdown()
        server.server_close()
