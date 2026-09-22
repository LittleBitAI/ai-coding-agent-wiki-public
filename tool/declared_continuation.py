"""Stop hook — revert a turn that said it would continue and then ended.

Two languages on purpose. The patterns that match Korean are Korean because
that is what they read, and the block reason is Korean because the person
reads it — the same boundary `english_progress` draws. Everything written for
whoever maintains this is English.
"""

from __future__ import annotations

# First import of the entry point: it keeps the stack from before whatever
# time limit kills this.
import hook_diagnostics  # noqa: F401
import argparse
import json
import re
import sys
from pathlib import Path

# A promise to do it right now, in this response.
#
# Not a list of verbs. The first version knew six of them (`하겠습니다`,
# `진행하겠습니다`, …) and a session on 2026-09-07 walked past it with
# `올리겠습니다`, `돌리겠습니다` and `여쭙겠습니다`. A list has to be short, and
# what sits outside a short list is the next incident. So the condition is the
# ending itself — `-겠습니다` / `-겠다` / `-겠음`.
_WILL = r"겠(습니다|다|음)"

# An immediacy adverb is enough on its own.
_IMMEDIATE = re.compile(rf"(이어서|계속|바로|지금|곧)[^.\n]{{0,40}}\w*{_WILL}")

# Without the adverb, a sentence that ends on this ending is still a promise
# for this turn. A plain statement does not use it: `돌립니다` does not match
# and `돌리겠습니다` does.
_BARE = re.compile(rf"\w*{_WILL}[.!]?$")


# The same promise in English. The Korean patterns stay: a failed translation
# still comes out as the Korean original, and this hook has to hold on that
# path too.
#
# Korean is caught by how a sentence ends, English by how one starts. Where the
# promise sits in the sentence is opposite in the two languages.
_WILL_EN = r"(?:I['’]?ll|I will|I['’]?m going to|I am going to|[Ll]et me(?! know)|[Ll]et['’]?s)"

_IMMEDIATE_EN = re.compile(
    rf"\b(?:now|next|then|first|continuing|moving on)\b[^.\n]{{0,40}}\b{_WILL_EN}\b",
    re.I,
)

# A sentence that **opens** this way is a promise for this turn. A statement
# does not open that way: `I ran the tests` does not match, and
# `I'll run the tests` does.
_BARE_EN = re.compile(rf"^\s*(?:and\s+|so\s+|okay,?\s+|now\s+)?{_WILL_EN}\b", re.I)


class PROMISE:  # noqa: N801 - callers already say `PROMISE.search`
    @staticmethod
    def search(sentence: str):
        clean = sentence.rstrip()
        return (
            _IMMEDIATE.search(sentence)
            or _BARE.search(clean)
            or _IMMEDIATE_EN.search(sentence)
            or _BARE_EN.search(clean)
        )


# Writing that it will ask and then not asking is the worst shape of this. No
# work was done and no question was left, so the person cannot even tell what
# is being waited on. A turn ending that way should have asked, so a turn that
# called no tool is reverted.
ASK_PROMISE = re.compile(rf"(여쭙|여쭈|묻|물어보|확인받|승인)\w*{_WILL}")

ASK_PROMISE_EN = re.compile(
    rf"{_WILL_EN}\s+(?:\w+\s+){{0,2}}"
    r"(?:ask|check with you|confirm with you|get your|run (?:this|that) by you)",
    re.I,
)

# Words that put it off. In the same sentence, it is not a promise for this
# turn, and reverting would be reverting a turn that is correctly waiting.
DEFERRED = re.compile(
    r"(끝나면|나오면|도착하면|뒤에|다음에|이후에|기다렸다가|알림이|결과가)"
)

DEFERRED_EN = re.compile(
    r"\b(?:once|after|when|as soon as|wait(?:ing)? for|if (?:it|that|you)|"
    r"in the next turn|next session|later)\b",
    re.I,
)

