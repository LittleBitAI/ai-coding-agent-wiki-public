"""Reuse the real injection functions to produce a cost and utterance table.

It does not score false positives — whether a rule belonged in a turn is a
judgement, and a number claiming to have made it would only hide that nobody
did. `label` drafts that judgement for measurement only, under the exception
`SCHEMA.md` writes down: a second model reviews every label, and the labels
choose thresholds, never what the hook injects.

    trigger_audit.py <census.jsonl>...        the census comparison
    trigger_audit.py replay <trajectory>...   dedup against today, recall
    trigger_audit.py latency --project <repo> the hook's own time, p50 and p95
    trigger_audit.py label <trajectory>...    recall labels into raw/
    trigger_audit.py suggest [labels]         the similarity threshold, from those labels
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import glob
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

import trajectory
from inject import (
    COMPACTED, LIMIT, REPO_BUDGET, RULE_BUDGET, budget, compose, first_sentence,
    label, match_pages, pages, remembered, render_parts, repeatable, repeated,
    rule_paragraph, sent_whole, tag, title_of, whole,
)


def measure(prompt: str, available: list, rule_limit=None, repo_limit=None) -> dict:
    """The size of the rendered block, without the header, source or separator.

    This is the size before translation. `inject` renders a target
    repository's `.wiki/` body after turning it English, so on a turn where
    the translation succeeded `trajectory.cost` is larger than this. Matching
    the two would mean a round trip per utterance, which is exactly what
    replaying a census is for avoiding. Subtract this difference before
    comparing the numbers.
    """
    matched = match_pages(prompt, available)
    rules, decisions, rule, repo, _trimmed = render_parts(matched, rule_limit, repo_limit)
    return {
        "names": [label(p) for _s, _b, p in rules + decisions],
        "rule": sum(map(len, rule)), "repo": sum(map(len, repo)),
    }


def census_paths(patterns: list[str]) -> list[Path]:
    """PowerShell does not expand a wildcard for a native command."""
    paths = []
    for pattern in patterns:
        found = sorted(glob.glob(pattern))
        if not found:
            raise ValueError(f"입력 파일이 없다: {pattern}")
        paths.extend(Path(p) for p in found)
    return list(dict.fromkeys(paths))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command in COMMANDS:
        return COMMANDS[command](sys.argv[2:])
    return census(sys.argv[1:])


def census(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="실제 발화와 주입 결과를 대조한다")
    parser.add_argument("census", nargs="+")
    parser.add_argument("--samples", type=int, default=2, help="페이지별 적중·미적중 표본 수")
    parser.add_argument("--project", type=Path, help="지식을 측정할 저장소 (생략하면 미측정)")
    parser.add_argument("--adapter", help="기본값은 프로젝트 폴더 이름")
    args = parser.parse_args(argv)
    project = args.project.expanduser().resolve() if args.project else None
    if project and not project.is_dir():
        parser.error(f"저장소가 없다: {project}")
    adapter = args.adapter or (project.name if project else None)
    try:
        paths = census_paths(args.census)
    except ValueError as error:
        parser.error(str(error))
    turns = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                turns.append((f"{path.as_posix()}:{number}", json.loads(line)["text"]))

    available = pages(adapter, project)
    limits = budget(adapter, RULE_BUDGET, project), budget(adapter, REPO_BUDGET, project)
    before = [measure(text, available) for _where, text in turns]
    after = [measure(text, available, *limits) for _where, text in turns]
    counts = Counter(name for row in after for name in row["names"])
    print(f"# 트리거 감사 — 실제 발화 {len(turns)}건\n")
    print(f"대상: {project} · 어댑터: {adapter}\n" if project else
          "공유 규칙만 측정. 프로젝트 지식은 **미측정** (--project 필요).\n")
    print("현재 페이지로 재생한 결과다. 과거 실행이나 자동 오탐 판정이 아니다.\n")
    print("글자 수는 번역 전 크기다. 헤더·출처·구분자는 제외한다.")
    print("번역이 성공한 턴의 trajectory.cost 는 이보다 크다 — 두 수를 그대로 비교하지 마라.")
    print("repo는 결정 블록이다. .wiki/*.md 규칙은 rule, SessionStart 목록은 별도다.\n")
    print("| 축 | 축약 전 최대 | 실제 블록 최대 | p95 | 중앙 | 예산 |")
    print("| --- | ---: | ---: | ---: | ---: | --- |")
    for axis, limit in zip(("rule", "repo"), limits):
        if axis == "repo" and project is None:
            print("| repo | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 |")
            continue
        values = sorted(row[axis] for row in after) or [0]
        peak = max((row[axis] for row in before), default=0)
        print(f"| {axis} | {peak:,} | {max(values):,} | "
              f"{values[min(len(values)-1, int(len(values)*.95))]:,} | "
              f"{values[len(values)//2]:,} | {limit if limit else '없음 (축약 안 함)'} |")
    print("\n예산은 축약 목표다. 이름 목록의 최소 크기보다 작으면 초과할 수 있다.\n")
    print("| 걸린 발화 | 페이지 |")
    print("| ---: | --- |")
    for name, count in counts.most_common():
        print(f"| {count} | {name} |")

    print("\n## 페이지별 발화 대조 — 판정은 사람이 한다\n")
    for _meta, _body, path in available:
        name = label(path)
        if name == "operator/agent-delegation":
            continue  # an every-utterance rule must not hide another page's misses
        print(f"### {name}\n")
        for hit in (True, False):
            selected = [(where, text) for (where, text), row in zip(turns, after)
                        if (name in row["names"]) == hit]
            for where, text in selected[:max(0, args.samples)]:
                excerpt = " ".join(text.split())[:180]
                print(f"- {'걸림' if hit else '안 걸림'} {where} — {excerpt}")
        print()
    return 0


# ---- replay -----------------------------------------------------------------


def recall_misses(matched: list, seen: set, repeat: set, injection: str,
                  squeezed: bool = False) -> list[str]:
    """The recall invariant — one judgement, shared by `replay` and the tests.

    Every rule page the triggers chose is in the injection word for word:
    the whole rule paragraph for a page that declared `repeat: rule` and was
    already seen or sits on a turn over the host's ceiling (`inject.compose`),
    the full body for any other. Checking names alone goes green with the
    binding clauses gone. Written twice, the two copies drift apart. Decision
    records are left out: they never go in whole, and the summary `knowledge`
    makes of them is not what deduplication touches.
    """

    missing = []
    for _s, body, path in matched:
        name = label(path)
        if path.parent.name == "decisions":
            continue
        known = (name, tag(body)) in seen or squeezed
        if name in repeat and known and rule_paragraph(body):
            need = rule_paragraph(body)
        else:
            need = body
        if need not in injection:
            missing.append(name)
    return missing


def when(text: str) -> dt.datetime:
    found = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return found if found.tzinfo else found.replace(tzinfo=dt.timezone.utc)


def pct(values: list, q: float) -> int:
    """Nearest rank. `0` for nothing."""
    values = sorted(values)
    return values[min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))] if values else 0


def transcripts(home: Path | None = None) -> dict[str, tuple[str, Path]]:
    """`session → (host, transcript)` for every transcript on this machine.

    Codex has more than one home. Orca runs it under its own, one per
    account, and from August on this PC every Codex session lives there.
    """

    home = home or Path.home()
    orca = home / "AppData/Roaming/orca"
    codex_homes = [home / ".codex", *orca.glob("*/home"), *orca.glob("*/*/home")]
    if os.environ.get("CODEX_HOME"):
        codex_homes.append(Path(os.environ["CODEX_HOME"]))
    found = {}
    for codex in codex_homes:
        for root in (codex / "sessions", codex / "archived_sessions"):
            for path in root.rglob("rollout-*.jsonl") if root.is_dir() else ():
                found[path.stem[-36:]] = ("codex", path)
    for path in (home / ".claude/projects").glob("*/*.jsonl"):
        found[path.stem] = ("claude", path)
    return found


FILED = re.compile(r"Full output saved to: (\S+?additionalContext\.txt)")


def scan(path: Path) -> dict:
    """One pass over a transcript: compacts, Claude's hook injections, usage.

    `kept` and `filed` are the character counts of `UserPromptSubmit`
    injections that went in whole and that the host put in a file — the
    evidence `inject.LIMIT` stands on. `usage` is each Claude response's time
    and token usage, for the idle-return count.
    """

    out = {"compacts": [], "kept": [], "filed": [], "usage": []}
    with path.open("rb") as handle:
        for line in handle:
            compact = any(marker in line for marker in COMPACTED)
            hooked = b"hook_additional_context" in line
            used = b'"usage"' in line and b'"type":"assistant"' in line
            if not (compact or hooked or used):
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if compact and row.get("timestamp"):
                out["compacts"].append(when(row["timestamp"]))
            if used and row.get("timestamp"):
                out["usage"].append((when(row["timestamp"]), (row.get("message") or {}).get("usage") or {}))
            attachment = row.get("attachment") or {}
            if hooked and attachment.get("type") == "hook_additional_context" \
                    and attachment.get("hookEvent") == "UserPromptSubmit":
                content = attachment.get("content")
                for item in content if isinstance(content, list) else [content]:
                    item = str(item)
                    filed = FILED.search(item) if item.startswith("<persisted-output>") else None
                    if filed and Path(filed.group(1)).is_file():
                        out["filed"].append(len(Path(filed.group(1)).read_text(encoding="utf-8", errors="replace")))
                    elif not filed:
                        out["kept"].append(len(item))
    return out


def render(matched: list, limits: tuple, project, seen=frozenset(), repeat=frozenset(),
           limit: int | None = None) -> tuple:
    """`(body, full, names, squeezed)` as `inject` would send it, less the rendering."""

    rules, decisions, rule_parts, _repo, _t, body, squeezed = compose(
        matched, limits, "", project, seen, repeat, limit)
    return (body, sent_whole(rules, rule_parts),
            [label(p) for _s, _b, p in rules + decisions], squeezed)


# Pings needed to keep the cache over a gap: none under 60 minutes, then one
# per 55. The arithmetic is in the plan's bundle 3, step 7.
def pings(gap: float) -> int:
    return 0 if gap < 60 else math.ceil((gap - 60) / 55)


def replay(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="trajectory 를 지금 페이지로 다시 흘려 지금 방식과 중복 제거를 견준다")
    parser.add_argument("trajectory", nargs="+")
    parser.add_argument("--project", type=Path, help="페이지를 읽을 저장소 (기본: 첫 trajectory 의 저장소)")
    parser.add_argument("--adapter", help="기본값은 프로젝트 폴더 이름")
    parser.add_argument("--since", help="이 시각 이후 행만 (UTC, 예: 2026-09-23)")
    parser.add_argument("--until", help="이 시각까지의 행만 — 출발점 재현용 (UTC, 예: 2026-09-25T03:00)")
    args = parser.parse_args(argv)
    try:
        paths = census_paths(args.trajectory)
    except ValueError as error:
        parser.error(str(error))
    project = (args.project or paths[0].resolve().parent.parent).expanduser().resolve()
    adapter = args.adapter or project.name
    since = when(args.since) if args.since else None
    until = when(args.until) if args.until else None

    available = pages(adapter, project)
    limits = budget(adapter, RULE_BUDGET, project), budget(adapter, REPO_BUDGET, project)
    repeat = repeatable(available)
    sessions: dict[object, list[dict]] = defaultdict(list)
    for path in paths:
        for i, row in enumerate(trajectory.read(path)):
            at = when(row.get("at") or "1970-01-01")
            if (since and at < since) or (until and at > until):
                continue
            # No id joins nothing — each such row is a session of its own.
            sessions[row.get("session") or (path, i)].append(row | {"_at": at})

    found = transcripts()
    scans: dict[str, dict] = {}
    missing_tx = 0
    old_turn, new_turn, old_sum, new_sum = [], [], [], []
    loads = {"기록": [0, 0], "지금 방식": [0, 0], "새 방식": [0, 0]}
    over = Counter()
    over_recorded = Counter()
    turns_by_host = Counter()
    misses = []
    loaded_pages = Counter()
    gaps = []  # (gap minutes or None for no return, context tokens or None)
    for key, rows in sessions.items():
        rows.sort(key=lambda r: r["_at"])
        host, tx = found.get(key, (None, None)) if isinstance(key, str) else (None, None)
        if tx is None:
            missing_tx += 1
        traced = scans.setdefault(str(tx), scan(tx)) if tx else {"compacts": [], "usage": []}
        limit = LIMIT.get(host or "", min(LIMIT.values()))
        sim: list[dict] = []
        before: dict[str, set] = {"기록": set(), "지금 방식": set(), "새 방식": set()}
        session_old = session_new = 0
        previous = None
        for row in rows:
            matched = match_pages(str(row.get("utterance") or ""), available)
            old_body, _full, names, _s = render(matched, limits, project)
            reset = previous is not None and any(
                previous < c <= row["_at"] for c in traced["compacts"])
            seen = set() if reset or not isinstance(key, str) else remembered(sim, limit)
            new_body, full, _names, squeezed = render(matched, limits, project, seen, repeat, limit)
            new_size = len(new_body.encode("utf-8"))
            sim.append({"sent": new_size, "full": full, "reset": reset})
            misses += [(row.get("at"), name)
                       for name in recall_misses(matched, seen, repeat, new_body, squeezed)]

            if reset:
                before["새 방식"] = set()
            for kind, got in (("기록", row.get("injected") or []), ("지금 방식", names),
                              ("새 방식", [n for n, _t in full])):
                loads[kind][0] += sum(n in before[kind] for n in got)
                loads[kind][1] += len(got)
                before[kind] |= set(got)
            loaded_pages.update(names)
            old_size = len(old_body.encode("utf-8"))
            old_turn.append(old_size)
            new_turn.append(new_size)
            session_old += old_size
            session_new += new_size
            turns_by_host[host or "?"] += 1
            over[host or "?"] += new_size > limit
            if isinstance(row.get("sent"), int):
                over_recorded[host or "?"] += row["sent"] > limit

            if previous is not None:
                gap = (row["_at"] - previous).total_seconds() / 60
                after = [u for t, u in traced["usage"] if t > row["_at"]]
                gaps.append((gap, after[0].get("cache_creation_input_tokens") if after else None))
            previous = row["_at"]
        last = [u for t, u in traced["usage"] if t <= previous] if previous else []
        context = sum(last[-1].get(k) or 0 for k in (
            "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")) if last else None
        gaps.append((None, context))
        old_sum.append(session_old)
        new_sum.append(session_new)

    total = sum(len(r) for r in sessions.values())
    print(f"# 재생 — {total}턴, 세션 {len(sessions)}개\n")
    print(f"대상: {project} · 어댑터: {adapter} · 기간: {args.since or '처음'} ~ {args.until or '끝'} (UTC)\n")
    print("페이지는 지금의 페이지다 — 과거 실행의 재현이 아니라 지금 규칙으로 그 발화를 받았다면이다.")
    print("크기는 UTF-8 바이트, 번역 전이고 영어본 블록은 뺐다 (`measure` 와 같은 차이). "
          "그래서 실제 `sent` 보다 작고, 한도를 넘는 턴은 실제보다 적게 나온다.")
    print(f"`repeat: rule` 선언 페이지: {', '.join(sorted(repeat)) or '없음'}\n")
    if missing_tx:
        print(f"transcript 를 못 찾은 세션 {missing_tx}개는 compact 없이 재생했다 — "
              "그 세션의 절감은 과대 추정이다.\n")

    print("## 반복률 — 같은 세션에 이미 실린 페이지를 또 실은 비율\n")
    print("| | 다시 실음 / 적재 | 비율 |\n| --- | ---: | ---: |")
    for kind, (again, all_) in loads.items():
        note = " (전문만)" if kind == "새 방식" else ""
        print(f"| {kind}{note} | {again:,} / {all_:,} | {again / all_:.0%} |" if all_ else f"| {kind} | 0 / 0 | — |")

    print("\n## 턴당 주입 크기 (바이트)\n")
    print("| | 중앙값 | p90 |\n| --- | ---: | ---: |")
    recorded = [r.get("cost") for rs in sessions.values() for r in rs if isinstance(r.get("cost"), int)]
    print(f"| 기록 `cost` (글자, 규칙·결정 블록만) | {pct(recorded, .5):,} | {pct(recorded, .9):,} |")
    sent = [r["sent"] for rs in sessions.values() for r in rs if isinstance(r.get("sent"), int)]
    if sent:
        print(f"| 기록 `sent` ({len(sent)}턴) | {pct(sent, .5):,} | {pct(sent, .9):,} |")
    print(f"| 지금 방식 | {pct(old_turn, .5):,} | {pct(old_turn, .9):,} |")
    print(f"| 새 방식 | {pct(new_turn, .5):,} | {pct(new_turn, .9):,} |")

    print("\n## 세션 누적 주입량 (바이트)\n")
    print("| | 세션 합 중앙값 | 전체 합 |\n| --- | ---: | ---: |")
    print(f"| 지금 방식 | {pct(old_sum, .5):,} | {sum(old_sum):,} |")
    print(f"| 새 방식 | {pct(new_sum, .5):,} | {sum(new_sum):,} |")
    if sum(old_sum):
        print(f"\n감소율: 전체 합 {1 - sum(new_sum) / sum(old_sum):.0%}, "
              f"세션 합 중앙값 {1 - pct(new_sum, .5) / max(1, pct(old_sum, .5)):.0%}")

    print("\n## 호스트 한도를 넘은 턴\n")
    print("| 호스트 | 한도 (바이트) | 턴 | 새 방식 재생 초과 | 기록 `sent` 초과 |\n| --- | ---: | ---: | ---: | ---: |")
    for host, count in sorted(turns_by_host.items()):
        limit = LIMIT.get(host, min(LIMIT.values()))
        print(f"| {host} | {limit:,} | {count:,} | {over[host]:,} | {over_recorded[host]:,} |")
    kept = [n for s in scans.values() for n in s["kept"]]
    filed = [n for s in scans.values() for n in s["filed"]]
    if kept or filed:
        print(f"\nClaude 한도 근거 (이 세션들의 transcript): 전문으로 들어간 가장 큰 주입 "
              f"{max(kept, default=0):,}자, 파일로 빠진 가장 작은 주입 "
              f"{f'{min(filed):,}자' if filed else '없음'} — `inject.LIMIT` 과 견줘라")

    print("\n## 페이지별 주입 크기 (바이트)\n")
    print("| 페이지 | 전문 | 반복형 | 실린 턴 |\n| --- | ---: | ---: | ---: |")
    for meta, body, path in available:
        if path.parent.name == "decisions" or str(meta.get("severity")) not in ("landmine", "contract"):
            continue
        name = label(path)
        severity = str(meta["severity"])
        again = len(repeated(body, path, severity).encode("utf-8")) if name in repeat else None
        print(f"| {name} | {len(whole(severity, body, path).encode('utf-8')):,} | "
              f"{f'{again:,}' if again else '—'} | {loaded_pages[name]:,} |")

    print("\n## 유휴 뒤 복귀 — 7단계\n")
    print("간격은 같은 세션의 이어진 두 행 사이. C 는 복귀 직후 첫 응답의 "
          "`cache_creation_input_tokens` (Claude transcript 에서만), 복귀가 없으면 마지막 문맥 크기다.\n")
    print("| 간격 | 복귀 | C 측정 | C 합 |\n| --- | ---: | ---: | ---: |")
    buckets = ["60분 미만", "60~115분", "115~170분", "170~225분", "225~280분", "그 이상"]
    for i, name in enumerate(buckets):
        hit = [c for g, c in gaps if g is not None and min(pings(g), 5) == i]
        measured = [c for c in hit if c is not None]
        print(f"| {name} | {len(hit):,} | {len(measured):,} | {sum(measured):,} |")
    ends = [c for g, c in gaps if g is None]
    print(f"| 복귀 없음 (세션 끝) | {len(ends):,} | {sum(c is not None for c in ends):,} | "
          f"{sum(c or 0 for c in ends):,} |")
    print("\n| 상한 k | 순절감 추정 (토큰 환산, API 요율 대리값) |\n| ---: | ---: |")
    for k in range(1, 5):
        net = 0.0
        for g, c in gaps:
            if c is None or (g is not None and pings(g) == 0):
                continue
            j = pings(g) if g is not None else None
            net += (2 * c - 0.1 * c * (j + 1)) if j is not None and j <= k else -0.1 * c * k
        print(f"| {k} | {net:,.0f} |")
    print("\n복귀 없음은 핑 k번을 다 쓴 것으로 셌다 — 아직 열려 있는 세션에는 손해가 과대 추정이다.")

    print("\n## 리콜 불변식\n")
    if misses:
        print(f"빨강 — {len(misses)}건. 정규식이 고른 페이지가 새 방식 주입에 글자 그대로 없다:")
        for at, name in misses[:20]:
            print(f"- {at} {name}")
        return 1
    print("녹색 — 정규식이 고른 모든 페이지가 새 방식 주입에 글자 그대로 있다.")
    return 0


# ---- latency ----------------------------------------------------------------

HEAVY = "훅 주입 인코딩 cp949 원인 진단 리뷰 루프 머지 async 비동기 pytest 마크다운 강조 화면 디자인 예산 측정"
UTTERANCES = {"빈 발화 (0장)": "", "상시 3장": "좋다, 그렇게 해라", "많이 걸림": HEAVY}


def latency(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="inject.py 를 훅처럼 하위 프로세스로 돌려 시간을 잰다")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--with-translation", action="store_true",
                        help="번역을 켠 종단 수치. 발화마다 꼬리를 달아 캐시를 피한다")
    parser.add_argument("--host", default="claude")
    parser.add_argument("--search", action="store_true",
                        help="검색 데몬을 켜고 잰다. 없으면 훅이 데몬에 묻지 않는다 (PR ① 과 같은 경로)")
    args = parser.parse_args(argv)
    project = args.project.expanduser().resolve()
    here = Path(__file__).resolve().parent

    # A throwaway copy of `.wiki/`. Running against the real one would write
    # these fake turns into its trajectory.
    root = Path(tempfile.mkdtemp())
    try:
        target = root / "project"
        if (project / ".wiki").is_dir():
            shutil.copytree(project / ".wiki", target / ".wiki",
                            ignore=shutil.ignore_patterns("trajectory.jsonl"))
        else:
            (target / ".wiki").mkdir(parents=True)
        transcript = root / "transcript.jsonl"
        transcript.write_text("", encoding="utf-8")
        env = dict(os.environ) | {"PYTHONIOENCODING": "utf-8"}
        if args.search:
            import inject
            import search

            if inject.SUGGEST_MIN is None:
                print("`inject.SUGGEST_MIN` 이 없어 훅이 데몬에 묻지 않는다 — 데몬 있음은 잴 것이 없다")
                return 1
            env.pop("WIKI_SEARCH", None)
            # Started and warm on this copy before the clock runs: the first
            # request for a repository builds its index.
            for _attempt in range(120):
                if search.ask("warm", target, "hook", 5.0, wait=120) is not None:
                    break
                time.sleep(1)
        else:
            env["WIKI_SEARCH"] = "off"
        if not args.with_translation:
            # The switches `test_inject.py` already uses. The cache answers
            # before the key is consulted, so it is redirected too.
            env |= {"GEMINI_API_KEY": "", "TRANSLATE_ENV": str(root / "absent.env"),
                    "TRANSLATE_CACHE": str(root / "cache.sqlite3")}
        print(f"# 훅 지연 — {args.runs}회, 번역 {'켬' if args.with_translation else '끔'}, "
              f"호스트 {args.host}, 검색 데몬 {'있음' if args.search else '없음'}\n")
        print("| 발화 | p50 (ms) | p95 (ms) |\n| --- | ---: | ---: |")
        for name, text in UTTERANCES.items():
            times = []
            for i in range(args.runs):
                prompt = f"{text} ({i})" if text and args.with_translation else text
                started = time.perf_counter()
                subprocess.run(
                    [sys.executable, str(here / "inject.py"), "--project", str(target),
                     "--host", args.host],
                    input=json.dumps({"prompt": prompt, "session_id": "latency",
                                      "transcript_path": str(transcript)}, ensure_ascii=False),
                    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                )
                times.append((time.perf_counter() - started) * 1000)
            print(f"| {name} | {pct(times, .5):,.0f} | {pct(times, .95):,.0f} |")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


# ---- label --------------------------------------------------------------------

# Codex's id for the model the plan calls sol, read off its model list.
SOL = "gpt-6-sol"
BATCH = 20
ROUNDS = 3


def candidates(available: list, always: set[str]) -> dict[str, str]:
    """`name → one line` for every page the hook can inject.

    The rule paragraph's first sentence, the same extraction `rule_index`
    makes; a page without one is represented by its title. The pages that
    ride on every turn are left out — there is nothing to decide about them.
    """

    found = {}
    for meta, body, path in available:
        name = label(path)
        if path.parent.name == "decisions" or name in always:
            continue
        if str(meta.get("severity")) in ("landmine", "contract") and meta.get("triggers"):
            found[name] = first_sentence(body) or title_of(body, path)
    return found


def draw(turns: list[dict], size: int, seed: int) -> list[dict]:
    """A stratified sample, the same one for the same seed.

    Split across repositories by their share of turns, at most 20 turns from
    one session, and at least half from turns where nothing past the
    every-turn rules matched — those are where a miss would hide.
    """

    rng = random.Random(seed)
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for turn in turns:
        by_repo[turn["repo"]].append(turn)
    picked = []
    repos = sorted(by_repo)
    for n, repo in enumerate(repos):
        pool = list(by_repo[repo])
        rng.shuffle(pool)
        quota = size - len(picked) if n == len(repos) - 1 else round(size * len(pool) / len(turns))
        chosen: list[dict] = []
        per_session = Counter()
        for quiet_only, goal in ((True, math.ceil(quota / 2)), (False, quota)):
            for turn in pool:
                if len(chosen) >= goal:
                    break
                if (quiet_only and not turn["quiet"]) or turn in chosen \
                        or per_session[turn["session"]] >= 20:
                    continue
                chosen.append(turn)
                per_session[turn["session"]] += 1
        picked += chosen
    return picked


def parse_json(text: str):
    """The model's JSON, from inside a code fence or loose in the text."""

    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", text.strip())
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=0)
    end = max(text.rfind("]"), text.rfind("}")) + 1
    return json.loads(text[start:end])


