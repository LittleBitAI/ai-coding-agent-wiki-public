"""주입 기록이 앞 턴을 제대로 채점하는지만 본다."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trajectory  # noqa: E402


def wiki() -> Path:
    return Path(tempfile.mkdtemp()) / ".wiki"


def say(root: Path, prompt: str, session: str = "s1", injected=None) -> None:
    trajectory.record(root, prompt, injected or [], 100, session)


def test_같은_세션이면_다음_발화가_앞_턴을_채점한다():
    root = wiki()
    say(root, "주석 좀 고쳐줘")
    say(root, "아니, 그게 아니라 줄바꿈을 말한 거다")
    rows = trajectory.rows(root)
    assert len(rows) == 2, rows
    assert "prev" not in rows[0], rows[0]
    assert rows[1]["prev"] == "교정", rows[1]


def test_평범한_다음_발화는_ok_다():
    root = wiki()
    say(root, "주석 좀 고쳐줘")
    say(root, "이제 커밋해라")
    assert trajectory.rows(root)[1]["prev"] == "ok"


def test_세션이_바뀌면_앞_줄을_채점하지_않는다():
    root = wiki()
    say(root, "주석 좀 고쳐줘", session="s1")
    say(root, "아니, 틀렸다", session="s2")
    assert "prev" not in trajectory.rows(root)[1]


def test_세션_id_가_없으면_잇지_않는다():
    # 훅 입력에 `session_id` 가 없는 환경이 있다. 빈 문자열끼리 같다고 보면
    # 서로 다른 세션이 한 줄로 이어져 없는 인과를 만든다.
    root = wiki()
    say(root, "주석 좀 고쳐줘", session="")
    say(root, "아니, 틀렸다", session="")
    assert "prev" not in trajectory.rows(root)[1]


def test_긴_지시문_안의_이어서는_재개_요구가_아니다():
    root = wiki()
    say(root, "첫 턴")
    say(root, "이어서 진행해라. " + "그리고 다음 항목도 처리하고 보고해라. " * 6)
    assert trajectory.rows(root)[1]["prev"] == "ok"

    short = wiki()
    say(short, "첫 턴")
    say(short, "이어서 해라")
    assert trajectory.rows(short)[1]["prev"] == "재개요구"


def test_안_걸린_턴도_남는다():
    # 무엇이 실렸는지만큼 무엇이 안 실렸는지가 근거다. 빈 목록으로 남는다.
    root = wiki()
    say(root, "아무 규칙도 안 걸리는 말")
    assert trajectory.rows(root)[0]["injected"] == []


def test_발화는_잘리되_원래_길이는_남는다():
    root = wiki()
    long = "가" * (trajectory.KEEP + 200)
    say(root, long)
    row = trajectory.rows(root)[0]
    assert len(row["utterance"]) == trajectory.KEEP
    assert row["chars"] == trajectory.KEEP + 200


def test_스트림은_깃에_안_담긴다():
    root = wiki()
    say(root, "첫 턴")
    assert trajectory.FILENAME in (root / ".gitignore").read_text(encoding="utf-8")


def test_두_번_불러도_ignore_가_한_줄이다():
    root = wiki()
    say(root, "첫 턴")
    say(root, "둘째 턴")
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(trajectory.FILENAME) == 1, lines


def test_깨진_줄이_있어도_앞_줄을_찾는다():
    # 꼬리만 읽으므로 첫 줄이 잘려 들어올 수 있다. 그 조각에서 멈추면 안 된다.
    root = wiki()
    say(root, "첫 턴")
    with trajectory.path_for(root).open("a", encoding="utf-8") as handle:
        handle.write('{"at": "잘린 조\n')
    say(root, "아니, 틀렸다")
    assert trajectory.rows(root)[-1]["prev"] == "교정"


def test_쓸_수_없어도_안_죽되_조용하지도_않다():
    # 훅은 무슨 일이 있어도 세션을 멈추지 않는다 — craft/hooks-fail-open.
    # 다만 조용히 실패하면 안 도는데 도는 줄 알게 되므로 이름은 돌려준다.
    assert trajectory.record(None, "아무 말", [], 0, "s1") is None
    blocked = Path(tempfile.mkdtemp()) / "파일"
    blocked.write_text("나는 폴더가 아니다", encoding="utf-8")
    assert trajectory.record(blocked / ".wiki", "아무 말", [], 0, "s1")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
