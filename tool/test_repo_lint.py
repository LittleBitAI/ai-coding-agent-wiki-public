"""repo_lint 가 실제로 빨개지는지 증명한다."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repo_lint  # noqa: E402

PAGE = """---
scope: {scope}
severity: {severity}
triggers: {triggers}
reads: {reads}
---

# 프로젝트 페이지

규칙. 한 줄.
"""


def repo(docs: list[str] | None = None, listed: list[str] | None = None,
         severity: str = "preference", triggers: str = "[]",
         reads: str = "[]", scope: str = "project") -> Path:
    """임시 저장소 하나. `.wiki/` 와 `docs/` 를 원하는 모양으로 세운다."""

    root = Path(tempfile.mkdtemp())
    (root / ".wiki").mkdir()
    (root / "docs").mkdir()
    for name in docs or []:
        (root / "docs" / name).write_text("# 문서\n", encoding="utf-8")

    (root / ".wiki" / "page.md").write_text(
        PAGE.format(scope=scope, severity=severity, triggers=triggers, reads=reads),
        encoding="utf-8",
    )
    index = root / ".wiki" / "corpus.json"
    index.write_text(
        json.dumps({"docs": [{"path": f"docs/{n}"} for n in (listed or docs or [])]}),
        encoding="utf-8",
    )
    # 목록을 문서보다 나중에 만든 것으로 둔다. 그래야 "뒤처졌다" 가 기본이 아니다.
    later = time.time() + 60
    os.utime(index, (later, later))
    return root


def kinds(root: Path) -> set[str]:
    return {kind for kind, _message in repo_lint.check(root)}


def test_깨끗하면_아무_말도_안_한다():
    assert kinds(repo(docs=["a.md", "b.md"])) == set()


def test_목록이_없는_문서를_가리키면_짚는다():
    root = repo(docs=["a.md"], listed=["a.md", "사라진.md"])
    assert "낡은 목록" in kinds(root)


def test_문서가_목록보다_나중에_고쳐지면_짚는다():
    root = repo(docs=[f"{n}.md" for n in range(5)])
    later = time.time() + 600
    for path in (root / "docs").glob("*.md"):
        os.utime(path, (later, later))
    assert "낡은 목록" in kinds(root)


def test_조금_뒤처진_것은_안_짚는다():
    # 문서 하나 고칠 때마다 뜨면 매 턴 뜨고, 매 턴 뜨는 경고는 안 읽힌다.
    root = repo(docs=[f"{n}.md" for n in range(5)])
    later = time.time() + 600
    for path in sorted((root / "docs").glob("*.md"))[:2]:
        os.utime(path, (later, later))
    assert "낡은 목록" not in kinds(root)


def test_reads_가_없는_파일을_가리키면_짚는다():
    assert "끊어진 포인터" in kinds(repo(docs=["a.md"], reads="[docs/없다.md]"))


def test_reads_가_실재하면_안_짚는다():
    assert "끊어진 포인터" not in kinds(repo(docs=["a.md"], reads="[docs/a.md]"))


def test_주입_등급인데_트리거가_없으면_짚는다():
    assert "안 실리는 규칙" in kinds(repo(docs=["a.md"], severity="contract"))


def test_취향_등급은_트리거가_없어도_된다():
    # `preference` 는 주입 대상이 아니다. 트리거를 요구하면 없는 결함을 만든다.
    assert "안 실리는 규칙" not in kinds(repo(docs=["a.md"], severity="preference"))


def test_허브_범위_페이지가_저장소에_있으면_짚는다():
    # 두 곳 다 "위키" 라고 불려서 한 세션이 저장소를 안 가리는 규칙을 여기 적었다.
    assert "범위가 어긋난 페이지" in kinds(repo(docs=["a.md"], scope="craft"))
    assert "범위가 어긋난 페이지" in kinds(repo(docs=["a.md"], scope="operator"))


def test_저장소_범위는_저장소에_있어도_된다():
    # 게이트 명령·런처·포트는 저장소마다 다르므로 여기가 제자리다.
    assert "범위가 어긋난 페이지" not in kinds(repo(docs=["a.md"], scope="project"))


def test_허브의_발견은_섞이지_않는다():
    # 이것이 가른 이유다. 대상 저장소의 검진에 허브의 슬롯 갈림이 뜨면, 이
    # 세션에서 할 수 있는 일이 없는 줄이 매번 뜬다.
    found = {kind for kind, _m in repo_lint.check(repo(docs=["a.md"]))}
    assert not found & {"모순(슬롯)", "고아 페이지", "끊어진 링크", "끊긴 줄바꿈"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