def ask(command: list[str], prompt: str):
    """Run one model call in an empty folder and read its JSON answer.

    The empty folder is what keeps this wiki's own hooks out of it: `hook.py`
    finds no attached repository there and passes. Codex prints progress to
    its streams, so its last message is read from `-o` instead.
    """

    from chat_local import cli_command

    codex = command[0] == "codex"
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "last.txt"
        command = [*cli_command(command[0]), *command[1:]]
        if codex:
            command = [*command[:-1], "-o", str(out), command[-1]]
        done = subprocess.run(command, input=prompt, cwd=folder, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900)
        if done.returncode:
            raise RuntimeError(f"{Path(command[0]).name} 실패 ({done.returncode}): {done.stderr[-500:]}")
        return parse_json(out.read_text(encoding="utf-8") if codex else done.stdout)


HAIKU = ["claude", "-p", "--model", "haiku", "--tools", "", "--setting-sources", "",
         "--settings", '{"disableAllHooks":true}', "--strict-mcp-config", "--no-session-persistence"]
CODEX = ["codex", "exec", "--model", SOL, "-c", 'model_reasoning_effort="medium"',
         "--sandbox", "read-only", "-c", 'approval_policy="never"', "--ephemeral",
         "--skip-git-repo-check", "--ignore-user-config", "-c", "project_doc_max_bytes=0",
         "--disable", "shell_tool", "--disable", "apps", "--disable", "plugins",
         "--disable", "memories", "--disable", "multi_agent", "-"]

