"""corpus — 대상 저장소의 문서 목록을 만든다. 고르는 것은 에이전트가 한다."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEAD = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.M)
SKIP_DIRS = {"node_modules", ".git", "artifacts", "__pycache__"}

# 여기에는 상한이 없다. 목록은 원시 자료이고 원시 자료는 자란다.
# 무엇을 얼마나 실을지 다듬는 것은 훅의 일이다. 세는 쪽은 있는 것을 다 센다.


def summarize(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    heads = HEAD.findall(text)
    title = next((h[1] for h in heads if h[0] == "#"), path.stem)
    body = HEAD.sub("", text)
    first = next(
        (" ".join(p.split()) for p in body.split("\n\n") if len(p.strip()) > 40), ""
    )
    return {
        "path": path.relative_to(root).as_posix(),
        "title": " ".join(title.split()),
        "heads": [" ".join(h[1].split()) for h in heads[1:14]],
        "lead": first[:220],
        "chars": len(text),
    }


DEFAULT_ROOTS = ["docs", "."]


def walk(root: Path, roots: list[str]) -> list[Path]:
    """문서 파일들. `.` 은 저장소 뿌리의 `*.md` 만이고 하위로는 안 내려간다.

    뿌리에 흩어진 문서를 오래 못 봤다. 이 저장소의 목록이 README.md 한 장이었고
    SCHEMA·ENFORCEMENT·MAINTENANCE·index 가 전부 빠져 있었다 — 위키가 자기
    문서를 자기 목록에서 못 보고 있었다.

    같은 파일이 두 root 에 걸릴 수 있으므로 순서를 지키며 중복을 지운다.
    """

    found: list[Path] = []
    for name in roots:
        if name == ".":
            found += sorted(root.glob("*.md"))
            continue
        base = root / name
        if base.is_file() and base.suffix == ".md":
            found.append(base)
        elif base.is_dir():
            found += [
                path for path in sorted(base.rglob("*.md"))
                if not SKIP_DIRS & set(path.parts)
            ]
    return list(dict.fromkeys(found))


def collect(root: Path, roots: list[str]) -> list[dict]:
    return [summarize(path, root) for path in walk(root, roots)]


def catalog(docs: list[dict]) -> str:
    """디렉터리로 묶은 목록. 세션 시작에 이대로 실린다.

    경로와 제목뿐이다. 8,972자로 109개가 다 들어간다 — 본문을 조금이라도
    넣으면 그 배가 되고, 목록의 값어치는 "무엇이 있는가" 이지 "무엇이라고
    적혀 있는가" 가 아니다.
    """

    from collections import defaultdict

    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for doc in docs:
        parent = str(Path(doc["path"]).parent).replace("\\", "/")
        groups[parent].append((Path(doc["path"]).name, doc["title"]))

    lines: list[str] = []
    for parent in sorted(groups):
        lines.append(f"{parent}/" if parent != "." else "(저장소 루트)")
        lines += [f"  {n} — {t}" for n, t in sorted(groups[parent])]
    return "\n".join(lines)


def load(project: Path) -> dict | None:
    path = project / ".wiki" / "corpus.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="저장소 문서의 목록을 만든다")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--roots", nargs="*", default=DEFAULT_ROOTS,
    )
    parser.add_argument("--catalog", action="store_true", help="목록만 찍는다")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    root = args.project.expanduser().resolve()

    if args.catalog:
        index = load(root)
        if not index:
            print("목록이 없다. `--write` 로 먼저 만들어라.", file=sys.stderr)
            return 2
        print(catalog(index["docs"]))
        return 0

    docs = collect(root, args.roots)
    if not docs:
        print("문서를 못 찾았다.", file=sys.stderr)
        return 2
    listing = catalog(docs)

    print(f"# corpus — {root.name}\n")
    print(f"문서 {len(docs)}개 · 본문 {sum(d['chars'] for d in docs):,}자")
    print(f"목록 {len(listing):,}자 — 세션 시작에 이대로 실린다\n")
    biggest = sorted(docs, key=lambda d: -d["chars"])[:5]
    print("## 가장 큰 문서 — 통째로는 못 싣는다\n")
    for doc in biggest:
        print(f"- {doc['chars']:>7,}자  `{doc['path']}`")
    print()

    if not args.write:
        print("`--write` 를 주면 `.wiki/corpus.json` 에 쓴다.")
        return 0

    out = root / ".wiki" / "corpus.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"docs": docs}, ensure_ascii=False), encoding="utf-8"
    )
    print(f"썼다: {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
