"""정책 그래프가 아티팩트로 온전한지 본다."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from graph import build, load_pages  # noqa: E402

PAGE = """---
scope: craft
severity: contract
triggers: ["ㄱ"]
sources: []
links: []
---

# 제목

규칙. 한 줄.
"""


def test_왕복해도_한_글자도_안_바뀐다():
    # 직렬화가 안 되는 값과, 왕복하며 타입이 바뀌는 값을 둘 다 잡는다. 읽는 쪽이
    # 이 파일만 보므로, 여기서 잃은 것은 화면에서 영영 못 본다.
    data = build(load_pages([]), [])
    assert json.loads(json.dumps(data, ensure_ascii=False)) == data


def test_아티팩트가_축을_선언한다():
    root = Path(tempfile.mkdtemp())
    (root / "craft").mkdir()
    (root / "craft" / "a.md").write_text(PAGE, encoding="utf-8")
    artifact = root / "graph.json"

    done = subprocess.run(
        [sys.executable, str(HERE / "graph.py"), "--json", str(artifact)],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "WIKI_ROOT": str(root), "PYTHONIOENCODING": "utf-8"},
    )
    assert done.returncode == 0, done.stderr

    assert b"\r\n" not in artifact.read_bytes()
    assert not artifact.read_bytes().startswith(b"\xef\xbb\xbf")
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data["ns"] == "rule"
    assert [n["id"] for n in data["nodes"]] == ["craft/a"]


def test_붙은_저장소를_스스로_찾는다():
    # 이름을 손으로 들면 저장소가 늘 때마다 여기를 고쳐야 하고, 그것은 곧 안 고치는 것이다.
    # 어댑터가 없거나 저장소가 아닌 폴더는 빼고, 워크스페이스 설정이 깨져도 그래프는 나와야 한다.
    import graph

    workspace = Path(tempfile.mkdtemp())
    wiki = workspace / "위키"
    for name, wired in (("붙은 저장소", True), ("안 붙은 것", False), ("위키", True)):
        repo = workspace / name
        (repo / ".git").mkdir(parents=True)
        if wired:
            (repo / ".wiki").mkdir()
            (repo / ".wiki/adapter.toml").write_text("agents=[]\n", encoding="utf-8")
    (workspace / "저장소_아님").mkdir()

    with patch.object(graph, "WIKI", wiki), patch.object(graph, "HERE", wiki / "tool"):
        assert graph.connected() == [workspace / "붙은 저장소", wiki]
        (wiki / ".chat-local.json").write_text('{"workspace": "."}', encoding="utf-8")
        assert graph.connected() == []          # 위키 아래에는 저장소가 없다
        (wiki / ".chat-local.json").write_text("깨진 JSON", encoding="utf-8")
        assert graph.connected() == [workspace / "붙은 저장소", wiki]
    # WIKI_ROOT 로 다른 허브를 가리키면 그 상위 폴더를 뒤지지 않는다.
    with patch.object(graph, "WIKI", wiki):
        assert graph.connected() == []


def test_그리는_코드가_여기_없다():
    # 뷰는 소비자다. 이 도구가 화면을 만들면 같은 그래프를 그리는 코드가 두 벌이
    # 되고, 두 벌은 어긋난다. 그래서 여기 HTML 이 한 글자도 없어야 한다.
    source = (HERE / "graph.py").read_text(encoding="utf-8")
    assert "<svg" not in source and "<div" not in source
    assert not (HERE / "graph_view.py").exists()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