TASK = (
    "Each turn below is one utterance a person sent to an AI coding agent. A wiki "
    "loads rule pages into the agent's context. Decide, for each turn, which of the "
    "candidate pages should have been loaded: a page belongs when its rule would "
    "change what the agent does on that turn. Many turns need none.\n\n"
    "Candidates (name — what the rule says):\n{candidates}\n\nTurns:\n{turns}\n"
)
LABEL = TASK + (
    '\nAnswer with JSON only: [{{"turn": <id>, "pages": [{{"name": "<candidate>", '
    '"why": "<one line>"}}]}}], one object for every turn, an empty list where no page belongs.'
)
REVIEW = TASK + (
    "\nAnother model labelled these turns:\n{labels}\n\nReview every label. Answer with "
    'JSON only: {{"objections": [{{"turn": <id>, "name": "<page>", "why": "<one line>"}}], '
    '"missing": [{{"turn": <id>, "name": "<page>", "why": "<one line>"}}]}}. An objection '
    "is a page that should not be there; missing is a candidate that should be there and "
    "is not. Use empty lists where you agree."
)
REVISE = TASK + (
    "\nYour labels were:\n{labels}\n\nA reviewer disagreed:\n{review}\n\nFor each point "
    "either change the label or keep it. Answer with the full corrected labels as JSON "
    "only, in the same shape as before."
)


