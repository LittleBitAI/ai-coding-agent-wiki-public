"""UserPromptSubmit 훅 — 발화를 보고 맞는 위키 페이지를 컨텍스트에 넣는다."""

from __future__ import annotations

import hook_diagnostics  # noqa: F401 -- 진입점의 제한 시간 전 스택 보존
import argparse
import json
import re
import sys
from pathlib import Path

import trajectory
from wikilib import WIKI, front_matter

INJECTABLE = {"landmine", "contract"}
SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")

# 기본 예산은 없다. 걸린 규칙은 다 싣는다.
#
# 버리면 안 되기 때문이다. 버려질 것은 트리거에 걸린 규칙 — 이 발화에
# 필요하다고 판정된 바로 그것이고, 규칙이 안 실려서 어기는 것이 이 위키가
# 막으려는 실패다. 상한이 그 실패를 스스로 만들어서는 안 된다.
#
# 예산을 두더라도 자르지 않고 다듬는다. 등급이 낮은 것부터
# 전문에서 규칙 한 줄로 줄이고, 그래도 넘으면 제목과 경로만 남긴다.
# 사라지는 페이지는 없다.
# 예산은 프로젝트가 어댑터로 정한다. 대상 저장소의 프롬프트 상한과는 무관하다 —
# 훅의 `additionalContext` 는 그 경로를 안 지나가므로, 그쪽 숫자를 여기
# 가져오면 남의 상한이 된다.
#
# **축마다 따로다.** 하나로 두면 모자랄 때 줄어드는 것이 언제나 규칙이다 —
# `fit` 은 규칙만 다듬고 결정 기록은 한 글자도 안 건드리기 때문이다. 실제로 잰
# 가장 무거운 턴이 규칙 20,620자에 결정 2,173자였다. 지식이 9%인데 다듬는
# 부담은 100% 규칙이 진다. 늘어나는 쪽이 지켜야 할 쪽을 밀어내면 안 된다.
RULE_BUDGET = "rule_budget"
REPO_BUDGET = "repo_budget"

# 한 턴에 전문으로 실을 결정 기록의 수. 넘는 것은 버리지 않고 이름만 남긴다.
MAX_DECISIONS = 3


def budget(adapter: str | None, slot: str, project: str | Path | None = None) -> int | None:
    """그 축에 이 프로젝트가 정한 예산. 안 정했으면 None — 상한이 없다."""

    raw = slots_for(adapter, project).get(slot)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def shrink(body: str, path: Path, severity: str, hard: bool) -> str:
    """전문을 줄인다. 지우지 않는다.

    `hard` 면 제목과 경로만, 아니면 규칙 한 문단까지. 어느 쪽이든 그 페이지가
    걸렸다는 사실과 어디를 열면 되는지는 남는다 — 그것이 버리는 것과의 차이다.
    """

    title = next((x[2:].strip() for x in body.splitlines() if x.startswith("# ")), path.stem)
    head = f"<!-- wiki:{label(path)} ({severity}, 줄임) -->\n# {title}"
    if hard:
        return head + f"\n\n전문: `{label(path)}.md`"
    rule = next((x for x in body.splitlines() if x.startswith("규칙.")), "")
    return head + (f"\n\n{rule}" if rule else "") + f"\n\n전문: `{label(path)}.md`"


def fit(parts: list[str], rules: list, limit: int | None) -> tuple[list[str], int]:
    """예산에 맞춰 다듬는다. 넘쳐도 아무것도 안 버린다.

    등급이 낮은 것부터 규칙 한 줄로 줄이고, 그래도 넘으면 제목만 남긴다.
    예산이 없으면 아무것도 안 한다 — 그것이 기본값이다.
    """

    if not limit or sum(len(p) for p in parts) <= limit:
        return parts, 0

    trimmed = 0
    for hard in (False, True):
        for i in range(len(rules) - 1, -1, -1):
            if sum(len(p) for p in parts) <= limit:
                return parts, trimmed
            severity, body, path = rules[i]
            small = shrink(body, path, severity, hard)
            if len(small) < len(parts[i]):
                parts[i] = small
                trimmed += 1
    return parts, trimmed


