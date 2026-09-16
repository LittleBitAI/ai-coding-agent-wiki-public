---
scope: craft
triggers:
- missing|not found|_missing
- state_missing
- 왜 (안 되|안 나|없)
- 어댑터|adapter
- 선택자|selector
- DOM
- 안 그려
- 렌더
- 리셋|reset
- 건너뛰|스킵|skip
slots: []
links:
- diagnose-from-what-ran
- do-the-whole-instruction
- verify-narrow-then-wide
severity: contract
sources: []
---

# 오류 이름은 증상이 난 자리를 가리킨다. 원인이 있는 자리가 아니다

규칙. missing 오류가 나면 조회한 대상과 실행 상태부터 확인한다. 오류명만으로 원인을 단정하거나 검사를 건너뛰지 않는다. 실패를 발생시킨 조회와 실제 요구 조건을 따로 확인한다.
