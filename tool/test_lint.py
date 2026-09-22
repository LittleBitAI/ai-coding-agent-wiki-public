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

    # Citing Korean is not writing Korean, in every quote a person types.
    #
    # The first version of check 9 knew backticks and double quotes, so a
    # comment citing a marker with single quotes was blocked by the gate. A
    # check that stops correct work is the one that gets switched off, so the
    # false-positive side gets asserted as hard as the true-positive side.
    tick = chr(96)
    cited = {
        "backticks": f"# The marker {tick}왜.{tick} is parsed.",
        "double quotes": '# The marker "왜." is parsed.',
        "single quotes": "# The marker '왜.' is parsed.",
        "curly double": "# The marker “왜.” is parsed.",
        "curly single": "# The marker ‘왜.’ is parsed.",
        "a possessive beside a citation": "# The page's rule cites '왜.' and stops.",
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for n, (label, source) in enumerate(cited.items()):
            _clean_tool(root, f"cited{n}.py", source + "\n")
        quiet = korean_prose(root)
    print(f"  {'통과 ' if not quiet else '실패 '} 인용은 안 잡는다            → {quiet or '없음'}")
    if quiet:
        failed.append("인용 오탐")

    # And a quote mark inside a word is not a quote. Read as a pair these
    # swallow the Korean between them, which is a miss — the failure the
    # check was built to end. A digit and an underscore are inside a word
    # too: a first version tested `[A-Za-z]` and let `6'` and `foo_'` open a
    # span.
    masked = {
        "an apostrophe": "# It doesn't parse 왜. and won't either.",
        "a prime after a digit": "# The 6' case parses 왜. unlike the 5' case.",
        "an underscore before it": "# foo_' masks 왜. until bar_' here.",
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for n, (label, source) in enumerate(masked.items()):
            _clean_tool(root, f"masked{n}.py", source + "\n")
        caught = korean_prose(root)
    ok = len(caught) == len(masked)
    print(f"  {'통과 ' if ok else '실패 '} 낱말 안의 따옴표는 인용이 아니다 → {len(caught)}/{len(masked)}")
    if not ok:
        failed.append("낱말 안 따옴표 미탐")

    # A citation that spans a line break. The unit is one docstring, not one
    # line — splitting first meant such a quote could never close, and a
    # docstring quoting across two lines was blocked as Korean prose.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _clean_tool(
            root,
            "spanning.py",
            'def f():\n    """The parser cites “첫째\n    둘째” as one example."""\n',
        )
        spanning = korean_prose(root)
    print(f"  {'통과 ' if not spanning else '실패 '} 줄 넘는 인용도 인용이다     → {spanning or '없음'}")
    if spanning:
        failed.append("줄 넘는 인용 오탐")

    print()
    if failed:
        print(f"검사 {len(failed)}건이 심은 결함을 못 잡았다: {failed}")
        return 1
    print("검사가 전부 자기 결함에서만 빨개진다.")
    return 0


if __name__ == "__main__":
    shutil.rmtree  # noqa: B018  (tempfile does the cleaning up)
    raise SystemExit(main())
