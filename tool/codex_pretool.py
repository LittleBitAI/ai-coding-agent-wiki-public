"""Codex PreToolUse: the shared wiki's command blocks and its own checks, together."""

# First, so the wait on the other imports and on stdin is already being watched.
import hook_diagnostics  # noqa: F401
from fnmatch import fnmatchcase
import json
from pathlib import Path
import sys

def verdict(payload: dict) -> dict | None:
    from apply import declared
    import edit_as_diff
    import english_progress
    import markdown_emphasis

    given = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    command = str(given.get("command") or "").strip()
    denies, _ = declared()
    # Blocking a whole tool and blocking a Bash argument pattern read the same
    # `enforce.deny` declaration.
    # ponytail: only the declared pattern of the direct command is matched. A
    # nested shell or a command built at runtime gets past it, and making this
    # a security boundary means enforcing it in Codex's execution policy.
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
    # Codex takes one PreToolUse hook, so the checks are chained here. On
    # Claude `apply.py` wires each one separately out of a page's
    # `enforce.pretooluse`.
    return markdown_emphasis.verdict(payload) or english_progress.verdict(payload)


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
