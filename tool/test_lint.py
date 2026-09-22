"""lint 의 검사가 실제로 빨개지는지 증명한다."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lint import check  # noqa: E402

PAGE = """---
scope: {scope}
severity: {severity}
triggers: {triggers}
slots: []
sources: {sources}
links: {links}
---

# {name}

규칙. 한 줄.
{extra}
"""


def build(root: Path, pages: dict[str, dict]) -> None:
    """페이지 표를 임시 위키로 쓴다. 근거 파일도 같이 만든다."""

    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "raw" / "c.jsonl").write_text("{}\n", encoding="utf-8")
    for full, spec in pages.items():
        scope, stem = full.split("/", 1)
        (root / scope).mkdir(parents=True, exist_ok=True)
        (root / scope / f"{stem}.md").write_text(
            PAGE.format(
                scope=scope,
                name=stem,
                severity=spec.get("severity", "contract"),
                triggers=spec.get("triggers", '["ㄱ"]'),
                sources=spec.get("sources", "[raw/c.jsonl]"),
                links=spec.get("links", "[]"),
                extra=spec.get("extra", ""),
            ),
            encoding="utf-8",
        )


CLEAN = {
    "operator/a": {"triggers": '["가"]', "links": "[b]"},
    "craft/b": {"triggers": '["나"]', "links": "[a]"},
}


def _tool(root: Path, name: str, source: str) -> None:
    """임시 위키에 도구 하나를 심는다. 인코딩 검사가 보는 곳은 `tool/` 이다."""
    (root / "tool").mkdir(parents=True, exist_ok=True)
    (root / "tool" / name).write_text(source, encoding="utf-8")


FIXED = 'import sys\nsys.stdout.reconfigure(encoding="utf-8")\n'


def _clean_tool(root: Path, name: str, source: str) -> None:
    """인코딩만 고정해 둔 도구를 심는다.

    한 결함이 두 검사를 빨갛게 하면 어느 검사가 잡은 것인지 못 가른다.
    """

    _tool(root, name, FIXED + source)


def kinds(root: Path) -> set[str]:
    _loaded, _declared, findings = check(wiki=root, adapters=root / "none")
    return {kind for kind, _msg in findings}


def run(label: str, mutate, expect: str) -> bool:
    """결함을 심고 그 검사가 빨개지는지 본다."""

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pages = {name: dict(spec) for name, spec in CLEAN.items()}
        mutate(pages, root)
        build(root, pages)
        found = kinds(root)
    ok = expect in found
    print(f"  {'RED  ' if ok else '초록 '} {label:<28} → {sorted(found) or '없음'}")
    return ok


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build(root, CLEAN)
        base = kinds(root)
    print(f"기준 (결함 없음) → {sorted(base) or '없음'}")
    if base:
        print("기준이 이미 빨갛다. 아래 결과는 못 믿는다.")
        return 1

    checks = [
        (
            "끊어진 링크",
            lambda p, r: p["operator/a"].update(links="[nowhere]"),
            "끊어진 링크",
        ),
        (
            "고아 페이지",
            lambda p, r: p["operator/a"].update(links="[]"),
            "고아 페이지",
        ),
        (
            "근거가 사라짐",
            lambda p, r: p["operator/a"].update(sources="[raw/gone.jsonl]"),
            "낡은 서술",
        ),
        (
            "landmine 인데 근거 없음",
            lambda p, r: p["operator/a"].update(severity="landmine", sources="[]"),
            "근거 없는 landmine",
        ),
        (
            "contract 인데 트리거 없음",
            lambda p, r: p["operator/a"].update(triggers="[]"),
            "낡은 서술",
        ),
        (
            "트리거 공유하는데 링크 없음",
            lambda p, r: (
                p["operator/a"].update(triggers='["같은말"]', links="[]"),
                p["craft/b"].update(triggers='["같은말"]', links="[]"),
            ),
            "빠진 연결",
        ),
        (
            "도구가 인코딩을 안 고정한다",
            lambda p, r: _tool(r, "talky.py", 'print("한글")\n'),
            "인코딩 미고정",
        ),
        (
            # 첫 판이 놓친 자리. 발견 메시지가 고치는 방법으로 그 이름을 담고
            # 있어서, `lint.py` 자신이 "고쳤다" 로 판정됐다. 이름이 아니라
            # 호출문을 세는지 보는 것이 이 줄의 전부다.
            "이름만 문자열에 있고 호출은 없다",
            lambda p, r: _tool(
                r,
                "sneaky.py",
                'print("고치려면 sys.stdout.reconfigure(encoding=\'utf-8\') 를 써라")\n',
            ),
            "인코딩 미고정",
        ),
        (
            # 판정이 한국어 관형형에서 잘린 스팬으로 바뀌었다. 영어에서 줄 끝의
            # `the` 는 정상 조판이라 그 판이 1,515쌍 중 437건을 짚었다 — 29%는
            # 검사가 아니라 끄게 되는 소음이다. 표본도 같이 바뀌어야 한다.
            "주석의 코드 스팬이 줄바꿈에 잘린다",
            lambda p, r: _clean_tool(
                r,
                "wrapped.py",
                "# Fitting the width cut the span: `subprocess.run(cmd,\n"
                "# check=True)` is one span and now it is two.\n",
            ),
            "끊긴 줄바꿈",
        ),
        (
            # 페이지 산문은 다른 경로로 읽는다 — front matter 를 건너뛰고 표와
            # 코드 울타리를 거른다. 그 경로가 조용히 아무것도 안 읽으면 검사는
            # 초록인 채로 남고, 그 초록이 검사가 도는 증거처럼 보인다.
            "페이지 산문에서 숫자와 단위가 갈린다",
            lambda p, r: p["operator/a"].update(
                extra="\nMeasuring the corpus gave a median across the 21\npages already here."
            ),
            "끊긴 줄바꿈",
        ),
    ]

    print(f"\n결함을 하나씩 심는다 ({len(checks)}건)\n")
    failed = [label for label, mutate, expect in checks if not run(label, mutate, expect)]

    # 선언하면 지나가는가 — 모순 처리의 핵심이다
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pages = {name: dict(spec) for name, spec in CLEAN.items()}
        pages["operator/a"].update(triggers='["같은말"]', links="[]")
        pages["craft/b"].update(triggers='["같은말"]', links="[]")
        build(root, pages)
        text = (root / "operator" / "a.md").read_text(encoding="utf-8")
        (root / "operator" / "a.md").write_text(
            text.replace("links: []", "links: []\nconflicts_with: [craft/b]"),
            encoding="utf-8",
        )
        after = kinds(root)
    passed = "빠진 연결" not in after
    print(f"\n  {'통과 ' if passed else '실패 '} 선언하면 지나가는가        → {sorted(after) or '없음'}")
    if not passed:
        failed.append("선언 무시")

    print()
    if failed:
        print(f"검사 {len(failed)}건이 심은 결함을 못 잡았다: {failed}")
        return 1
    print("검사가 전부 자기 결함에서만 빨개진다.")
    return 0


if __name__ == "__main__":
    shutil.rmtree  # noqa: B018  (tempfile 이 정리한다)
    raise SystemExit(main())