# Both reasons are read by the person watching the turn get reverted, so they
# stay Korean. `english_progress` holds that boundary.
REASON = (
    "이어서 하겠다고 적어 놓고 도구를 하나도 안 부르고 턴을 끝냈다.\n"
    "적은 말: {sentence}\n"
    "그 말대로 지금 이어서 하라. 정말로 사용자 입력이 필요하면 무엇이 필요한지"
    " 한 줄로 묻고 끝내라 — 약속만 남기고 멈추지 마라.\n"
    "\n"
    "멈춰도 되는 자리는 셋뿐이다: 사용자만 정할 수 있는 판단(그때는 선택지로"
    " 묻는다) · 되돌리기 어렵거나 바깥으로 나가는 동작(푸시·머지·배포·삭제) ·"
    " 어느 가정으로 가도 결과물이 무의미해지는 자리. 게이트를 돌리고 검사를"
    " 보고 진단하는 것은 셋 중 어느 것도 아니다."
)

ASK_REASON = (
    "묻겠다고 적어 놓고 묻지 않았다. 일도 안 했고 질문도 안 남겼다.\n"
    "적은 말: {sentence}\n"
    "지금 실제로 물어라 — 선택지로 내되, 답이 없어도 할 수 있는 일은 먼저 하고"
    " 물어라. '묻겠습니다' 로 끝난 턴은 사용자가 무엇을 기다리는지조차 알 수 없다."
)


def _last_assistant_turn(lines: list[str]) -> tuple[str, bool]:
    """The last assistant message's text, and whether a tool ran after it.

    Both are reset by a `tool_use` block, because what matters is the prose
    that closed the turn rather than prose from earlier in it.
    """

    text = ""
    used_tool = False
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:  # noqa: BLE001 - a half-written line is skipped
            continue
        if entry.get("type") == "user":
            text, used_tool = "", False
            continue
        if entry.get("type") != "assistant":
            continue
        content = ((entry.get("message") or {}).get("content")) or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                used_tool = True
                text = ""
            elif block.get("type") == "text":
                text = str(block.get("text") or "")
    return text, used_tool


def verdict(payload: dict, *, codex: bool = False) -> dict | None:
    """The hook output when this has to be reverted, otherwise `None`."""

    if bool(payload.get("stop_hook_active")):
        return None
    if codex:
        # Codex's transcript format is not a published contract. Only the
        # last response Stop hands over is read, rather than guessing at
        # another client's way of recording a session.
        text = payload.get("last_assistant_message")
        if not isinstance(text, str):
            return None
        used_tool = False
    else:
        path = str(payload.get("transcript_path") or "")
        if not path:
            return None
        transcript = Path(path)
        if not transcript.exists():
            return None
        text, used_tool = _last_assistant_turn(
            transcript.read_text(encoding="utf-8", errors="replace").splitlines()
        )
    if used_tool or not text.strip():
        return None
    # Ending on a question is a turn waiting for the person, not one that
    # stopped short.
    tail = text.rstrip()
    if tail.endswith("?") or tail.endswith("？"):
        return None
    for sentence in reversed(re.split(r"(?<=[.!?])\s+|\n+", tail)):
        stripped = sentence.strip()
        if not stripped or not PROMISE.search(stripped):
            continue
        if DEFERRED.search(stripped) or DEFERRED_EN.search(stripped):
            return None
        # Promising to ask and promising to do need different instructions
        # back, so which one it was decides the reason.
        asked = ASK_PROMISE.search(stripped) or ASK_PROMISE_EN.search(stripped)
        reason = ASK_REASON if asked else REASON
        return {
            "decision": "block",
            "reason": reason.format(sentence=stripped[:200]),
        }
    return None


def main() -> int:
    # What is judged and the reason given are both Korean. The encoding is not
    # left to the environment, where the default on this pipe is cp949.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="약속만 남긴 종료를 되돌린다")
    parser.add_argument("--codex", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        answer = verdict(payload if isinstance(payload, dict) else {}, codex=args.codex)
    except Exception:
        return 0  # pass: a broken hook must not stop the work
    if answer:
        json.dump(answer, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    # The rule at the top of this file, extended past `main`. Whatever goes
    # wrong, pass.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
