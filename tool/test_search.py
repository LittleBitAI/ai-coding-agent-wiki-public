"""The search daemon and its client, without a model.

The embedder is off throughout, so the daemon ranks with BM25 alone — the
same path it takes while the model downloads or where `onnxruntime` is
missing. Nothing here downloads anything or binds the real port.
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import search  # noqa: E402
import searchd  # noqa: E402

RULE = """---
severity: contract
triggers: ["zzz"]
---

# {title}

Rule. {rule}

## Detail

{detail}
"""


def wiki(root: Path) -> Path:
    (root / "operator").mkdir(parents=True)
    (root / "craft").mkdir()
    (root / "operator" / "merge.md").write_text(RULE.format(
        title="Clean up after a merge", rule="Delete the merged branch.",
        detail="```\n## not a heading\n```\nPrune the remote too."), encoding="utf-8")
    (root / "craft" / "fonts.md").write_text(RULE.format(
        title="Type scale", rule="Keep the type scale small.", detail="화면 글꼴 크기를 줄인다."),
        encoding="utf-8")
    (root / "craft" / "note.md").write_text("---\nseverity: reference\n---\n\n# Merge notes\n",
                                            encoding="utf-8")
    return root


def test_terms_are_english_words_and_hangul_bigrams():
    assert searchd.terms("Hook 훅이 느리다 v2_x") == ["hook", "훅이", "느리", "리다", "v2_x"]
    assert searchd.terms("훅") == ["훅"]


def test_chunks_cut_at_headings_and_know_their_lines():
    text = RULE.format(title="T", rule="R.", detail="```\n## fenced\n```\nbody")
    found = searchd.chunks(text, Path("x.md"))
    assert [c["line"] for c in found] == [6, 10], found
    assert found[1]["heading"] == "T > Detail"
    assert "## fenced" in found[1]["text"], "a heading inside a fence cut the chunk"
    assert text.splitlines()[found[1]["line"] - 1] == "## Detail"
    bare = searchd.chunks("# T\n\nintro\n\n## Steps\n\n### 1. First\n\ndo it\n", Path("x.md"))
    assert [c["heading"] for c in bare] == ["T", "T > Steps > 1. First"], bare


def test_the_hook_pool_keeps_only_injectable_pages_and_ranks_by_bm25():
    root = wiki(Path(tempfile.mkdtemp()))
    was = searchd.WIKI
    searchd.WIKI = root
    try:
        pool = searchd.Pool(None, "hook", searchd.Embedder(None))
        pool.refresh()
        hits = pool.search("merged branch 머지", 5)
        names = [Path(h["path"]).stem for h in hits]
        assert names[0] == "merge", hits
        assert "note" not in {Path(c["path"]).stem for c in pool.chunks}
        assert hits[0]["cos"] is None, "no vectors, so no cosine"
        assert Path(pool.search("글꼴 크기", 5)[0]["path"]).stem == "fonts"
    finally:
        searchd.WIKI = was


def test_an_edited_page_is_cut_again():
    root = wiki(Path(tempfile.mkdtemp()))
    was = searchd.WIKI
    searchd.WIKI = root
    try:
        pool = searchd.Pool(None, "hook", searchd.Embedder(None))
        pool.refresh()
        page = root / "craft" / "fonts.md"
        page.write_text(page.read_text(encoding="utf-8").replace("small", "quokka"), encoding="utf-8")
        os.utime(page, ns=(1, 10**18))
        pool.refresh()
        assert Path(pool.search("quokka", 1)[0]["path"]).stem == "fonts"
    finally:
        searchd.WIKI = was


class Running:
    """A daemon on a free port with a state file in the test home."""

    def __init__(self, token="secret", version=None):
        self.root = wiki(Path(tempfile.mkdtemp()))
        self.was = searchd.WIKI, os.environ.pop("WIKI_SEARCH", None), search.spawn
        searchd.WIKI = self.root
        self.spawned = []
        search.spawn = lambda: self.spawned.append(1)
        self.daemon = searchd.Daemon(token, searchd.Embedder(None))
        self.server = searchd.serve(0, self.daemon)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        search.state_path().parent.mkdir(parents=True, exist_ok=True)
        search.state_path().write_text(json.dumps({"port": self.port, "token": "secret"}),
                                       encoding="utf-8")
        if version:
            self.running = searchd.RUNNING
            searchd.RUNNING = version

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        search.state_path().unlink(missing_ok=True)
        searchd.WIKI, off, search.spawn = self.was
        if off is not None:
            os.environ["WIKI_SEARCH"] = off
        if hasattr(self, "running"):
            searchd.RUNNING = self.running


def test_ask_gets_an_answer_from_a_running_daemon():
    run = Running()
    try:
        hits = search.ask("merged branch", None, "hook", timeout=5)
        assert hits and Path(hits[0]["path"]).stem == "merge", hits
        assert not run.spawned
    finally:
        run.close()


def test_a_server_that_cannot_prove_the_token_is_not_sent_the_query():
    run = Running(token="someone-else")
    try:
        asked = []
        real = run.daemon.search
        run.daemon.search = lambda *a: asked.append(a) or real(*a)
        assert search.ask("merged branch", None, "hook", timeout=5) is None
        assert not asked, "the utterance went to a server that did not hold the token"
        assert not run.spawned, "another daemon cannot take a port somebody holds"
    finally:
        run.close()


def test_a_stale_version_is_told_to_quit_and_replaced():
    run = Running(version="old")
    try:
        assert search.ask("merged branch", None, "hook", timeout=5) is None
        assert run.spawned == [1]
    finally:
        run.close()


def test_no_state_file_starts_the_daemon_without_connecting():
    was = os.environ.pop("WIKI_SEARCH", None), search.spawn
    spawned = []
    search.spawn = lambda: spawned.append(1)
    search.state_path().unlink(missing_ok=True)
    try:
        assert search.ask("q", None, "hook", timeout=0.15) is None
        assert spawned == [1]
    finally:
        os.environ["WIKI_SEARCH"], search.spawn = was[0] or "off", was[1]


def test_a_dead_daemon_left_behind_is_replaced():
    was = os.environ.pop("WIKI_SEARCH", None), search.spawn
    spawned = []
    search.spawn = lambda: spawned.append(1)
    import socket

    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()
    search.state_path().parent.mkdir(parents=True, exist_ok=True)
    search.state_path().write_text(json.dumps({"port": port, "token": "t"}), encoding="utf-8")
    try:
        assert search.ask("q", None, "hook", timeout=0.15) is None
        assert spawned == [1]
    finally:
        search.state_path().unlink(missing_ok=True)
        os.environ["WIKI_SEARCH"], search.spawn = was[0] or "off", was[1]


def test_the_port_is_the_lock():
    daemon = searchd.Daemon("t", searchd.Embedder(None))
    first = searchd.serve(0, daemon)
    try:
        assert searchd.serve(first.server_address[1], daemon) is None
    finally:
        first.server_close()


def test_quit_needs_the_token():
    run = Running()
    try:
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", run.port, timeout=5)
        conn.request("POST", "/quit", body=b"{}", headers={"X-Wiki-Token": "wrong"})
        assert conn.getresponse().status == 403
        conn.close()
        assert search.ask("merged branch", None, "hook", timeout=5), "a bad token stopped it"
    finally:
        run.close()
