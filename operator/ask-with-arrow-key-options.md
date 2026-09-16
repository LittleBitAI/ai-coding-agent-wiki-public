---
scope: operator
triggers:
- 방향키
- 선택지로
- 선택지를
- 골라\s*줘
- 어느\s*쪽으로
slots: []
enforce:
  deny:
  - request_user_input_async
  - functions.request_user_input_async
links:
- korean-progress
severity: contract
sources: []
---

# 판단이 필요하면 산문으로 묻지 말고 선택지로

규칙. 사용자의 선택이 필요한 질문은 현재 호스트가 제공하는 선택형 질문 도구로 묻는다. Claude Code는 AskUserQuestion, Codex는 해당 세션에서 허용된 request_user_input을 사용한다.

이 규칙 묶음은 request_user_input_async를 차단한다. 도구가 없거나 호출이 거부되면 그 사실을 알리고 가능한 질문 방식으로 진행한다. 상위 지시와 도구의 허용 범위를 따른다.
