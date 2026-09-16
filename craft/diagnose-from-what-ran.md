---
scope: craft
triggers:
- 원인
- 왜 (깨|실패|안 되|안 돌)
- 진단
- 디버깅|디버그
- 회귀|regression
- 갑자기
- 되던 게
- 이상하다
slots: []
links:
- hooks-fail-open
- run-inside-this-session
- ask-with-arrow-key-options
- verify-narrow-then-wide
- error-names-the-symptom-site
severity: contract
sources: []
---

# 무엇이 실제로 돌았는지 먼저 물어라

규칙. 원인을 판단하기 전에 실제 실행된 프로세스, 설정, 버전을 확인한다. 관측과 가설을 구분하고 가설만으로 환경을 초기화하지 않는다. 진단에 쓰는 세션이나 기록을 종료할 수 있는 작업은 영향을 먼저 확인한다.
