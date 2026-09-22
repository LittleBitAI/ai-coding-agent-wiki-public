"""Only the ways `format_rows` can split something wrongly.

The Korean in the fixtures is input data: these are real commit subjects, and
what is being measured is a separator surviving them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from slack_brief import SEP, format_rows  # noqa: E402

URL = "https://github.com/o/r"


def test_one_commit_is_one_row():
    """The separator must not be something `splitlines()` treats as a break.

    With `\\x1e` as the separator one commit became two rows and the count
    silently went to zero.
    """

    raw = f"f6ecc4e5{SEP}수정: 예산을 올린다 (#98)\nec16ebad{SEP}문서: 표를 맞춘다"
    rows = format_rows(raw, URL)
    assert len(rows) == 2, rows


def test_a_pr_number_becomes_a_second_link():
    rows = format_rows(f"f6ecc4e5{SEP}수정: 예산을 올린다 (#98)", URL)
    assert f"[`f6ecc4e5`]({URL}/commit/f6ecc4e5)" in rows[0]
    assert f"[#98]({URL}/pull/98)" in rows[0]
    assert "(#98)" not in rows[0].replace(f"[#98]({URL}/pull/98)", "")


def test_a_pipe_in_the_subject_stays_in_the_subject():
    """`partition` splits on the first `|` only, so a subject may contain one."""

    rows = format_rows(f"abc1234{SEP}수정: a|b 를 가른다", URL)
    assert rows[0].endswith("수정: a|b 를 가른다"), rows[0]


def test_the_shared_status_line_is_korean_by_default():
    """Stops one English `session_state.report` turning Slack English as well.

    `branch_line`, `decisions` and `active_page` are shared by three
    consumers. Putting the translation inside those functions changes two
    screens a person reads for the price of fixing one agent context, so
    English is something `report()` asks for explicitly.
    """

    # No `tmp_path` fixture. The direct-run runner at the bottom of this file
    # calls these with no arguments, so taking a fixture would make this a
    # check that only runs under pytest.
    import subprocess
    import tempfile

    from session_state import branch_line

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for args in (["init", "-q"], ["config", "user.email", "t@e.com"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", tmp, *args], check=True,
                           capture_output=True, encoding="utf-8", errors="replace")

        assert "워크트리 깨끗" in branch_line(repo)
        assert "worktree clean" in branch_line(repo, english=True)


def test_with_no_remote_the_hash_stands_without_a_link():
    rows = format_rows(f"abc1234{SEP}수정: 무언가", "")
    assert rows == ["- `abc1234` 수정: 무언가"]


def test_empty_output_is_an_empty_list():
    assert format_rows("", URL) == []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
