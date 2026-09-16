"""PreToolUse 훅 — 사용자에게 보이는 진행 설명이 한국어가 아니면 막는다."""

from __future__ import annotations

import json
import re
import sys

# 설명이 사용자 화면에 그대로 뜨는 도구만 본다. 프롬프트나 파일 내용은 안 본다.
WATCHED = {"Bash", "Agent", "Task"}
HANGUL = re.compile(r"[가-힣]")

REASON = (
    "진행 설명은 한국어로 쓴다. 이 문장은 사용자 화면에 그대로 뜬다.\n"
    "받은 설명: {description}\n"
    "같은 도구 호출을 설명만 한국어로 바꿔 다시 하라. "
    "명령·경로·식별자는 영어 그대로 두고 설명하는 말만 한국어로."
)


def verdict(payload: dict) -> dict | None:
    """막아야 하면 훅 출력, 아니면 None."""

    if str(payload.get("tool_name")) not in WATCHED:
        return None
    description = str((payload.get("tool_input") or {}).get("description") or "")
    if not description.strip() or HANGUL.search(description):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON.format(description=description),
        },
        "systemMessage": "진행 설명이 영어라 막았다",
    }


def main() -> int:
    # 판정 대상도 차단 사유도 한글이다. 인코딩을 환경에 안 맡긴다.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        payload = json.load(sys.stdin)
        answer = verdict(payload if isinstance(payload, dict) else {})
    except Exception:
        return 0  # 통과. 훅이 깨져서 작업이 멈추면 안 된다.
    if answer:
        json.dump(answer, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    # 첫머리의 규칙을 `main` 밖까지 덮는다. 무엇이든 잘못되면 통과시킨다.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
