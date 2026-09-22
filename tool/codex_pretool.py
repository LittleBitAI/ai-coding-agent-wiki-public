"""Codex PreToolUse: 공유 위키의 명령 차단과 기존 검사를 함께 적용한다."""

import hook_diagnostics  # noqa: F401 -- 다른 import와 stdin 대기부터 관측한다.
from fnmatch import fnmatchcase
import json
from pathlib import Path
import sys

def verdict(payload: dict) -> dict | None:
    from apply import declared
    import edit_as_diff
    import korean_progress
    import markdown_emphasis

    given = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    command = str(given.get("command") or "").strip()
    denies, _ = declared()
    # 도구 전체 차단과 Bash 인자 패턴은 같은 enforce.deny 선언을 읽는다.
    # ponytail: 직접 명령의 선언된 패턴만 대조한다. 중첩 셸과 동적 명령까지
    # 보안 경계로 삼아야 한다면 Codex 실행 정책에서 강제해야 한다.
    for rule in denies:
        blocked = rule == tool
        if tool == "Bash" and rule.startswith("Bash(") and rule.endswith(")"):
            blocked = fnmatchcase(command, rule[5:-1])
        if blocked:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"공유 위키의 차단 규칙: {rule}",
            }}
    answer = edit_as_diff.verdict(payload, Path(str(payload.get("cwd") or Path.cwd())))
    if answer:
        output = answer["hookSpecificOutput"]
        output["permissionDecisionReason"] = output["permissionDecisionReason"].replace(
            "Edit", "apply_patch"
        ).replace("Write", "apply_patch")
        return answer
    # Codex 는 PreToolUse 훅 하나만 걸리므로 여기서 이어 붙인다. Claude 쪽은
    # `apply.py` 가 페이지의 `enforce.pretooluse` 에서 각각 따로 만든다.
    return markdown_emphasis.verdict(payload) or korean_progress.verdict(payload)


if __name__ == "__main__":
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        payload = json.load(sys.stdin)
        answer = verdict(payload) if isinstance(payload, dict) else None
        if answer:
            json.dump(answer, sys.stdout, ensure_ascii=False)
    except Exception as error:
        print(f"hook skipped: {type(error).__name__}", file=sys.stderr)
