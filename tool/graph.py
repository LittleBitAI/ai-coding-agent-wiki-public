"""graph — 정책 그래프를 낸다. 그리는 것은 여기서 안 한다."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from inject import (  # noqa: E402
    INJECTABLE, RULE_BUDGET, SLOT, WIKI, budget, slots_for,
)
from wikilib import front_matter  # noqa: E402

SCOPES = ("operator", "craft")
HOOK_MARK = "tool/inject.py"
NS = "rule"          # 이 파일이 담는 축. 지식 축은 대상 저장소의 `.wiki/graph.json`

# 강제 사다리. 색은 "굳은 것 → 흩어지는 것" 순서다 — 1층은 막히고 5층은 문장이다.
LADDER = [
    (1, "차단", "permissions.deny", "#2b3a67"),
    (2, "주입", "UserPromptSubmit 훅", "#3f6b8f"),
    (3, "절차", "스킬", "#6b8ea3"),
    (4, "검사", "PreToolUse 훅", "#93a8ac"),
    (5, "문장", "산문", "#b9b3a4"),
]

# 사다리의 번호는 비용 순이지 세기 순이 아니다. 싼 것부터 1이고, 그래서
# "첫 칸에서 멈춘다" 가 성립한다. 하지만 노드 색이 답해야 하는 물음은 "얼마나
# 세게 강제되나" 이고, 그건 다른 순서다 — 막는 둘(1·4)이 가장 세고, 절차가
# 그다음, 읽히기만 하는 주입이 그다음, 문장이 맨 끝이다.
STRENGTH = [1, 4, 3, 2, 5]


def page_files(project_paths: list[Path]) -> list[tuple[str, str, Path]]:
    """(범위, 이름, 경로). 공유 위키의 규칙 + 각 저장소의 지식 페이지.

    결정 기록은 뺀다. 한 저장소에 88건이라 그리면 그래프가 아니라 모래알이
    되고, 그것들은 서로 링크하지도 않는다. 개수만 프로젝트 표에 싣는다.
    """

    found = []
    for scope in SCOPES:
        directory = WIKI / scope
        if directory.is_dir():
            for path in sorted(directory.glob("*.md")):
                found.append((scope, f"{scope}/{path.stem}", path))
    for repo in project_paths:
        directory = repo / ".wiki"
        if directory.is_dir():
            for path in sorted(directory.glob("*.md")):
                found.append((repo.name, f"{repo.name}/.wiki/{path.stem}", path))
    return found


def load_pages(project_paths: list[Path] | None = None) -> dict[str, dict]:
    pages: dict[str, dict] = {}
    for scope, name, path in page_files(project_paths or []):
        meta, body = front_matter(path.read_text(encoding="utf-8"))
        enforce = meta.get("enforce") if isinstance(meta.get("enforce"), dict) else {}
        headline, rule = "", ""
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("# ") and not headline:
                headline = line[2:]
            elif line.startswith("규칙."):
                rule = line[3:].strip()
                break
        pages[name] = {
            "scope": scope,
            "local": path.parent.name == ".wiki",
            "severity": str(meta.get("severity") or "preference"),
            "triggers": [str(t) for t in (meta.get("triggers") or [])],
            "links": [str(x) for x in (meta.get("links") or [])]
            + re.findall(r"\[\[([^\]]+)\]\]", body),
            "sources": [str(s).split("#")[0] for s in (meta.get("sources") or [])]
            + [str(s) for s in (meta.get("reads") or [])],
            "deny": [str(d) for d in (enforce.get("deny") or [])],
            "pretooluse": str(enforce.get("pretooluse") or ""),
            "headline": headline or path.stem,
            "rule": rule,
            "chars": len(body),
            "slots": sorted(set(SLOT.findall(body))),
        }
    return pages


def skills_touching(pages: dict[str, dict]) -> dict[str, list[str]]:
    """어느 스킬이 어느 페이지를 든다고 말하는가."""

    touched: dict[str, list[str]] = {name: [] for name in pages}
    directory = WIKI / "skills"
    if not directory.is_dir():
        return touched
    for path in sorted(directory.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for name in pages:
            if name in text or name.rsplit("/", 1)[-1] in text:
                touched[name].append(path.parent.name)
    return touched


def layers_of(page: dict, skills: list[str]) -> list[int]:
    """이 규칙이 실제로 서 있는 층들. 산문(5)은 언제나 포함한다."""

    found = []
    if page["deny"]:
        found.append(1)
    if page["severity"] in INJECTABLE and page["triggers"]:
        found.append(2)
    if skills:
        found.append(3)
    if page["pretooluse"]:
        found.append(4)
    return found + [5]


def corpus_of(name: str) -> list[str]:
    path = WIKI / "raw" / f"census-{name}.jsonl"
    if not path.exists():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            text = json.loads(line).get("text")
        except Exception:
            continue
        if text:
            found.append(text)
    return found


def read_project(path: Path, pages: dict[str, dict]) -> dict:
    """대상 저장소에 무엇이 실제로 붙어 있는가.

    위키가 무엇을 선언했는지가 아니라 그쪽 `settings.json` 이 무엇을 갖고
    있는지를 읽는다. 둘이 어긋나는 것이 이 화면이 답해야 할 물음이다.
    """

    settings_path = path / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            settings = {}
    deny = set((settings.get("permissions") or {}).get("deny") or [])
    commands = [
        str(entry.get("command", ""))
        for event in (settings.get("hooks") or {}).values()
        for group in event
        for entry in group.get("hooks", [])
    ]
    inject = any(HOOK_MARK in c for c in commands)
    values = slots_for(path.name, path)

    status: dict[str, str] = {}
    for name, page in pages.items():
        # 남의 저장소의 지식 페이지는 이 저장소와 아무 상관이 없다.
        if page["local"] and not name.startswith(f"{path.name}/"):
            status[name] = "foreign"
            continue
        wants = []
        if page["deny"]:
            wants.append(page["deny"] and all(d in deny for d in page["deny"]))
        if page["pretooluse"]:
            wants.append(any(page["pretooluse"] in c for c in commands))
        if page["severity"] in INJECTABLE and page["triggers"]:
            wants.append(inject)
        if not wants:
            status[name] = "prose"
        elif all(wants):
            status[name] = "on"
        elif any(wants):
            status[name] = "partial"
        else:
            status[name] = "none"

    missing = sorted({
        slot
        for page in pages.values()
        if page["severity"] in INJECTABLE and page["triggers"]
        for slot in page["slots"]
        if slot not in values
    })
    corpus = corpus_of(path.name)
    attached = sum(1 for v in status.values() if v == "on")
    return {
        "key": path.name,
        "short": path.name,
        "path": str(path),
        "adapter": (str(path / ".wiki/adapter.toml") if (path / ".wiki/adapter.toml").exists()
                    else f"adapters/{path.name}.toml") if values else "",
        "inject": inject,
        "deny": len([d for d in deny]),
        "hooks": len([c for c in commands if HOOK_MARK not in c]),
        "corpus": len(corpus),
        "missing": missing,
        "status": status,
        "note": (
            f"규칙 {attached}장이 붙어 있다."
            if attached
            else "아직 아무것도 안 붙었다. `apply` 를 돌리지 않은 저장소다."
        ),
        "_corpus": corpus,
    }


def co_injection(pages: dict[str, dict], corpus: list[str]) -> dict[tuple[str, str], int]:
    """두 페이지가 같은 발화에 함께 실린 횟수.

    이것이 옵시디언에 없는 축이다. 위키링크는 사람이 이은 것이지만 이건 실제
    트래픽에서 잰 것이고, 한 턴에 나란히 실리는 두 규칙이 서로를 모르면 읽는
    쪽이 둘의 관계를 못 읽는다.
    """

    compiled = {
        name: [re.compile(t, re.IGNORECASE) for t in page["triggers"]]
        for name, page in pages.items()
        if page["severity"] in INJECTABLE and page["triggers"]
    }
    pairs: dict[tuple[str, str], int] = {}
    for text in corpus:
        hit = sorted(n for n, ps in compiled.items() if any(p.search(text) for p in ps))
        for i, a in enumerate(hit):
            for b in hit[i + 1 :]:
                pairs[(a, b)] = pairs.get((a, b), 0) + 1
    return pairs


def per_turn_load(pages: dict[str, dict], corpus: list[str]) -> dict[str, int]:
    """한 턴에 실제로 실리는 양.

    페이지 본문의 합계가 아니다. 여섯 장이 있어도 한 턴에 다 걸리는 일은
    없으므로 합계는 아무 뜻이 없고, 그걸 "예산" 이라고 부르면 아무도 정한 적
    없는 상한처럼 읽힌다.
    """

    compiled = {
        name: (page["chars"], [re.compile(t, re.IGNORECASE) for t in page["triggers"]])
        for name, page in pages.items()
        if page["severity"] in INJECTABLE and page["triggers"]
    }
    loads, counts = [], []
    for text in corpus:
        hit = [c for c, ps in compiled.values() if any(p.search(text) for p in ps)]
        if hit:
            loads.append(sum(hit))
            counts.append(len(hit))
    if not loads:
        return {"max": 0, "median": 0, "pages": 0, "hits": 0}
    loads.sort()
    return {
        "max": max(loads),
        "median": loads[len(loads) // 2],
        "pages": max(counts),
        "hits": len(loads),
    }


def build(pages: dict[str, dict], project_paths: list[Path]) -> dict:
    skills = skills_touching(pages)
    names = set(pages)
    projects = [read_project(p, pages) for p in project_paths]
    everything = [t for p in projects for t in p["_corpus"]] or corpus_of("*")
    if not everything:
        for path in sorted((WIKI / "raw").glob("census-*.jsonl")):
            everything += corpus_of(path.stem.removeprefix("census-"))

    nodes = []
    for name, page in pages.items():
        layers = layers_of(page, skills[name])
        nodes.append({
            "id": name,
            "label": name.rsplit("/", 1)[-1],
            "scope": page["scope"],
            "severity": page["severity"],
            "headline": page["headline"],
            "rule": page["rule"],
            "chars": page["chars"],
            "injected": page["severity"] in INJECTABLE and bool(page["triggers"]),
            "triggers": page["triggers"],
            "layers": layers,
            "layer": min(layers, key=STRENGTH.index),
            "deny": page["deny"],
            "pretooluse": page["pretooluse"],
            "skills": skills[name],
            "sources": page["sources"],
            "status": {p["key"]: p["status"][name] for p in projects},
        })

    def resolve(target: str) -> str | None:
        if target in names:
            return target
        return next((n for n in names if n.split("/", 1)[1] == target), None)

    links, seen = [], set()
    for name, page in pages.items():
        for target in page["links"]:
            hit = resolve(target)
            if hit and hit != name:
                key = tuple(sorted((name, hit)))
                if key not in seen:
                    seen.add(key)
                    links.append({"a": key[0], "b": key[1], "kind": "link", "by": {}})

    by_key = {"all": co_injection(pages, everything)}
    for p in projects:
        by_key[p["key"]] = co_injection(pages, p["_corpus"])
    pairs = sorted({k for table in by_key.values() for k in table})
    for a, b in pairs:
        links.append({
            "a": a, "b": b, "kind": "co",
            "by": {key: table.get((a, b), 0) for key, table in by_key.items()},
        })

    for p in projects:
        p.pop("_corpus", None)

    return {
        "nodes": nodes,
        "links": links,
        "projects": projects,
        "evidence": sorted({s for page in pages.values() for s in page["sources"]}),
        "corpus": len(everything),
        "load": per_turn_load(pages, everything),
        "cap": next(
            (budget(p["key"], RULE_BUDGET, p["path"]) for p in projects
             if budget(p["key"], RULE_BUDGET, p["path"])), 0),
        "ladder": [{"n": n, "title": t, "detail": d, "color": c} for n, t, d, c in LADDER],
    }


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="정책 그래프를 아티팩트로 낸다")
    parser.add_argument("--json", type=Path, default=WIKI / "graph.json")
    parser.add_argument(
        "--project", action="append", type=Path, default=[],
        help="붙은 상태를 읽을 저장소. 여러 번 줄 수 있다",
    )
    args = parser.parse_args()

    projects = [p.expanduser().resolve() for p in args.project if p.expanduser().is_dir()]
    pages = load_pages(projects)
    if not pages:
        print("페이지가 없다.")
        return 2

    data = build(pages, projects)
    data["ns"] = NS
    args.json.write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    co = [x for x in data["links"] if x["kind"] == "co"]
    load = data["load"]
    print(f"# graph — 노드 {len(data['nodes'])} · 링크 {len(data['links']) - len(co)} "
          f"· 공동 주입 {len(co)}")
    for p in data["projects"]:
        attached = sum(1 for v in p["status"].values() if v == "on")
        print(f"  {p['short']:32} 붙은 규칙 {attached}/{len(pages)} · 코퍼스 {p['corpus']:,}")
    cap = data["cap"]
    where = f"예산 {cap:,}" if cap else "예산 없음"
    print(f"한 턴 최대 {load['max']:,}자({load['pages']}장) · "
          f"중앙 {load['median']:,}자 · {where}")
    print(f"썼다: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
