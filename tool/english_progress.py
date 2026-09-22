"""PreToolUse hook — deny a progress description that is not in English.

This is the inversion of the rule that came before it. The old one demanded
Korean, because Korean was what the person read. Now the person reads Korean
in the mirror and the agent thinks in English, so the description the agent
writes has to be English or the mirror has nothing to translate and the agent
has spent a turn thinking in the wrong language.

Two things survive the inversion unchanged, and both on purpose. The tools
watched are the same three: a description is only worth a rule when it lands
on the person's screen verbatim. And the refusal itself stays Korean — the
person reads the refusal, not the agent.

Korean is still allowed where it names a Korean thing. The glossary already
holds that list for the translator, and a word that must not be translated is
exactly a word that may stay Korean here. One list, two readers.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The description is what shows up on the person's screen as it is written.
# Prompts and file contents are not this hook's business.
WATCHED = {"Bash", "Agent", "Task"}
HANGUL = re.compile(r"[가-힣]")

REASON = (
    "진행 설명은 영어로 쓴다. 이 저장소는 에이전트가 닿는 면을 영어로 두고, "
    "사람이 읽을 것은 한국어 미러가 옮긴다.\n"
    "받은 설명: {description}\n"
    "같은 도구 호출을 설명만 영어로 바꿔 다시 하라. 용어집의 고유명사는 "
    "한국어로 남겨도 된다."
)


def spared() -> tuple[str, ...]:
    """Korean words the glossary refuses to translate, so this may not deny them.

    Empty on any failure. Fewer spared words means more denials, and a hook
    that denies more when its own data is missing is a hook that stops the
    work it was meant to shape — so the caller treats an empty list as "let
    it through" rather than "deny harder".
    """

    try:
        import translate

        return translate.glossary()[0]
    except Exception:
        return ()


def verdict(payload: dict) -> dict | None:
    """The hook's output when it must block, `None` otherwise."""

    if str(payload.get("tool_name")) not in WATCHED:
        return None
    description = str((payload.get("tool_input") or {}).get("description") or "")
    if not description.strip():
        return None

    keep = spared()
    rest = description
    for word in keep:
        rest = rest.replace(word, "")
    if not HANGUL.search(rest):
        return None
    if not keep:
        # The glossary did not load. A description made entirely of terms it
        # would have spared is indistinguishable from a Korean one here, so
        # this hook does not get to be the one that decides.
        return None

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON.format(description=description),
        },
        "systemMessage": "진행 설명이 한국어라 막았다",
    }


def main() -> int:
    # The refusal is Korean even though the rule is about English. Encoding is
    # not left to the environment.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        payload = json.load(sys.stdin)
        answer = verdict(payload if isinstance(payload, dict) else {})
    except Exception:
        return 0  # pass. A broken hook must not stop the work.
    if answer:
        json.dump(answer, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    # The rule at the top covers more than `main`. Anything goes wrong, it passes.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
