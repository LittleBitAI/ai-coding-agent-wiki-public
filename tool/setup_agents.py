"""checkout의 규칙을 apply.py로 설치한다. 다운로드·호스트 신뢰 변경은 하지 않는다."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

WIKI = Path(__file__).resolve().parents[1]
SETTINGS = {"claude": ".claude/settings.json", "codex": ".codex/hooks.json"}


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=45,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if result.returncode:
        raise ValueError(f"명령 실패 ({result.returncode}): {command[0]}\n{result.stdout}{result.stderr}")
    return result.stdout


def hook_shell(agent):
    if os.name != "nt":
        return ["/bin/sh", "-c"]
    if agent == "codex":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell:
            return [shell, "-NoProfile", "-NonInteractive", "-Command"]
        raise ValueError("Codex hook 실행에 필요한 PowerShell을 찾지 못했습니다.")
    # 이 위키 버전의 Claude 명령은 Git Bash 형식이다. WSL의 bash.exe와 구분한다.
    git = shutil.which("git")
    bash = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if not bash and git:
        # Git for Windows ships git.exe three times -- `cmd/`, `bin/` and
        # `mingw64/bin/` -- and only the install root holds `bin/bash.exe`.
        # One level up reaches it from `cmd/` and lands on `mingw64` from the
        # third, which is the copy PATH points at on a machine that installed
        # the MinGW tools. So walk up instead of assuming a depth. Three levels
        # is the deepest of the three layouts and keeps the search inside the
        # Git install, where a match cannot be WSL's bash.exe.
        for parent in Path(git).resolve().parents[:3]:
            if (parent / "bin/bash.exe").is_file():
                bash = str(parent / "bin/bash.exe")
                break
    if bash and Path(bash).is_file():
        return [bash, "--noprofile", "--norc", "-c"]
    raise ValueError("이 위키 버전의 Claude hooks는 Git for Windows의 Git Bash가 필요합니다. "
                     "설치 후 CLAUDE_CODE_GIT_BASH_PATH를 실제 bash.exe 경로로 지정하세요.")


def install(project, choice, check, allow_dirty=False):
    wiki = WIKI
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 이상이 필요합니다. 새 Python으로 이 명령을 다시 실행하세요.")
    import tomllib

    try:
        import yaml  # noqa: F401 -- apply.py를 읽기 전에 해결 방법을 안내한다.
    except ImportError as error:
        raise ValueError("PyYAML이 없습니다. 프로젝트 가상환경에서 python -m pip install PyYAML 후 재실행하세요. "
                         "공용 위키 README의 팀원 설치 안내를 참고하세요.") from error
    if not (wiki / "tool/apply.py").is_file():
        raise ValueError(f"위키 경로에 tool/apply.py가 없습니다: {wiki}. 완전한 위키 checkout을 사용하세요.")
    for path in (project, wiki, Path(sys.executable)):
        if any(char in str(path) for char in ('"', '$', '`', '\n', '\r')):
            raise ValueError(f"고정 위키의 셸 인용이 지원하지 않는 문자가 경로에 있습니다: {path}. "
                             "따옴표·달러·백틱·줄바꿈 없는 경로로 옮기세요. 공백·한글은 지원합니다.")
    actual = run(["git", "rev-parse", "HEAD"], wiki).strip()
    if project == wiki:
        # 위키가 자기 자신을 대상으로 삼는 경우다. 버전 핀도 dirty 검사도 자기참조가 된다.
        # 커밋할 때마다 핀이 낡고, 도구를 고치는 중에는 늘 dirty다. 설치되는 훅은 어차피
        # 이 작업 트리를 가리키므로 "다른 버전을 쓰고 있는가"라는 물음 자체가 성립하지 않는다.
        revision = actual
        print("자기 설치: 이 checkout의 현재 상태를 그대로 겁니다. 위키 버전 고정 검사는 하지 않습니다.")
    else:
        revision = (project / ".wiki/wiki-revision").read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or actual != revision:
            raise ValueError(f"위키 버전 불일치: 기대 {revision}, 현재 {actual}. "
                             "기존 작업을 보존한 별도 checkout을 준비하세요. 자동 checkout은 하지 않습니다.")
        runtime = ("tool", "operator", "craft", "skills")
        dirty = run(["git", "diff", "--name-only", "HEAD", "--", *runtime], wiki)
        dirty += run(["git", "ls-files", "--others", "--exclude-standard", "--", *runtime], wiki)
        if dirty.strip() and not allow_dirty:
            raise ValueError("고정 버전과 다른 위키 실행 코드·규칙이 있습니다. 깨끗한 별도 checkout을 사용하세요:\n" + dirty)
        if allow_dirty:
            print("개발 검증: --allow-dirty-wiki 사용. 고정 버전의 배포 검증으로 세지 않습니다.")

    # 부모 세션의 테스트용 WIKI_ROOT가 다른 허브를 가리켜도 설치 대상은 이 도구다.
    os.environ["WIKI_ROOT"] = str(wiki)
    from apply import installed_agents, unfilled
    source = project / ".wiki/adapter.toml"
    canonical = tomllib.loads(source.read_text(encoding="utf-8"))
    declared = canonical.get("agents", list(SETTINGS))
    if not isinstance(declared, list) or not declared or any(a not in SETTINGS for a in declared):
        raise ValueError(f"{source}의 agents는 claude/codex 목록이어야 합니다.")
    missing = unfilled(None, project)
    if missing:
        raise ValueError(f"{source}의 안 채워진 슬롯: {', '.join(sorted(missing))}")

    agents = tuple(SETTINGS) if choice == "both" else (choice,)
    if any(agent not in declared for agent in agents):
        raise ValueError(f"선택한 호스트가 {source}의 agents에 없습니다: {choice}")
    configs = {}
    for agent, relative in SETTINGS.items():
        path = project / relative
        configs[agent] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for agent in agents:
        binary = shutil.which(agent)
        if not binary:
            raise ValueError(f"{agent} CLI를 PATH에서 찾지 못했습니다. 해당 호스트의 공식 설치 안내 후 재실행하세요.")
        print(run([binary, "--version"], project).strip())
        shell = hook_shell(agent)
        run([*shell, "exit 0"], project)
        if configs[agent].get("disableAllHooks"):
            raise ValueError(f"{SETTINGS[agent]}에서 disableAllHooks가 켜져 있습니다. 직접 검토 후 해제하세요.")
        if agent == "codex":
            features = run([binary, "features", "list"], project)
            hooks = re.search(r"^hooks\s+(.+?)\s+(true|false)\s*$", features, re.M)
            if not hooks or hooks[1].strip() in ("removed", "deprecated"):
                raise ValueError("이 Codex CLI는 필요한 hooks 기능을 제공하지 않습니다. 공식 지원 버전으로 갱신하세요.")
            config = tomllib.loads((project / ".codex/config.toml").read_text(encoding="utf-8"))
            if config.get("features", {}).get("hooks") is not True:
                raise ValueError("프로젝트 .codex/config.toml의 [features] hooks = true를 검토하세요. 자동 덮어쓰기는 하지 않습니다.")
            for line in features.splitlines():
                if line.startswith(("hooks ", "default_mode_request_user_input ")):
                    print(line)
            print("Codex 프로젝트 신뢰와 /hooks 검토가 필요합니다. 질문 UI는 현재 호스트 도구 명세를 따르며, "
                  "미지원 시 Plan mode 또는 텍스트 선택지를 사용하세요.")

    # 선택하지 않은 기존 설치도 보존한다. 다른 도구를 선택해 재실행해도 제거하지 않는다.
    previous = installed_agents(project) or []
    expected = [agent for agent in SETTINGS if agent in agents or agent in previous or any(
        "tool/inject.py" in hook.get("command", "")
        for group in configs[agent].get("hooks", {}).get("UserPromptSubmit", [])
        for hook in group.get("hooks", [])
    )]
    manifest = project / ".wiki/installed-agents.json"
    if check and previous != expected:
        raise ValueError("설치 호스트 목록이 미설치 또는 선택한 호스트와 다릅니다. --check 없이 설치하세요.")

    files = [manifest, *(project / SETTINGS[agent] for agent in agents)]
    before = {path: path.read_bytes() if path.exists() else None for path in files}
    try:
        # 공용 도구가 설정 구조를 모두 읽은 다음에만 실제 쓰기를 시작한다.
        commands = [[sys.executable, "-X", "utf8", str(wiki / "tool/apply.py"),
                     "--project", str(project), "--agent", agent]
                    for agent in agents]
        if not check:
            for command in commands:
                run(command, project)
            for agent, command in zip(agents, commands):
                run([*command, "--write"], project)
            manifest.write_text(json.dumps(expected) + "\n", encoding="utf-8", newline="\n")
        for agent, command in zip(agents, commands):
            run([*command, "--check"], project)
            print(f"{agent}: apply --check 통과")
    except Exception:
        if not check:
            for path, data in before.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(data)
        raise
    print(f"설치 배선 검사 완료: 위키 기준 {revision}\n"
          "이 명령은 실제 자동 이벤트·선택형 질문 UI를 검증하지 않습니다. 새 세션에서 별도로 확인하세요.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="대상 checkout (기본: 현재 폴더)")
    parser.add_argument("--agent", choices=("claude", "codex", "both"), default="both")
    parser.add_argument("--check", action="store_true", help="설정 쓰기 없이 선택한 호스트의 배선만 검사")
    parser.add_argument("--allow-dirty-wiki", action="store_true", help="미커밋 위키 개발 검증 전용. SHA 일치는 여전히 필수")
    args = parser.parse_args()
    try:
        install(args.project.expanduser().resolve(), args.agent, args.check, args.allow_dirty_wiki)
        return 0
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"설치 실패: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
