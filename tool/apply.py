"""apply — 위키를 대상 저장소에 붙인다."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from inject import WIKI, adapter_path, slots_for  # noqa: E402
from wikilib import front_matter  # noqa: E402

HOOK_MARK = "tool/inject.py"
SESSION_MARK = "tool/session_state.py"
SYNC_MARK = "tool/sync.py"
CONTINUATION_MARK = "tool/declared_continuation.py"


def declared() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """페이지가 선언한 deny 규칙과 PreToolUse 스크립트.

    어느 페이지에서 왔는지 같이 든다. 강제가 어느 규칙에서 나왔는지 못 대면
    나중에 그 규칙을 지울 때 강제가 남는다.
    """

    denies: dict[str, list[str]] = {}
    scripts: dict[str, list[str]] = {}
    for scope in ("operator", "craft"):
        directory = WIKI / scope
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            meta, _body = front_matter(path.read_text(encoding="utf-8"))
            enforce = meta.get("enforce")
            if not isinstance(enforce, dict):
                continue
            page = f"{scope}/{path.stem}"
            for rule in enforce.get("deny") or []:
                denies.setdefault(str(rule), []).append(page)
            script = enforce.get("pretooluse")
            if script:
                scripts.setdefault(str(script), []).append(page)
    return denies, scripts


def unfilled(adapter: str | None, project: Path | None = None) -> dict[str, list[str]]:
    """채워지지 않은 슬롯. 주입될 페이지의 것만 본다."""

    values = slots_for(adapter, project)
    missing: dict[str, list[str]] = {}
    for scope in ("operator", "craft"):
        directory = WIKI / scope
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            meta, body = front_matter(path.read_text(encoding="utf-8"))
            if str(meta.get("severity")) not in ("landmine", "contract"):
                continue
            for name in sorted(set(meta.get("slots") or [])):
                if name not in values:
                    missing.setdefault(name, []).append(f"{scope}/{path.stem}")
    return missing


def hook_entry(python: str, adapter: str | None, project: str = "") -> dict:
    where = f' --project "{project}"' if project else ""
    selection = f' --adapter "{adapter}"' if adapter and not (
        project and (Path(project) / ".wiki/adapter.toml").exists()
    ) else ""
    return {
        "hooks": [
            {
                "type": "command",
                "command": (
                    f'"{python}" "{(HERE / "inject.py").as_posix()}"'
                    f"{selection}{where}"
                ),
                "timeout": 10,
                "statusMessage": "위키 확인",
            }
        ]
    }


def session_entry(python: str, project: str) -> dict:
    return {
        "hooks": [
            {
                "type": "command",
                "command": (
                    f'"{python}" "{(HERE / "session_state.py").as_posix()}"'
                    f' --project "{project}"'
                ),
                "timeout": 15,
                "statusMessage": "위키: 현재 상태",
            }
        ]
    }


def sync_entry(python: str, project: str) -> dict:
    """위키를 저장소 상태에 맞추는 훅. 일이 끝날 때 돈다."""

    return {
        "hooks": [
            {
                "type": "command",
                "command": (
                    f'"{python}" "{(HERE / "sync.py").as_posix()}"'
                    f' --project "{project}" --quiet'
                ),
                "timeout": 30,
                "statusMessage": "위키 갱신",
            }
        ]
    }


def continuation_entry(python: str) -> dict:
    """이어서 하겠다고 적고 도구를 안 부른 턴을 되돌리는 훅.

    `--project` 를 안 받는다. 판정에 필요한 것은 전사 경로뿐이고 그것은 훅이
    stdin 으로 받으므로, 경로를 인자로 주면 두 곳이 같은 것을 말하게 된다.
    """

    return {
        "hooks": [
            {
                "type": "command",
                "command": (
                    f'"{python}" "{(HERE / "declared_continuation.py").as_posix()}"'
                ),
                "timeout": 10,
                "statusMessage": "이어서 한다고 적었나",
            }
        ]
    }


def script_entry(python: str, script: str, status: str) -> dict:
    return {
        "hooks": [
            {
                "type": "command",
                "command": f'"{python}" "{(HERE / script).as_posix()}"',
                "timeout": 10,
                "statusMessage": status,
            }
        ]
    }


def put_hook(settings: dict, event: str, mark: str, entry: dict) -> list[str]:
    """한 이벤트에 훅 하나를 건다. 같은 스크립트가 이미 있으면 명령만 갱신한다.

    이름이 아니라 명령 안의 스크립트 경로로 자기 것을 알아본다. 이름으로
    찾으면 사용자가 붙인 훅과 구별이 안 되고, 그러면 남의 훅을 덮는다.
    """

    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    for group in groups:
        for existing in group.get("hooks", []):
            if mark in str(existing.get("command", "")):
                wanted = entry["hooks"][0]
                if any(existing.get(k) != v for k, v in wanted.items() if k != "statusMessage"):
                    existing.update(wanted)
                    return [f"{event} 훅 명령 갱신: {mark}"]
                return []
    groups.append(entry)
    return [f"{event} 훅 추가: {mark}"]


def merge(
    settings: dict,
    denies: list[str],
    hook: dict,
    scripts: dict[str, dict] | None = None,
    session: dict | None = None,
    sync: dict | None = None,
    continuation: dict | None = None,
) -> list[str]:
    """설정에 합치고 무엇을 더했는지 돌려준다. 기존 값은 안 건드린다."""

    changes: list[str] = []

    permissions = settings.setdefault("permissions", {})
    existing = permissions.setdefault("deny", [])
    for rule in denies:
        if rule not in existing:
            existing.append(rule)
            changes.append(f"deny 추가: {rule}")

    changes += put_hook(settings, "UserPromptSubmit", HOOK_MARK, hook)
    for script, entry in sorted((scripts or {}).items()):
        changes += put_hook(settings, "PreToolUse", script, entry)
    if session:
        changes += put_hook(settings, "SessionStart", SESSION_MARK, session)
    if sync:
        changes += put_hook(settings, "Stop", SYNC_MARK, sync)
    if continuation:
        changes += put_hook(settings, "Stop", CONTINUATION_MARK, continuation)
    return changes


def configure(settings: dict, project: Path, adapter: str | None, python: str, agent: str) -> list[str]:
    """설치와 드리프트 검사가 같은 배선 정의를 쓴다."""
    where = project.as_posix()
    denies, scripts = declared()
    if agent == "codex":
        entries = [
            ("UserPromptSubmit", HOOK_MARK, hook_entry(python, adapter, where)),
            ("SessionStart", SESSION_MARK, session_entry(python, where)),
            ("PreToolUse", "tool/codex_pretool.py",
             script_entry(python, "codex_pretool.py", "위키: 도구 실행 검사")),
            ("Stop", SYNC_MARK, sync_entry(python, where)),
            ("Stop", CONTINUATION_MARK, continuation_entry(python)),
        ]
        changes = []
        for event, mark, entry in entries:
            if sys.platform == "win32":
                # Codex는 PowerShell로 실행한다. 따옴표 경로는 & 없이는 문자열이다.
                entry["hooks"][0]["command"] = "& " + entry["hooks"][0]["command"]
            if mark == CONTINUATION_MARK:
                entry["hooks"][0]["command"] += " --codex"
            if event in ("SessionStart", "UserPromptSubmit"):
                # 실측 주입은 최대 약 2만 자다. 기본 2,500 토큰이면 규칙이
                # 파일 미리보기로 바뀌므로 여유를 두되 무제한으로 풀지는 않는다.
                entry["hooks"][0]["additionalContextLimit"] = 12000
            changes += put_hook(settings, event, mark, entry)
    else:
        changes = merge(
            settings,
            list(denies),
            hook_entry(python, adapter, where),
            {s: script_entry(python, s, "진행 설명 확인") for s in scripts},
            session_entry(python, where),
            sync_entry(python, where),
            continuation_entry(python),
        )

    return changes


def installed_agents(project: Path) -> list[str] | None:
    """이 PC의 선택. 설정 전체가 지워져도 설치 기대값은 남는다."""
    path = project / ".wiki/installed-agents.json"
    if not path.exists():
        return None
    agents = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(agents, list) or not agents or any(a not in ("claude", "codex") for a in agents):
        raise ValueError(f"설치 호스트 목록이 잘못됐다: {path}")
    return agents


def wiring_drift(project: Path, agents: tuple[str, ...] | None = None) -> list[tuple[str, str]]:
    """읽기 전용. 어댑터의 기대 에이전트, 미등록 프로젝트는 설치된 에이전트를 본다."""
    project = project.resolve()
    paths = {"claude": project / ".claude/settings.json", "codex": project / ".codex/hooks.json"}
    if agents is None:
        try:
            source = adapter_path(project.name, project, wiki=WIKI)
            declared_agents = tomllib.loads(source.read_text(encoding="utf-8")).get("agents", []) if source and source.exists() else []
            if not isinstance(declared_agents, list) or any(a not in paths for a in declared_agents):
                raise ValueError("알 수 없는 adapter agents")
            declared_agents = installed_agents(project) or declared_agents
        except (OSError, ValueError, TypeError):
            return [("훅 배선 드리프트", "adapter 또는 설치 호스트 목록을 읽을 수 없다")]
        agents = tuple(declared_agents) or tuple(agent for agent, path in paths.items() if path.exists())
    findings = []
    for agent in agents:
        try:
            settings = json.loads(paths[agent].read_text(encoding="utf-8")) if paths[agent].exists() else {}
            commands = [h.get("command", "") for g in settings.get("hooks", {}).get("UserPromptSubmit", [])
                        for h in g.get("hooks", []) if HOOK_MARK in h.get("command", "")]
            # 실행 파일은 기계별 값이다. 설치된 인터프리터를 보존해 경로 차이 소음을 피한다.
            quoted = re.match(r'(?:&\s*)?"([^"]+)"', commands[0]) if commands else None
            python = quoted[1] if quoted else sys.executable
            adapter_match = re.search(r'--adapter\s+(?:"([^"]+)"|(\S+))', commands[0]) if commands else None
            adapter = (adapter_match[1] or adapter_match[2]) if adapter_match else project.name
            changes = configure(settings, project, adapter, python, agent)
            for event, groups in settings.get("hooks", {}).items():
                for group in groups:
                    if group.get("matcher") not in (None, "", "*") and any(
                        HERE.as_posix() in h.get("command", "") for h in group.get("hooks", [])
                    ):
                        changes.append(f"{event} 위키 훅에 제한 matcher가 있다")
            findings.extend(("훅 배선 드리프트", f"{agent}: {change}") for change in changes)
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            findings.append(("훅 배선 드리프트", f"{agent}: 설정을 읽을 수 없다"))
    return findings


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="위키를 대상 저장소에 붙인다")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--adapter", default=None, help="로컬 adapter가 없는 기존 허브 설치의 이름")
    parser.add_argument("--python", default=sys.executable, help="훅을 돌릴 인터프리터")
    parser.add_argument("--write", action="store_true", help="실제로 쓴다")
    parser.add_argument("--check", action="store_true", help="미적용 변경이 있으면 종료 코드 1")
    parser.add_argument("--agent", choices=("claude", "codex"), default="claude")
    args = parser.parse_args()
    if args.check and args.write:
        parser.error("--check와 --write는 함께 쓸 수 없다")

    project = args.project.expanduser().resolve()
    adapter = args.adapter or project.name
    if not project.is_dir():
        print(f"저장소가 없다: {project}")
        return 2

    print(f"# apply — {project.name}\n")

    # 훅을 돌릴 인터프리터가 위키를 읽을 수 있어야 한다. 못 읽으면 훅은
    # 조용히 아무것도 안 하고, 그게 강제 계층의 가장 나쁜 실패 모양이다.
    probe = subprocess.run(
        [args.python, "-c", "import yaml, tomllib"], capture_output=True
    )
    if probe.returncode != 0:
        print(f"`{args.python}` 이 yaml/tomllib 를 못 읽는다. 훅이 조용히 죽는다.")
        print("`--python` 으로 다른 인터프리터를 대라.")
        return 2

    source = adapter_path(adapter, project)
    if source is None or not source.exists():
        print(f"어댑터가 없다: `adapters/{adapter}.toml`")
        print("슬롯 값 없이 붙이면 페이지가 `{gate_cmd}` 같은 빈칸째로 실린다.\n")

    missing = unfilled(adapter, project)
    if missing:
        print("## 안 채워진 슬롯\n")
        for name, where in sorted(missing.items()):
            print(f"- `{{{name}}}` — {', '.join(where)}")
        print(f"\n`{source}` 의 `[slots]` 에 채워라.\n")

    denies, scripts = declared()
    missing_scripts = [s for s in scripts if not (HERE / s).exists()]
    if missing_scripts:
        print(f"선언된 훅 스크립트가 없다: {', '.join(missing_scripts)}")
        return 2

    settings_path = project / (".codex" if args.agent == "codex" else ".claude") / (
        "hooks.json" if args.agent == "codex" else "settings.json"
    )
    before = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.exists()
        else {}
    )
    kept = len((before.get("permissions") or {}).get("deny") or [])

    settings = json.loads(json.dumps(before))
    changes = configure(settings, project, adapter, args.python, args.agent)

    local = project / ".wiki"
    if local.is_dir():
        knowledge = sorted(local.glob("*.md"))
        records = sorted((local / "decisions").glob("*.md"))
        print("## 프로젝트 위키\n")
        for path in knowledge:
            print(f"- `.wiki/{path.stem}`")
        print(f"- `.wiki/decisions/` — 결정 기록 {len(records)}건\n")
    else:
        print("## 프로젝트 위키\n")
        print("`.wiki/` 가 없다. 규칙은 붙지만 이 저장소의 지식은 안 실린다.")
        print("`tool/harvest.py` 로 결정을 캐고 지식 페이지를 쓰라.\n")

    print("## deny 규칙\n")
    for rule, where in sorted(denies.items()):
        print(f"- `{rule}` ← {', '.join(where)}")
    print(f"\n기존 규칙 {kept}개는 그대로 둔다.\n")

    if scripts:
        print("## PreToolUse 훅\n")
        for script, where in sorted(scripts.items()):
            print(f"- `{script}` ← {', '.join(where)}")
        print()

    print("## 바뀌는 것\n")
    if not changes:
        print("없음. 이미 붙어 있다.")
    for line in changes:
        print(f"- {line}")
    print()

    if not args.write:
        print("`--write` 를 주면 쓴다.")
        drift = wiring_drift(project, (args.agent,)) if args.check else []
        if drift and not changes:
            for _kind, message in drift:
                print(f"- {message}")
        return int(args.check and bool(changes or missing or drift))
    if not changes:
        return 0

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"썼다: {settings_path}")
    if args.agent == "codex":
        print("Codex /hooks에서 새 훅을 검토하고 신뢰해야 실행된다. 신뢰 설정은 자동으로 쓰지 않는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
