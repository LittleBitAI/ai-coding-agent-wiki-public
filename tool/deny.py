"""PreToolUse: the pages' `enforce.deny`, judged by a script instead of the host.

A per-project install writes these into `permissions.deny`, where they apply
to that checkout. The user-level install cannot: `~/.claude/settings.json`
applies to every directory on the machine, including repositories that never
attached this wiki. Behind `hook.py` the same rules reach only attached
projects. Codex has no deny list at all and chains this from `codex_pretool`.
"""

# First, so the wait on the other imports and on stdin is already being watched.
import hook_diagnostics  # noqa: F401
from fnmatch import fnmatchcase
import json
import sys


def verdict(payload: dict) -> dict | None:
    from apply import declared

    given = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    command = str(given.get("command") or "").strip()
    denies, _ = declared()
    # Blocking a whole tool and blocking a Bash argument pattern read the same
    # `enforce.deny` declaration.
    # ponytail: only the declared pattern of the direct command is matched. A
    # nested shell or a command built at runtime gets past it, and making this
    # a security boundary means enforcing it in the host's execution policy.
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
    return None


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
