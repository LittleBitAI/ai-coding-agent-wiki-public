"""Prove this hook reverts only under its own conditions."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from declared_continuation import verdict  # noqa: E402


def _transcript(blocks: list[tuple[str, str]]) -> str:
    lines = [json.dumps({"type": "user", "message": {"content": "가라"}})]
    for kind, value in blocks:
        block = (
            {"type": "text", "text": value}
            if kind == "text"
            else {"type": "tool_use", "name": value}
        )
        lines.append(
            json.dumps(
                {"type": "assistant", "message": {"content": [block]}},
                ensure_ascii=False,
            )
        )
    path = Path(tempfile.mkdtemp()) / "transcript.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# The first two are sentences that actually came out of the session this hook
# was written for.
CASES: list[tuple[str, list[tuple[str, str]], bool, bool]] = [
    ("약속만 남기고 끝냄", [("text", "나머지 셋과 P2 를 이어서 하겠습니다.")], False, True),
    ("사용자가 물어서 재개", [("text", "아니요, 턴을 끝냈습니다. 지금 이어서 하겠습니다.")], False, True),
    ("약속 뒤에 도구를 부름", [("text", "이어서 하겠습니다."), ("tool", "Bash")], False, False),
    ("결과가 나오면 (미룸)", [("text", "게이트 결과가 나오면 이어서 진행하겠습니다.")], False, False),
    ("알림이 오면 (미룸)", [("text", "끝나면 알림이 오는 대로 이어서 하겠습니다.")], False, False),
    ("질문으로 끝남", [("text", "둘 중 어느 쪽으로 갈까요?")], False, False),
    ("약속이 없음", [("text", "게이트 여섯 전부 초록입니다.")], False, False),
    ("이미 한 번 되돌렸음", [("text", "이어서 하겠습니다.")], True, False),
    # The four below are shapes that really did leak through in the
    # 2026-09-07 session. Six fixed endings meant `올리겠습니다` and
    # `돌리겠습니다` went unseen, and without an immediacy adverb they were
    # not counted as promises at all.
    ("어미가 목록 밖 — 올리겠습니다", [("text", "두 PR 을 올리겠습니다.")], False, True),
    ("어미가 목록 밖 — 돌리겠습니다", [("text", "게이트 여섯을 각 브랜치에서 돌리겠습니다.")], False, True),
    # Writing that it will ask and then not asking is the worst of these. No
    # work was done and no question was left, so the person cannot even tell
    # what is being waited on.
    (
        "묻겠다고만 하고 안 물음",
        [("text", "결과와 함께 PR 을 열어도 될지 여쭙겠습니다.")],
        False,
        True,
    ),
    (
        "묻겠다고 하고 실제로 물음",
        [("text", "PR 을 열어도 될지 여쭙겠습니다."), ("tool", "AskUserQuestion")],
        False,
        False,
    ),
    # After the widening, a deferral and a turn ending on a question still
    # have to pass.
    ("어미는 넓지만 미룸", [("text", "리뷰 결과가 도착하면 PR 을 올리겠습니다.")], False, False),
    ("서술이지 약속이 아님", [("text", "이 값은 축약 패스를 돌립니다.")], False, False),
    # After progress reporting flipped to English. Watching only the Korean
    # endings switches this hook off entirely: an English promise has no ending
    # to match, it has an opening.
    ("영어 약속만 남김", [("text", "I'll run the remaining three gates.")], False, True),
    ("영어 약속 뒤에 도구", [("text", "Let me run the gates."), ("tool", "Bash")], False, False),
    ("영어 서술은 약속이 아님", [("text", "I ran the gates and all six are green.")], False, False),
    ("영어지만 미룸", [("text", "I'll open the PR once the review lands.")], False, False),
    ("영어 질문으로 끝남", [("text", "Which of the two should I take?")], False, False),
    # Saying it will ask and then not asking is the same failure in English.
    ("영어로 묻겠다고만 함", [("text", "I'll ask whether to open the PR.")], False, True),
    (
        "영어로 묻겠다고 하고 실제로 물음",
        [("text", "Let me ask which one you want."), ("tool", "AskUserQuestion")],
        False,
        False,
    ),
    # Handing the turn back is not a promise, and that line ends most turns.
    ("사용자에게 넘기는 말", [("text", "Six gates are green. Let me know if you want more.")], False, False),
]


def main() -> int:
    # The planted sentences and the finding messages are both Korean. The
    # encoding is not left to the environment.
    sys.stdout.reconfigure(encoding="utf-8")

    failed: list[str] = []
    print("Stop 훅 — 심은 문장에서만 되돌리는가\n")
    for label, blocks, active, expected in CASES:
        answer = verdict(
            {"transcript_path": _transcript(blocks), "stop_hook_active": active}
        )
        blocked = answer is not None
        mark = "통과 " if blocked == expected else "실패 "
        print(f"  {mark} {'되돌림' if blocked else '그냥 끝'}  {label}")
        if blocked != expected:
            failed.append(label)

    missing = [
        name
        for name in ("transcript_path", "stop_hook_active")
        if verdict({name: ""}) is not None
    ]
    print(f"\n  {'통과 ' if not missing else '실패 '} 입력이 모자라면 그냥 끝낸다")
    failed.extend(missing)

    print()
    if failed:
        print(f"{len(failed)}건이 기대와 달랐다: {failed}")
        return 1
    print("훅이 자기 조건에서만 되돌린다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
