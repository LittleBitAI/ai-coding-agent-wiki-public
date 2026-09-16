"""이 훅이 자기 조건에서만 되돌리는지 증명한다."""

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


# 첫 둘은 이 훅을 만든 세션에서 실제로 나온 문장이다.
CASES: list[tuple[str, list[tuple[str, str]], bool, bool]] = [
    ("약속만 남기고 끝냄", [("text", "나머지 셋과 P2 를 이어서 하겠습니다.")], False, True),
    ("사용자가 물어서 재개", [("text", "아니요, 턴을 끝냈습니다. 지금 이어서 하겠습니다.")], False, True),
    ("약속 뒤에 도구를 부름", [("text", "이어서 하겠습니다."), ("tool", "Bash")], False, False),
    ("결과가 나오면 (미룸)", [("text", "게이트 결과가 나오면 이어서 진행하겠습니다.")], False, False),
    ("알림이 오면 (미룸)", [("text", "끝나면 알림이 오는 대로 이어서 하겠습니다.")], False, False),
    ("질문으로 끝남", [("text", "둘 중 어느 쪽으로 갈까요?")], False, False),
    ("약속이 없음", [("text", "게이트 여섯 전부 초록입니다.")], False, False),
    ("이미 한 번 되돌렸음", [("text", "이어서 하겠습니다.")], True, False),
    # 아래 넷은 2026-09-07 세션에서 실제로 새어 나간 모양이다. 어미가 여섯 개로
    # 고정돼 있어서 `올리겠습니다`·`돌리겠습니다` 를 못 봤고, 즉시성 부사가
    # 없으면 약속으로도 안 셌다.
    ("어미가 목록 밖 — 올리겠습니다", [("text", "두 PR 을 올리겠습니다.")], False, True),
    ("어미가 목록 밖 — 돌리겠습니다", [("text", "게이트 여섯을 각 브랜치에서 돌리겠습니다.")], False, True),
    # **묻겠다고 적고 안 묻는 것이 가장 나쁘다.** 일도 안 하고 질문도 안 남겨서,
    # 사용자가 무엇을 기다리는지조차 알 수 없다.
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
    # 넓힌 뒤에도 미룸과 질문 종료는 그대로 통과해야 한다.
    ("어미는 넓지만 미룸", [("text", "리뷰 결과가 도착하면 PR 을 올리겠습니다.")], False, False),
    ("서술이지 약속이 아님", [("text", "이 값은 축약 패스를 돌립니다.")], False, False),
]


def main() -> int:
    # 심는 문장도 발견 메시지도 한글이다. 인코딩을 환경에 안 맡긴다.
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