def digest(body: str, path: Path) -> str:
    """결정 기록을 두 줄로 줄인다.

    전문을 실으면 안 된다. 한 저장소에 88건이고 각 700자라, 셋만 걸려도 규칙을
    밀어낸다. 실제로 통째로 싣자 한 턴 최대가 13,241자로 상한을 넘었고 적중률이
    67%가 됐다 — 40%를 넘으면 다 실어서 아무것도 안 읽히는 것과 같아진다는 게
    이 위키 자신의 기준이다.

    주입 시점에 필요한 것은 "이건 이미 정했고 이유는 이것" 이지 전문이 아니다.
    전문은 경로를 따라가면 있다.
    """

    title = next((x[2:].strip() for x in body.splitlines() if x.startswith("# ")), path.stem)
    why = next((x[3:].strip() for x in body.splitlines() if x.startswith("왜.")), "")
    head = re.split(r"(?<=다\.)\s", why, maxsplit=1)[0][:180] if why else ""
    return f"- {title}\n  {head}\n  전문: `.wiki/decisions/{path.stem}.md`"


def knowledge(decisions: list, limit: int | None) -> list[str]:
    """결정 기록 블록. 규칙과 **다른 예산**을 쓴다.

    지식이 규칙의 자리를 먹으면 안 된다. 규칙이 안 실려서 어기는 것이 이 위키가
    막으려는 실패이고, 그 실패를 지식이 만들어서는 안 되기 때문이다.

    넘칠 때는 전문을 하나씩 이름으로 내린다. 여기서도 사라지는 것은 없다 —
    무엇이 걸렸는지는 남고 어디를 열면 되는지도 남는다.
    """

    if not decisions:
        return []

    keep = MAX_DECISIONS
    while True:
        briefs = [digest(b, p) for _s, b, p in decisions[:keep]]
        rest = [p.stem for _s, _b, p in decisions[keep:]]
        block = "<!-- wiki:decisions -->\n이 주제는 이미 정한 적이 있다. 뒤집기 전에 이유를 보라."
        if briefs:
            block += "\n\n" + "\n".join(briefs)
        if rest:
            head = "같은 주제의 결정이" if briefs else "이 주제의 결정이"
            block += (
                f"\n\n{head} {len(rest)}건 {'더 ' if briefs else ''}있다: "
                + ", ".join(f"`{n}`" for n in rest[:8])
                + (" …" if len(rest) > 8 else "")
            )
        if limit is None or len(block) <= limit or keep == 0:
            return [block]
        keep -= 1


def label(path: Path) -> str:
    """페이지를 부르는 이름. 공유 위키는 `범위/이름`, 프로젝트는 `.wiki/이름`."""

    if path.parent.name == "decisions":
        return f".wiki/decisions/{path.stem}"
    if path.parent.name == ".wiki":
        return f".wiki/{path.stem}"
    return f"{path.parent.name}/{path.stem}"


