---
scope: craft
triggers:
- 이어서 (하|진행)
- 계속 (하|진행)
- 이어서 하고 있는가
- 진행중인가
- 돌고 있는가
- 하겠습니다
- Stop 훅
- stop hook
slots: []
links:
- do-the-whole-instruction
- hooks-fail-open
- pick-up-async-results
severity: contract
sources: []
---

# 이어서 하겠다고 적었으면 그 응답에서 이어서 한다

규칙. 이번 응답에서 바로 실행하겠다고 썼다면 도구 호출 없이 턴을 끝내지 않는다. 완료 보고, 조건부 계획, 사용자 입력 대기는 실행 약속과 구별한다. Stop 훅 검사는 실제 호스트 이벤트 전달과 별도로 확인한다.
