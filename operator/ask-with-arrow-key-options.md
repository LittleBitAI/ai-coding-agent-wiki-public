---
scope: operator
severity: contract
triggers: ["[\\s\\S]"]
slots: []
enforce:
  deny: ["request_user_input_async", "functions.request_user_input_async"]
sources: []
sources_withheld: true
links: [korean-progress]
---

# 판단이 필요하면 산문으로 묻지 말고 선택지로

규칙. 사용자의 판단이 필요한 자리에서는 현재 호스트의 선택형 질문 도구를 쓴다.
Claude Code는 `AskUserQuestion`, Codex는 현재 세션에서 제공되고 해당 용도로 허용된
`request_user_input`이다. **Codex의 `request_user_input_async` 호출은 전면 금지다.**
선택지가 없는 호출도 예외가 아니다. 재발 중요도는 사용자 지정 P0다.

## 실행 환경별로 고른다

| 환경 | 도구 | 확인할 것 |
| --- | --- | --- |
| Claude Code 대화형 세션 | 내장 `AskUserQuestion` | 도구 명세의 `questions`·`options`·`multiSelect`. Codex 실험 설정은 관계없다 |
| Codex | `request_user_input` | 도구 제공 여부와 모드·용도 제한. `header`·`id`·`question`, 선택지의 `label`·`description` |
| Codex 비동기 질문 | `request_user_input_async` | 전면 금지. `functions.request_user_input_async`도 같다 |

- Claude에 Codex 도구나 설정을 적용하지 않는다. 두 도구의 스키마도 서로 복사하지 않는다.
- Codex 기본 모드 지원은 설치 버전과 호스트에 달려 있다. `default_mode_request_user_input`을
  제공하는 버전에서는 이 실험 기능도 확인한다. 활성화만으로 실제 UI가
  확인된 것은 아니다. 세션의 도구 목록과 제한이 우선한다.
- 도구가 없거나 해당 용도가 금지돼 있으면 제한을 밝히고 상위 지침이 허용하는 방식으로
  묻는다. 산문·비동기 질문을 같은 UI라고 설명하지 않는다.
- 권장안을 첫 선택지에 두고 결과·대가를 설명한다. 실제로 제출된 답만 반영한다.
  접수 응답이나 미리 선택된 항목은 답이 아니다.
- 기본값이 명백하면 판단해서 진행한다. 다르게 읽으면 결과가 실질적으로 달라지는
  것만 묻는다. 답이 필요 없는 일은 먼저 끝낸다.
- 잘못 물었으면 같은 판단을 올바른 도구로 다시 묻는다.

## 왜 모든 발화에 싣는가

판단은 에이전트가 답을 쓰면서 생기므로 사용자 발화의 ‘방향키’ 낱말을 기다려서는 늦다.
이제 비어 있지 않은 모든 발화에 짧은 규칙을 싣는다. 이것은 질문 UI 호출을 강제하는
장치나 성공 증명이 아니다. 실제 도구 호출·사용자 응답은 별도로 확인한다.

기존 `enforce.deny`와 `codex_pretool.py`가 두 비동기 이름을 차단한다.

어겼을 때. 사용자가 질문 형식을 다시 지정하고 같은 판단을 두 번 한다.
선택지의 라벨과 설명도 사용자 화면에 뜨는 말이다 — [[korean-progress]].