def source_map(matched: list, project: str | None) -> str:
    """실린 페이지가 **어느 저장소에서 왔는지.** 경로를 절대 경로로 적는다.

    이 줄이 없어서 한 세션이 "위키에 기록해라" 를 현재 저장소의 `.wiki/` 로
    읽었다. 주입된 페이지 대부분이 허브에서 왔는데 헤더가 "이 저장소의 위키"
    라고 말했고, 허브의 경로는 어디에도 안 나왔다. 이름만으로는 못 고른다 -
    두 곳 다 "위키" 라고 불린다.

    범위별로 갈리는 규칙도 같이 적는다. `operator`·`craft` 는 저장소를 안
    가리므로 허브에, 저장소의 게이트·런처·포트·불변식은 그 저장소의 `.wiki/`
    에 산다.
    """

    hub = Path(__file__).resolve().parents[1]
    from_hub = sorted(
        {label(p) for _s, _b, p in matched if not str(label(p)).startswith(".wiki/")}
    )
    from_repo = sorted(
        {label(p) for _s, _b, p in matched if str(label(p)).startswith(".wiki/")}
    )

    lines = ["**출처.** 아래 페이지는 두 곳에서 온다. 고쳐 쓸 곳을 여기서 정해라."]
    lines.append(f"- 허브 위키 `{hub}` — `operator/` `craft/`. 저장소를 안 가리는 규칙")
    if project:
        repo_wiki = Path(project).expanduser() / ".wiki"
        lines.append(f"- 이 저장소 `{repo_wiki}` — 게이트·런처·포트·아키텍처 불변식")
    else:
        lines.append("- 대상 저장소의 `.wiki/` — 게이트·런처·포트·아키텍처 불변식")
    if from_hub:
        lines.append(f"- 이번에 허브에서 온 것: {', '.join(from_hub)}")
    if from_repo:
        lines.append(f"- 이번에 이 저장소에서 온 것: {', '.join(from_repo)}")
    return "\n".join(lines)


def adapter_path(adapter=None, project=None, *, wiki=None) -> Path | None:
    """checkout 원본 우선. 없는 기존 설치만 허브 이름 조회를 유지한다."""
    if project:
        local = Path(project).expanduser().resolve() / ".wiki/adapter.toml"
        if local.exists():
            return local
    return (wiki or WIKI) / "adapters" / f"{adapter}.toml" if adapter else None


def slots_for(adapter: str | None, project: str | Path | None = None) -> dict[str, str]:
    """선택한 checkout의 슬롯 값. adapter가 없으면 빈 표."""

    path = adapter_path(adapter, project)
    if path is None or not path.exists():
        return {}
    import tomllib

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {k: str(v) for k, v in (data.get("slots") or {}).items()}


def fill(body: str, values: dict[str, str]) -> str:
    """`{슬롯}` 만 바꾼다.

    `str.format` 을 쓰면 트리거의 `{0,10}` 과 코드 블록의 중괄호까지 건드린다.
    아는 이름만 갈아 끼우고 모르는 것은 그대로 둔다 — 안 채워진 채로 남으면
    `apply` 가 짚는다.
    """

    return SLOT.sub(lambda m: values.get(m.group(1), m.group(0)), body)


def project_wiki(project: str | Path | None) -> Path | None:
    """대상 저장소의 `.wiki/`. 없으면 None."""

    if not project:
        return None
    directory = Path(project).expanduser() / ".wiki"
    return directory if directory.is_dir() else None


def pages(
    adapter: str | None = None,
    project: str | Path | None = None,
) -> list[tuple[dict[str, object], str, Path]]:
    """공유 위키의 규칙 + 그 프로젝트의 지식.

    프로젝트 페이지는 `decisions/` 까지 훑는다. 결정 기록은 수가 많아서
    (한 저장소에 90건) 전부 실으면 예산이 터지므로, 고르는 쪽에서 몇 개만
    남긴다. 여기서는 읽기만 한다.
    """

    values = slots_for(adapter, project)
    found = []
    for scope in ("operator", "craft"):
        directory = WIKI / scope
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            meta, body = front_matter(path.read_text(encoding="utf-8"))
            found.append((meta, fill(body, values) if values else body, path))

    local = project_wiki(project)
    if local:
        for path in sorted(local.glob("*.md")) + sorted(local.glob("decisions/*.md")):
            meta, body = front_matter(path.read_text(encoding="utf-8"))
            found.append((meta, fill(body, values) if values else body, path))
    return found


