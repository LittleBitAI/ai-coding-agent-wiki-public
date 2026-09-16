---
scope: operator
triggers:
- 멈추지\s*마
- 왜\s*(자꾸\s*)?멈추
- 돌리고\s*있
- 계속\s*(해|진행)
- 다음은
- 이어서
- 쭉\s*진행
slots: []
links:
- korean-progress
- pick-up-async-results
- ask-with-arrow-key-options
severity: contract
sources: []
---

# 보고는 하되 턴을 끝내지 마라

규칙. 이번 응답에서 수행하겠다고 알린 일은 같은 응답에서 시작한다. 중간 보고와 작업 완료를 구분한다. 사용자 입력이 필요한 경우 필요한 정보와 이유를 명시한다.