def label_batch(batch: list[dict], pool: dict[str, str]) -> list[dict]:
    """Haiku drafts, sol reviews, Haiku revises — until no objection or three rounds."""

    listing = "\n".join(f"- `{name}` — {line}" for name, line in sorted(pool.items()))
    turns = json.dumps([{"turn": i, "utterance": t["utterance"]} for i, t in enumerate(batch)],
                       ensure_ascii=False, indent=1)
    fill = {"candidates": listing, "turns": turns}
    labels = ask(HAIKU, LABEL.format(**fill))
    review: dict = {}
    for _round in range(ROUNDS):
        review = ask(CODEX, REVIEW.format(**fill, labels=json.dumps(labels, ensure_ascii=False)))
        if not (review.get("objections") or review.get("missing")):
            break
        labels = ask(HAIKU, REVISE.format(**fill, labels=json.dumps(labels, ensure_ascii=False),
                                          review=json.dumps(review, ensure_ascii=False)))
    else:
        # One last review of the final revision, so what stays disputed is
        # what sol still objects to rather than what it said a round ago.
        review = ask(CODEX, REVIEW.format(**fill, labels=json.dumps(labels, ensure_ascii=False)))

    chosen = {int(x.get("turn", -1)): {p.get("name") for p in x.get("pages") or []}
              for x in labels if isinstance(x, dict)}
    disputed = defaultdict(list)
    for kind in ("objections", "missing"):
        for x in review.get(kind) or []:
            disputed[int(x.get("turn", -1))].append(f"{kind}:{x.get('name')}")
    out = []
    for i, turn in enumerate(batch):
        names = sorted(n for n in chosen.get(i, set()) if n in pool)
        out.append({k: turn[k] for k in ("repo", "session", "at", "utterance", "regex")}
                   | {"labels": names, "extra": sorted(set(names) - set(turn["regex"])),
                      "disputed": disputed.get(i, [])})
    return out