def match_pages(prompt: str, available: list) -> list:
    """주입과 감사가 같은 등급·정규식 판정을 쓴다."""
    matched = []
    for meta, body, path in available:
        severity = str(meta.get("severity") or "")
        triggers = meta.get("triggers")
        if severity not in INJECTABLE or not isinstance(triggers, list):
            continue
        for pattern in triggers:
            try:
                if re.search(str(pattern), prompt, re.IGNORECASE):
                    matched.append((severity, body, path))
                    break
            except re.error:
                continue
    return matched


def render_parts(matched: list, rule_limit: int | None, repo_limit: int | None) -> tuple:
    """실제로 보내는 두 축. 감사도 슬롯 치환·요약·이름 목록까지 센다."""
    decisions = sorted(
        (m for m in matched if m[2].parent.name == "decisions"),
        key=lambda m: m[2].name, reverse=True,
    )
    rules = [m for m in matched if m[2].parent.name != "decisions"]
    rules.sort(key=lambda item: 0 if item[0] == "landmine" else 1)
    parts = [f"<!-- wiki:{label(p)} ({s}) -->\n{b}" for s, b, p in rules]
    parts, trimmed = fit(parts, rules, rule_limit)
    return rules, decisions, parts, knowledge(decisions, repo_limit), trimmed


def main() -> int:
    # 들어오는 발화도 나가는 주입문도 한글이다. 인코딩을 환경에 안 맡긴다.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="발화에 맞는 위키 페이지를 넣는다")
    parser.add_argument("--adapter", default=None, help="adapters/<이름>.toml")
    parser.add_argument("--project", default=None, help="대상 저장소. `.wiki/` 를 읽는다")
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
    if not prompt:
        return 0

    matched = match_pages(prompt, pages(args.adapter, args.project))
    rules, decisions, rule_parts, repo_parts, trimmed = render_parts(
        matched, budget(args.adapter, RULE_BUDGET, args.project),
        budget(args.adapter, REPO_BUDGET, args.project),
    )
    parts = rule_parts + repo_parts

    # 저장소 문서는 여기서 안 고른다. 목록 전체를 세션 시작에 한 번 싣고,
    # 고르는 일은 그 목록을 이미 들고 있는 쪽이 한다. `tool/session_state.py`.

    loaded = [label(p) for _s, _b, p in rules + decisions]

    # 아무것도 안 걸린 턴도 남긴다. 무엇이 실렸는지만큼 **무엇이 안 실렸는지**가
    # 라우팅의 근거이고, 안 걸린 발화만 모아 보는 것이 미탐을 찾는 유일한 길이다.
    # 읽기와 달리 쓰기는 `.wiki/` 가 아직 없어도 해야 한다. `project_wiki` 는
    # 없으면 None 을 주므로, 갓 붙은 저장소에서 조용히 아무것도 안 남게 된다.
    failed = trajectory.record(
        Path(args.project).expanduser() / ".wiki" if args.project else None,
        prompt,
        loaded,
        sum(len(part) for part in parts),
        str(payload.get("session_id") or ""),
    )
    if failed:
        # 이름만 남긴다. 한글이 섞이면 이 stderr 쓰기가 또 죽는다.
        print(f"trajectory skipped: {failed}", file=sys.stderr)

    if not parts:
        return 0
    body = (
        "다음은 위키가 이 발화에 대해 실은 것이다. 규칙은 어기면 과거에 실제로 "
        "사고가 났던 자리이고, 지식은 이미 정한 것이다.\n\n"
        + source_map(rules, args.project)
        + "\n\n"
        + "\n\n---\n\n".join(parts)
    )
    note = f"위키 주입: {', '.join(loaded[:6])}"
    if trimmed:
        note += f" · 줄임 {trimmed}장"

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": body,
            },
            "systemMessage": note,
        },
        sys.stdout,
        ensure_ascii=False,
    )
    return 0


if __name__ == "__main__":
    # 훅은 무슨 일이 있어도 세션을 멈추면 안 된다. 이름만 남기고 통과시킨다.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
