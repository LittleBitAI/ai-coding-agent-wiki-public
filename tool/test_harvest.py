"""수확이 줄끝에 흔들리지 않고, 있는 기록을 덮지 않는다."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8")

from harvest import record, triggers_for  # noqa: E402 -- 위의 reconfigure 가 먼저 돌아야 한다

BODY = """## 왜 셀을 지우면 안 됐나

`defer` 대조군이 혼합 문서입니다.

## 무엇을 바꿨나

`_replay` 가 `defer` 대조군만 다르게 비교합니다.
"""

PR = {"number": 95, "mergedAt": "2026-09-06T00:00:00Z", "title": "제목",
      "headRefName": "feat/branch"}


def _record(body: str) -> str:
    return record({**PR, "body": body})[1]


def test_CRLF_본문도_LF_본문과_같은_기록을_낸다() -> None:
    lf = _record(BODY)
    crlf = _record(BODY.replace("\n", "\r\n"))
    assert lf == crlf, "줄끝만 다른 같은 본문이 다른 기록을 냈다"


def test_이유가_있는_본문은_없다고_적히지_않는다() -> None:
    for body in (BODY, BODY.replace("\n", "\r\n")):
        assert "이 결정의 근거는 기록되지 않았다" not in _record(body)
        assert "혼합 문서" in _record(body)


def test_이유가_정말_없으면_없다고_적는다() -> None:
    """반대쪽 절반. 없는 것을 지어내지 않는지도 같이 못박는다."""
    assert "이 결정의 근거는 기록되지 않았다" in _record("한 문단뿐인 본문.")


def _what(body: str) -> str:
    line = next(ln for ln in _record(body).splitlines() if ln.startswith("무엇."))
    return line[len("무엇."):].strip()


def test_무엇에_마크다운_제목이_그대로_들어가지_않는다() -> None:
    """또 실제로 난 사고다. 폴백이 첫 `\\n\\n` 덩어리를 무엇으로 쓰는데
    이 저장소들의 PR 본문은 거의 다 마크다운 제목으로 시작한다. 그래서
    `무엇. ## 결론` 이 그대로 기록이 됐다 -- 2026-09-10 의 131~135 전부.

    없는 것을 없다고 적는 것과 마찬가지로, 제목을 내용이라고 적는 것도
    다음 세션이 읽고 믿는다."""
    for body in (BODY, BODY.replace("\n", "\r\n")):
        what = _what(body)
        assert not what.startswith("#"), f"제목이 그대로 들어갔다: {what!r}"
        assert "대조군" in what, f"제목 뒤의 산문이 안 왔다: {what!r}"


def test_제목과_본문_사이에_빈_줄이_없어도_산문을_찾는다() -> None:
    """제목 줄만 걷어내야 한다. 덩어리째 버리면 이 모양에서 본문까지 잃는다."""
    assert _what("## 결론\n붙어 있는 본문입니다.\n\n둘째 문단.") == "붙어 있는 본문입니다."


def test_제목뿐인_본문은_요약이_없다고_적는다() -> None:
    """걷어낸 뒤 남는 산문이 없으면 지어내지 않는다."""
    assert "PR 본문에 요약 절이 없다" in _record("## 제목뿐\n\n### 또 제목뿐")


def test_짧은_ascii_표지가_낱말_안에서_걸리지_않는다() -> None:
    """`ci` 가 `de-ci-sion` 에 걸려 chore 배치 하나가 infra 로 분류됐다.

    도메인이 붙으면 트리거도 같이 붙고, `inject.py` 는 트리거가 있으면 규칙처럼
    주입한다. 그래서 오분류는 조용하지 않다 -- 상관없는 세션마다 그 기록이 뜬다.
    실제로 2026-09-10 의 131 이 그렇게 나왔고, 그 PR 의 제목 자체가
    "infra 오탐 두 건을 고칩니다" 였다. 그때는 기록을 손으로 내렸고 표지는 그대로였다."""
    for branch, title in (("chore/decision-records-126-130", "결정 기록을 캡니다"),
                          ("fix/early-return", "이른 반환을 고칩니다"),
                          ("feat/framework-upgrade", "의존성을 올립니다")):
        domain, triggers = triggers_for(title, branch)
        assert domain == "", f"{branch} 가 {domain!r} 로 걸렸다"
        assert triggers == []


def test_한글_표지는_아직_합성어_안에서도_걸린다() -> None:
    """고친 것은 ASCII 쪽뿐이다. `프레임` 은 `프레임워크` 안에서 여전히 걸린다.

    한글에는 낱말 경계가 없어 같은 방법을 못 쓴다. 조사가 붙는 언어라 오른쪽
    경계를 막으면 `게이트를` 같은 진짜 양성이 통째로 죽는다. 여기 적어 두는
    이유는, 다음 세션이 오탐을 보고 이 함수가 이미 다 막는다고 믿지 않게
    하려는 것이다."""
    assert triggers_for("프레임워크를 올립니다", "chore/deps")[0] == "vision"


def test_낱말로_선_표지는_그대로_걸린다() -> None:
    """엄격해지느라 진짜 양성을 놓치면 안 된다."""
    assert triggers_for("CI 를 붙입니다", "feat/ci-pipeline")[0] == "infra"
    assert triggers_for("프레임 동기화", "feat/frame-sync")[0] == "vision"
    assert triggers_for("턴 조립", "feat/turn-assembly")[0] == "api"
    assert triggers_for("스키마를 올립니다", "chore/migration")[0] == "infra"
    assert triggers_for("런처를 고칩니다", "fix/launcher")[0] == "infra"


def test_손으로_쓴_기록은_번호가_이름에만_있어도_보인다() -> None:
    """`pr:` 줄만 보면 손으로 쓴 전문이 안 보이고, 캔 기록이 그 자리를 덮는다.

    2026-09-17 에 013·015·016 이 그렇게 통째로 날아갔다. 파일 이름의 번호도 읽는다.
    """
    import sync

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / ".wiki" / "decisions"
        out.mkdir(parents=True)
        (out / "2026-09-17-013-docs-run-archive.md").write_text(
            '---\nscope: project\ntitle: "손으로 쓴 전문"\n---\n', encoding="utf-8")
        (out / "2026-09-17-012-feat-x.md").write_text("---\npr: 12\n---\n", encoding="utf-8")
        (out / "2026-09-18-run-colab-1789.md").write_text("---\nscope: project\n---\n",
                                                          encoding="utf-8")
        assert sync.recorded(Path(tmp)) == {12, 13}, "이름의 번호와 pr: 줄을 둘 다 읽어야 한다"


def test_있는_결정_파일은_절대_안_덮는다() -> None:
    """번호 판정이 또 틀려도 여기서 멈춘다. 사람이 쓴 전문이 그 자리에 있을 수 있다."""
    import sync

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        out = repo / ".wiki" / "decisions"
        out.mkdir(parents=True)
        kept = out / "2026-09-17-013-docs-run-archive.md"
        kept.write_text("사람이 쓴 전문\n", encoding="utf-8")
        pr = {"number": 13, "title": "docs: archive", "body": "본문",
              "mergedAt": "2026-09-17T00:00:00Z", "headRefName": "docs/run-archive"}
        with patch.object(sync.harvest, "prs", return_value=[pr]), \
                patch.object(sync, "recorded", return_value=set()):
            written = sync.new_decisions(repo, 10)
        assert written == [], "있는 파일을 덮으려 했다"
        assert kept.read_text(encoding="utf-8") == "사람이 쓴 전문\n"


if __name__ == "__main__":
    for name, case in sorted(globals().items()):
        if name.startswith("test_"):
            case()
            print(f"ok  {name}")
    print("\n줄끝이 달라도 기록은 같다. 있는 이유를 없다고 적지 않는다.")
