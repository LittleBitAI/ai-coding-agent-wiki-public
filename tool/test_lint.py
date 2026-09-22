"""Prove each of `lint`'s checks actually goes red."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lint import check, korean_prose  # noqa: E402

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
    """Write a table of pages as a throwaway wiki, grounds files and all."""

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
    """Plant one tool in the throwaway wiki. The encoding check looks in `tool/`."""
    (root / "tool").mkdir(parents=True, exist_ok=True)
    (root / "tool" / name).write_text(source, encoding="utf-8")


FIXED = 'import sys\nsys.stdout.reconfigure(encoding="utf-8")\n'


def _clean_tool(root: Path, name: str, source: str) -> None:
    """Plant a tool with its encoding already pinned.

    One defect turning two checks red leaves no way to tell which check
    caught it.
    """

    _tool(root, name, FIXED + source)


def kinds(root: Path) -> set[str]:
    _loaded, _declared, findings = check(wiki=root, adapters=root / "none")
    return {kind for kind, _msg in findings}


def run(label: str, mutate, expect: str) -> bool:
    """Plant a defect and watch that check go red."""

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
    # Down a pipe the default here is cp949. The encoding is not left to the
    # environment.
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
            # What the first version missed. The finding message contained
            # that name as the way to fix it, so `lint.py` itself was judged
            # "already fixed". This line is entirely about whether the check
            # counts the call or the name.
            "이름만 문자열에 있고 호출은 없다",
            lambda p, r: _tool(
                r,
                "sneaky.py",
                'print("고치려면 sys.stdout.reconfigure(encoding=\'utf-8\') 를 써라")\n',
            ),
            "인코딩 미고정",
        ),
        (
            # The judgement moved from a Korean adnominal ending to a span cut
            # in half. A `the` at the end of a line is ordinary English
            # typesetting, and that version flagged 437 of 1,515 pairs — 29%
            # is not a check, it is noise that gets switched off. The samples
            # had to move with it.
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
            # Page prose is read by a different path — front matter skipped,
            # tables and code fences filtered out. If that path quietly reads
            # nothing the check stays green, and that green looks like
            # evidence the check ran.
            "페이지 산문에서 숫자와 단위가 갈린다",
            lambda p, r: p["operator/a"].update(
                extra="\nMeasuring the corpus gave a median across the 21\npages already here."
            ),
            "끊긴 줄바꿈",
        ),
        (
            # A comment written in Korean. This check exists because the
            # completion claim was asserted from a regex over `#` lines that
            # counted no docstring at all.
            "주석이 한국어로 적혀 있다",
            lambda p, r: _clean_tool(r, "korean.py", "# 이 주석은 한국어 산문이다.\n"),
            "주석이 한국어다",
        ),
        (
            # The same, in a docstring rather than a comment. A regex on `#`
            # sees nothing here, which is exactly how 104 lines stayed under a
            # green gate.
            "docstring 이 한국어로 적혀 있다",
            lambda p, r: _clean_tool(
                r, "korean_doc.py", 'def f():\n    """이 설명은 한국어다."""\n',
            ),
            "주석이 한국어다",
        ),
    ]

    print(f"\n결함을 하나씩 심는다 ({len(checks)}건)\n")
    failed = [label for label, mutate, expect in checks if not run(label, mutate, expect)]

    # Does declaring it let it pass — the heart of how contradictions work
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

    # Citing Korean is not writing Korean, and the backtick is what says so.
    # A check that stops correct work is the one that gets switched off, so
    # the false-positive side is asserted as hard as the true-positive side.
    tick = chr(96)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _clean_tool(root, "cited.py", f"# The marker {tick}왜.{tick} is parsed.\n")
        _clean_tool(
            root,
            "cited_doc.py",
            f'def f():\n    """English first.\n\n    It cites {tick}왜.{tick} and stops.\n    """\n',
        )
        quiet = korean_prose(root)
    print(f"  {'통과 ' if not quiet else '실패 '} 백틱 인용은 안 잡는다        → {quiet or '없음'}")
    if quiet:
        failed.append("인용 오탐")

    # A quotation mark is punctuation, not a marker, so pairing two of them
    # is a guess. Three rounds added members to a set of quote characters and
    # the fourth found the guess going wrong the expensive way: an unclosed
    # `"` pairs with a later one and the Korean between the two disappears
    # from the gate. Every one of these has to be caught.
    unmarked = {
        "double quotes": '# The marker "왜." is parsed.',
        "single quotes": "# The marker '왜.' is parsed.",
        "an apostrophe": "# It doesn't parse 왜. and won't either.",
        "an unclosed quote": (
            'def f():\n'
            '    """The output starts with " but never closes it.\n'
            '    한국어 산문이다.\n'
            '    Later it names "done" as a separate token.\n'
            '    """\n'
        ),
        "a span cut by a line wrap": (
            f"# Fitting the width cut the span: {tick}왜.\n"
            f"# 그리고 다음 줄{tick} was one span.\n"
        ),
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for n, (label, source) in enumerate(unmarked.items()):
            _clean_tool(root, f"unmarked{n}.py", source)
        caught = {at.split(":")[0] for at, _line in korean_prose(root)}
    ok = len(caught) == len(unmarked)
    print(f"  {'통과 ' if ok else '실패 '} 표지 없는 한국어는 다 잡는다 → {len(caught)}/{len(unmarked)}")
    if not ok:
        failed.append("표지 없는 한국어 미탐")

    # The line number names the line the Korean is on, not the `def` above
    # the docstring. Preserving the line structure while masking is what this
    # is for, and it was preserved for two rounds without being used.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _clean_tool(root, "where.py", 'def f():\n    """English first.\n    한국어 산문이다.\n    """\n')
        where = korean_prose(root)
    ok = where == [("tool/where.py:5", "한국어 산문이다.")]
    print(f"  {'통과 ' if ok else '실패 '} 발견이 그 줄을 가리킨다     → {where or '없음'}")
    if not ok:
        failed.append("발견 줄 번호 어긋남")

    print()
    if failed:
        print(f"검사 {len(failed)}건이 심은 결함을 못 잡았다: {failed}")
        return 1
    print("검사가 전부 자기 결함에서만 빨개진다.")
    return 0


if __name__ == "__main__":
    shutil.rmtree  # noqa: B018  (tempfile does the cleaning up)
    raise SystemExit(main())
