"""Stop 훅 — 이어서 하겠다고 말해 놓고 끝낸 턴을 되돌린다."""

from __future__ import annotations

import hook_diagnostics  # noqa: F401 -- 진입점의 제한 시간 전 스택 보존
import argparse
import json
import re
import sys
from pathlib import Path

# 이번 응답에서 곧바로 하겠다는 약속.
#
# **동사를 열거하지 않는다.** 첫 판은 여섯 개(`하겠습니다`·`진행하겠습니다` …)만
# 알았고, 2026-09-07 세션이 `올리겠습니다`·`돌리겠습니다`·`여쭙겠습니다` 로 그
# 옆을 통과했다. 목록은 반드시 짧고, 짧은 목록의 바깥이 다음 사고다. 그래서
# 어미 `-겠습니다`/`-겠다`/`-겠음` 자체를 조건으로 둔다.
_WILL = r"겠(습니다|다|음)"

# 즉시성 부사가 있으면 그것만으로 약속이다.
_IMMEDIATE = re.compile(rf"(이어서|계속|바로|지금|곧)[^.\n]{{0,40}}\w*{_WILL}")

# 부사가 없어도, 문장이 이 어미로 **끝나면** 이번 턴의 약속으로 본다. 서술문은
# 이 어미를 안 쓴다 — `돌립니다` 는 걸리지 않고 `돌리겠습니다` 만 걸린다.
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


class PROMISE:  # noqa: N801 - 기존 호출부가 `PROMISE.search` 를 그대로 쓴다
    @staticmethod
    def search(sentence: str):
        clean = sentence.rstrip()
        return (
            _IMMEDIATE.search(sentence)
            or _BARE.search(clean)
            or _IMMEDIATE_EN.search(sentence)
            or _BARE_EN.search(clean)
        )


# **묻겠다고 적고 안 묻는 것**이 가장 나쁜 모양이다. 일도 안 하고 질문도 안
# 남겨서, 사용자는 무엇을 기다리는지조차 알 수 없다. 이 말로 끝났으면 실제로
# 물었어야 하므로, 도구를 하나도 안 불렀다면 되돌린다.
ASK_PROMISE = re.compile(rf"(여쭙|여쭈|묻|물어보|확인받|승인)\w*{_WILL}")

ASK_PROMISE_EN = re.compile(
    rf"{_WILL_EN}\s+(?:\w+\s+){{0,2}}"
    r"(?:ask|check with you|confirm with you|get your|run (?:this|that) by you)",
    re.I,
)

# 뒤로 미루는 말. 이것이 같은 문장에 있으면 이번 턴의 약속이 아니다.
DEFERRED = re.compile(
    r"(끝나면|나오면|도착하면|뒤에|다음에|이후에|기다렸다가|알림이|결과가)"
)

DEFERRED_EN = re.compile(
    r"\b(?:once|after|when|as soon as|wait(?:ing)? for|if (?:it|that|you)|"
    r"in the next turn|next session|later)\b",
    re.I,
)

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
    """마지막 어시스턴트 메시지의 글자와, 그 뒤에 도구 호출이 있었는지."""

    text = ""
    used_tool = False
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:  # noqa: BLE001 - 부분 기록 줄은 건너뛴다
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
    """되돌려야 하면 훅 출력, 아니면 None."""

    if bool(payload.get("stop_hook_active")):
        return None
    if codex:
        # Codex의 전사 파일 형식은 공개 계약이 아니다. Stop이 제공하는
        # 마지막 응답만 읽어 다른 클라이언트의 기록 형식을 추측하지 않는다.
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
    # 질문으로 끝나면 사용자 답을 기다리는 턴이다.
    tail = text.rstrip()
    if tail.endswith("?") or tail.endswith("？"):
        return None
    for sentence in reversed(re.split(r"(?<=[.!?])\s+|\n+", tail)):
        stripped = sentence.strip()
        if not stripped or not PROMISE.search(stripped):
            continue
        if DEFERRED.search(stripped) or DEFERRED_EN.search(stripped):
            return None
        # 묻겠다고 한 것과 하겠다고 한 것은 되돌릴 때 시킬 일이 다르다.
        asked = ASK_PROMISE.search(stripped) or ASK_PROMISE_EN.search(stripped)
        reason = ASK_REASON if asked else REASON
        return {
            "decision": "block",
            "reason": reason.format(sentence=stripped[:200]),
        }
    return None


def main() -> int:
    # 판정 대상도 차단 사유도 한글이다. 인코딩을 환경에 안 맡긴다.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="약속만 남긴 종료를 되돌린다")
    parser.add_argument("--codex", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        answer = verdict(payload if isinstance(payload, dict) else {}, codex=args.codex)
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