def label_turns(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="정규식이 놓친 페이지의 정답 라벨을 만든다 (Haiku 초안, sol 검토)")
    parser.add_argument("trajectory", nargs="+", help="<저장소>/.wiki/trajectory.jsonl — 저장소는 경로에서 읽는다")
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "raw/recall-labels.jsonl")
    parser.add_argument("--dry-run", action="store_true", help="표본 구성만 보이고 모델은 부르지 않는다")
    args = parser.parse_args(argv)
    try:
        paths = census_paths(args.trajectory)
    except ValueError as error:
        parser.error(str(error))

    turns, pools, cut = [], {}, 0
    for path in paths:
        project = path.resolve().parent.parent
        available = pages(project.name, project)
        # What a lone neutral character matches rides on every turn. Not a
        # space: ai-nara-shop's `project` triggers on `\S`.
        always = {label(p) for _s, _b, p in match_pages("·", available)}
        pools[project.name] = candidates(available, always)
        for row in trajectory.read(path):
            text = str(row.get("utterance") or "")
            if not text.strip():
                continue
            if int(row.get("chars") or 0) > len(text):
                cut += 1  # rows before 2026-09-25 were cut at 500 characters
                continue
            regex = [label(p) for _s, _b, p in match_pages(text, available)
                     if p.parent.name != "decisions" and label(p) not in always]
            turns.append({"repo": project.name, "session": row.get("session") or "",
                          "at": row.get("at"), "utterance": text, "regex": regex,
                          "quiet": not regex})
    sample = draw(turns, args.size, args.seed)
    print(f"# 리콜 라벨 — 표본 {len(sample)}턴 / 후보 {len(turns)}턴 (잘린 행 {cut}개 제외)\n")
    for repo, count in Counter(t["repo"] for t in sample).items():
        quiet = sum(t["quiet"] for t in sample if t["repo"] == repo)
        print(f"- {repo}: {count}턴, 상시 규칙 말고 안 걸린 턴 {quiet}, 후보 페이지 {len(pools[repo])}장")
    if args.dry_run:
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    labelled = []
    for repo in sorted({t["repo"] for t in sample}):
        mine = [t for t in sample if t["repo"] == repo]
        for start in range(0, len(mine), BATCH):
            labelled += label_batch(mine[start:start + BATCH], pools[repo])
            print(f"  {repo} {min(start + BATCH, len(mine))}/{len(mine)}", flush=True)
    args.out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in labelled),
                        encoding="utf-8", newline="\n")
    extra = [x for x in labelled if x["extra"] and not x["disputed"]]
    print(f"\n정규식이 놓친 페이지가 있는 턴 {len(extra)} · 이견이 남은 턴 "
          f"{sum(bool(x['disputed']) for x in labelled)} (문턱을 정할 때 뺀다)")
    print(f"결과: {args.out} — 커밋하지 않는다. 다른 저장소의 발화 원문이 들어 있다")
    return 0


