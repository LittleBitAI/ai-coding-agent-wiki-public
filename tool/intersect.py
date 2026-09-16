"""여러 프로젝트의 census 를 겹쳐 무엇이 공유할 지식인가를 낸다."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path


def skeleton(text: str) -> str:
    t = " ".join(text.split())
    t = re.sub(r"#\d+", "#N", t)
    t = re.sub(r"\b[0-9a-f]{7,40}\b", "SHA", t)
    t = re.sub(r"\d+", "N", t)
    t = re.sub(r"[A-Za-z0-9_./\\-]{12,}", "PATH", t)
    return t[:220]


def load(path: Path) -> tuple[str, list[str]]:
    name = path.stem.replace("census-", "")
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return name, [r["text"] for r in rows]


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="census 들을 겹쳐 공유 후보를 낸다")
    parser.add_argument("census", nargs="+", type=Path)
    parser.add_argument("--threshold", type=float, default=0.72)
    parser.add_argument("--min-chars", type=int, default=18,
                        help="이보다 짧은 발화는 규칙을 안 담는다")
    args = parser.parse_args()

    projects: dict[str, list[str]] = {}
    for path in args.census:
        name, texts = load(path)
        projects[name] = [t for t in texts if len(t) >= args.min_chars]

    names = list(projects)
    print(f"# 교집합 — {len(names)}개 프로젝트\n")
    for name in names:
        print(f"- `{name}` 발화 {len(projects[name])}건")
    print()

    # 프로젝트 A 의 각 발화 뼈대를 다른 프로젝트에서 찾는다.
    # 어느 프로젝트에서 나왔는지를 함께 들고 다닌다.
    buckets: list[tuple[str, dict[str, int]]] = []
    for name in names:
        for text in projects[name]:
            skel = skeleton(text)
            for rep, seen in buckets:
                if min(len(skel), len(rep)) / max(len(skel), len(rep), 1) < args.threshold:
                    continue
                if SequenceMatcher(None, skel, rep).ratio() >= args.threshold:
                    seen[name] = seen.get(name, 0) + 1
                    break
            else:
                buckets.append((skel, {name: 1}))

    shared = [(rep, seen) for rep, seen in buckets if len(seen) >= 2]
    shared.sort(key=lambda item: (-len(item[1]), -sum(item[1].values())))

    print(f"## 둘 이상에서 반복된 지시 — {len(shared)}종\n")
    print("여기 있는 것이 `operator`/`craft` 페이지 후보다. "
          "프로젝트가 달라도 같은 말을 했다면 그것은 저장소가 아니라 "
          "사람이나 기술을 따라다니는 것이다.\n")
    # 짧은 이름이 겹치면 어느 프로젝트인지 못 읽는다 — `example-wiki` 와
    # `example-project` 가 둘 다 `ai` 가 됐다. 겹치지 않을 만큼만 자른다.
    short = {name: name for name in names}
    for length in range(3, 40):
        cut = {name: name[:length] for name in names}
        if len(set(cut.values())) == len(names):
            short = cut
            break

    print("| 프로젝트 수 | 총 횟수 | 어디서 | 지시 |")
    print("| ---: | ---: | --- | --- |")
    for rep, seen in shared[:24]:
        where = " · ".join(f"{short[k]}×{v}" for k, v in sorted(seen.items()))
        print(f"| {len(seen)} | {sum(seen.values())} | {where} | {rep[:66]} |")

    only = defaultdict(int)
    for rep, seen in buckets:
        if len(seen) == 1:
            only[next(iter(seen))] += 1
    print("\n## 한 곳에서만 나온 것 — 여기 들이지 않는다\n")
    for name, count in sorted(only.items(), key=lambda i: -i[1]):
        print(f"- `{name}` {count}종")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
