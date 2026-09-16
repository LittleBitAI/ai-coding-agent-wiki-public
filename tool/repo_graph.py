"""repo_graph — 붙은 저장소의 지식이 서로 무엇을 가리키는가."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
from wikilib import front_matter, project_pages  # noqa: E402

NS = "repo"

# 두 가지 모양으로 문서를 가리킨다. 마크다운 링크와, 이 저장소들이 실제로 더
# 많이 쓰는 백틱 경로다 — 지시문에도 문서에도 `docs/development/TDD.md` 처럼
# 적힌다. 뒤엣것을 안 세면 고아 수가 실제보다 크게 나온다.
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s#]+\.md)[^)]*\)")
BARE_PATH = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.md)`")


def targets(text: str) -> set[str]:
    return set(MD_LINK.findall(text)) | set(BARE_PATH.findall(text))


def resolve(raw: str, source: str, known: set[str]) -> str | None:
    """가리킨 경로를 저장소 기준 경로로. 못 찾으면 None.

    상대 경로가 먼저다. `../architecture/x.md` 는 가리킨 문서의 자리에서만
    뜻이 통하고, 저장소 뿌리에서 풀면 엉뚱한 파일에 붙거나 아무 데도 안 붙는다.

    파일시스템은 안 건드린다. 실재 여부는 `known` 이 이미 답하고, `Path.resolve`
    는 현재 디렉터리를 기준으로 삼아 어디서 돌리느냐에 답이 매달리게 만든다.
    """

    here = posixpath.dirname(source)
    for candidate in (posixpath.join(here, raw), raw):
        name = posixpath.normpath(candidate).lstrip("./")
        if name in known:
            return name
    return None


def decisions_of(repo: Path) -> list[dict]:
    found = []
    for path in sorted((repo / ".wiki" / "decisions").glob("*.md")):
        meta, _body = front_matter(path.read_text(encoding="utf-8"))
        found.append({
            "id": f".wiki/decisions/{path.stem}",
            "severity": str(meta.get("severity") or ""),
            "injectable": bool(meta.get("triggers")),
        })
    return found


def build(repo: Path) -> dict | None:
    """이 저장소의 지식 엣지. `corpus.json` 이 없으면 아무것도 안 만든다."""

    index = corpus.load(repo)
    if not index:
        return None

    docs = {doc["path"]: doc for doc in index.get("docs") or []}
    known = set(docs)
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for path in sorted(known):
        try:
            text = (repo / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 정렬한다. 집합은 실행마다 순서가 달라서, 내용이 그대로인데도 커밋되는
        # 파일이 매번 흔들린다. 흔들리는 산출물은 diff 를 못 읽게 만든다.
        for raw in sorted(targets(text)):
            hit = resolve(raw, path, known)
            if hit and hit != path and (path, hit) not in seen:
                seen.add((path, hit))
                edges.append({"a": path, "b": hit, "kind": "link"})

    pages = project_pages(repo)
    for name, (meta, body, _path) in pages.items():
        pointed = {str(t) for t in (meta.get("reads") or [])} | targets(body)
        for raw in sorted(pointed):
            hit = resolve(raw, name, known)
            if hit:
                edges.append({"a": name, "b": hit, "kind": "reads", "cross": True})

    inbound = {edge["b"] for edge in edges}
    read = {edge["b"] for edge in edges if edge["kind"] == "reads"}
    orphans = sorted(known - inbound)
    records = decisions_of(repo)

    return {
        "ns": NS,
        "repo": repo.name,
        "nodes_from": ".wiki/corpus.json",
        "edges": edges,
        "orphans": orphans,
        "counts": {
            "docs": len(known),
            "linked": len(inbound - read),
            "read": len(read),
            "orphans": len(orphans),
            "pages": len(pages),
            "decisions": len(records),
            "injectable_decisions": sum(1 for d in records if d["injectable"]),
        },
    }


def write(repo: Path) -> dict | None:
    data = build(repo)
    if data is None:
        return None
    (repo / ".wiki" / "graph.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return data


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="붙은 저장소의 지식 그래프를 만든다")
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    data = write(repo)
    if data is None:
        print("`.wiki/corpus.json` 이 없다. `tool/corpus.py --write` 를 먼저 돌려라.")
        return 2

    counts = data["counts"]
    print(f"# repo_graph — {data['repo']}\n")
    print("| | 수 |")
    print("| --- | ---: |")
    for label, key in (
        ("문서", "docs"),
        ("  다른 문서가 가리킴", "linked"),
        ("  페이지가 가리킴", "read"),
        ("  **아무도 안 가리킴**", "orphans"),
        ("프로젝트 페이지", "pages"),
        ("결정 기록", "decisions"),
        ("  주입 대상", "injectable_decisions"),
    ):
        print(f"| {label} | {counts[key]:,} |")
    print(f"\n엣지 {len(data['edges']):,}개. `.wiki/graph.json` 에 썼다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