# ---- suggest ------------------------------------------------------------------


def sweep(turns: list[dict], key: str, k: int) -> list[tuple[float, int, int, int]]:
    """`(threshold, suggested, correct, truth)` at every score that occurs.

    A turn suggests its top `k` eligible pages scoring at least the
    threshold — what `inject.suggest` does. Truth is the labels' `extra`,
    the pages the regex missed.
    """

    truth = sum(len(t["extra"]) for t in turns)
    scores = sorted({h[key] for t in turns for h in t["eligible"][:k] if h[key] is not None})
    out = []
    for floor in scores:
        suggested = correct = 0
        for t in turns:
            ranked = sorted((h for h in t["eligible"] if h[key] is not None),
                            key=lambda h: -h[key])[:k]
            picked = [h["name"] for h in ranked if h[key] >= floor]
            suggested += len(picked)
            correct += len(set(picked) & set(t["extra"]))
        out.append((floor, suggested, correct, truth))
    return out


def suggest_eval(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="리콜 라벨로 유사도 보조의 문턱을 정한다")
    parser.add_argument("labels", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "raw/recall-labels.jsonl")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="라벨의 repo 이름을 찾을 상위 폴더")
    parser.add_argument("--no-english", action="store_true", help="질의를 발화 원문만으로")
    parser.add_argument("--precision", type=float, default=0.6)
    args = parser.parse_args(argv)

    import search
    import searchd
    import translate
    from inject import HANGUL, MAX_RENDERED

    rows = trajectory.read(args.labels)
    disputed = [r for r in rows if r.get("disputed")]
    turns = [r for r in rows if not r.get("disputed")]
    if not args.no_english:
        # The hook's own rule: a rendering only for Korean under the length
        # limit, and a failed one is the original alone.
        wanted = [i for i, t in enumerate(turns)
                  if HANGUL.search(t["utterance"]) and len(t["utterance"]) <= MAX_RENDERED]
        done = translate.translate([turns[i]["utterance"] for i in wanted], translate.KO_EN,
                                   time.monotonic() + 600)
        for i, english in zip(wanted, done):
            if english != turns[i]["utterance"]:
                turns[i]["english"] = english

    embedder = searchd.Embedder(search.cache_dir())
    embedder.start()
    for repo in sorted({t["repo"] for t in turns}):
        project = (args.root / repo).resolve()
        available = pages(repo, project)
        always = {label(p) for _s, _b, p in match_pages("·", available)}
        judged = set(candidates(available, always))
        pool = searchd.Pool(project, "hook", embedder)
        pool.refresh()
        while not pool.complete() and embedder.state != "off":
            time.sleep(0.5)
        for t in (t for t in turns if t["repo"] == repo):
            query = t["utterance"] + ("\n" + t["english"] if t.get("english") else "")
            taken = set(t["regex"]) | always
            t["eligible"] = [h | {"name": label(Path(h["path"]))} for h in pool.search(query, 60)
                             if label(Path(h["path"])) in judged - taken]

    print(f"# 유사도 보조 문턱 — 라벨 {len(rows)}턴, disputed {len(disputed)}턴 제외, "
          f"평가 {len(turns)}턴\n")
    print(f"질의: 발화 원문{'' if args.no_english else ' + 영어본'} · 벡터: {embedder.state} · "
          f"정답(정규식이 놓친 페이지) {sum(len(t['extra']) for t in turns)}개, "
          f"그런 턴 {sum(bool(t['extra']) for t in turns)}턴\n")
    print(f"기본 규칙: 정밀도 {args.precision:.0%} 이상 가운데 리콜이 가장 큰 문턱\n")
    print("| 점수 | k | 문턱 | 제안 | 맞음 | 정밀도 | 리콜 |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for key in ("cos", "rrf"):
        for k in (1, 2):
            rows_ = sweep(turns, key, k)
            ok = [r for r in rows_ if r[1] and r[2] / r[1] >= args.precision]
            best = max(ok, key=lambda r: (r[2], r[0])) if ok else None
            if best is None:
                top = max(rows_, key=lambda r: r[2] / r[1] if r[1] else 0, default=None)
                note = (f"최고 정밀도 {top[2] / top[1]:.0%} (문턱 {top[0]}, 제안 {top[1]})"
                        if top and top[1] else "제안 없음")
                print(f"| {key} | {k} | 없음 | — | — | {note} | — |")
                continue
            floor, suggested, correct, truth = best
            print(f"| {key} | {k} | {floor} | {suggested} | {correct} | "
                  f"{correct / suggested:.0%} | {correct / max(1, truth):.0%} |")
    return 0


COMMANDS = {"replay": replay, "latency": latency, "label": label_turns, "suggest": suggest_eval}


if __name__ == "__main__":
    raise SystemExit(main())
