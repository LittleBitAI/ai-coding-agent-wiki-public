"""format_rows 가 무엇을 잘못 쪼갤 수 있는지만 본다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from slack_brief import SEP, format_rows  # noqa: E402

URL = "https://github.com/o/r"


def test_한_커밋은_한_줄이다():
    raw = f"f6ecc4e5{SEP}수정: 예산을 올린다 (#98)\nec16ebad{SEP}문서: 표를 맞춘다"
    rows = format_rows(raw, URL)
    assert len(rows) == 2, rows


def test_pr_번호는_두_번째_링크가_된다():
    rows = format_rows(f"f6ecc4e5{SEP}수정: 예산을 올린다 (#98)", URL)
    assert f"[`f6ecc4e5`]({URL}/commit/f6ecc4e5)" in rows[0]
    assert f"[#98]({URL}/pull/98)" in rows[0]
    assert "(#98)" not in rows[0].replace(f"[#98]({URL}/pull/98)", "")


def test_제목의_파이프는_제목에_남는다():
    rows = format_rows(f"abc1234{SEP}수정: a|b 를 가른다", URL)
    assert rows[0].endswith("수정: a|b 를 가른다"), rows[0]


def test_공용_상태_한_줄은_기본이_한국어다():
    """`session_state.report` 하나를 영어로 바꾸려다 Slack 과 웹 인계까지
    영어가 되는 것을 막는다.

    `branch_line`·`decisions`·`active_page` 는 세 소비자가 나눠 쓴다. 번역을
    이 함수들 안에 넣으면 에이전트 컨텍스트 하나를 고치는 값으로 사람이 읽는
    화면 둘이 같이 바뀐다. 그래서 영어는 `report()` 가 명시적으로 고른다.
    """

    # `tmp_path` 픽스처를 안 쓴다. 이 파일 끝의 직접 실행 러너가 인자 없이
    # 부르므로, 픽스처를 받으면 pytest 에서만 도는 검사가 된다.
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


def test_리모트가_없으면_링크_없이_해시만():
    rows = format_rows(f"abc1234{SEP}수정: 무언가", "")
    assert rows == ["- `abc1234` 수정: 무언가"]


def test_빈_출력은_빈_목록():
    assert format_rows("", URL) == []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
