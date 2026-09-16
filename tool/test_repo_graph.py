"""지식 그래프가 무엇을 고아로 세는지 본다."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
import repo_graph  # noqa: E402

PAGE = """---
scope: project
severity: preference
reads: {reads}
---

# 페이지

{body}
"""


def repo(docs: dict[str, str], reads: str = "[]", body: str = "") -> Path:
    """임시 저장소. `docs` 는 저장소 기준 경로 → 본문."""

    root = Path(tempfile.mkdtemp())
    (root / ".wiki").mkdir()
    for name, text in docs.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n\n{text}\n", encoding="utf-8")
    (root / ".wiki" / "page.md").write_text(
        PAGE.format(reads=reads, body=body), encoding="utf-8"
    )
    (root / ".wiki" / "corpus.json").write_text(
        json.dumps({"docs": corpus.collect(root, corpus.DEFAULT_ROOTS)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def test_아무도_안_가리키면_고아다():
    data = repo_graph.build(repo({"docs/a.md": "", "docs/b.md": ""}))
    assert data["counts"]["orphans"] == 2
    assert data["orphans"] == ["docs/a.md", "docs/b.md"]


def test_마크다운_링크를_센다():
    data = repo_graph.build(repo({"docs/a.md": "[비](b.md) 를 보라", "docs/b.md": ""}))
    assert data["orphans"] == ["docs/a.md"]


def test_백틱_경로도_센다():
    # 이 저장소들이 실제로 더 많이 쓰는 모양이다. 안 세면 고아가 부푼다.
    data = repo_graph.build(repo({"docs/a.md": "`docs/b.md` 를 읽어라", "docs/b.md": ""}))
    assert data["orphans"] == ["docs/a.md"]


def test_상대_경로가_가리킨_자리에서_풀린다():
    data = repo_graph.build(repo({
        "docs/sub/a.md": "[위](../b.md)",
        "docs/b.md": "",
    }))
    assert data["orphans"] == ["docs/sub/a.md"]


def test_없는_문서를_가리키는_것은_엣지가_아니다():
    data = repo_graph.build(repo({"docs/a.md": "[없다](docs/없다.md) `또한.md`"}))
    assert data["edges"] == []
    assert data["counts"]["orphans"] == 1


def test_바깥_링크는_안_센다():
    body = "[깃헙](https://github.com/o/r/blob/main/docs/b.md)"
    data = repo_graph.build(repo({"docs/a.md": body, "docs/b.md": ""}))
    assert data["orphans"] == ["docs/a.md", "docs/b.md"]


def test_페이지가_가리키면_고아가_아니고_축을_넘는다고_적힌다():
    data = repo_graph.build(repo({"docs/a.md": ""}, reads="[docs/a.md]"))
    assert data["orphans"] == []
    crossing = [e for e in data["edges"] if e["kind"] == "reads"]
    assert crossing and all(e["cross"] for e in crossing)
    assert data["counts"]["read"] == 1


def test_자기를_가리켜도_고아다():
    data = repo_graph.build(repo({"docs/a.md": "`docs/a.md` 자기 자신"}))
    assert data["orphans"] == ["docs/a.md"]


def test_해시_씨앗이_달라도_같은_파일이_나온다():
    """커밋되는 산출물이다. 내용이 그대로인데 순서가 흔들리면 diff 를 못 읽는다.

    실제로 집합을 그대로 돌다가 엣지 순서가 실행마다 바뀌었다. 한 프로세스에서
    두 번 불러서는 못 잡는다 — 문자열 해시는 프로세스마다 정해지므로 같은
    프로세스 안에서는 언제나 같은 순서가 나온다. 그래서 씨앗을 바꿔 따로 돌린다.
    """

    root = repo({f"docs/{n}.md": "`docs/b.md` `docs/c.md` `docs/a.md`" for n in "abc"})
    runs = [
        subprocess.run(
            [sys.executable, str(HERE / "repo_graph.py"), "--repo", str(root)],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONIOENCODING": "utf-8"},
        ) and (root / ".wiki" / "graph.json").read_text(encoding="utf-8")
        for seed in ("1", "12345")
    ]
    assert runs[0] == runs[1]


def test_목록이_없으면_아무것도_안_만든다():
    root = Path(tempfile.mkdtemp())
    (root / ".wiki").mkdir()
    assert repo_graph.build(root) is None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
