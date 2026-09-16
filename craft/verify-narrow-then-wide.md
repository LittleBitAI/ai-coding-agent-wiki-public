---
scope: craft
triggers:
- 테스트를? (돌|실행)
- pytest
- 전체를? 돌리
- 다 돌리
- 라이브를? (돌|실행)
- 회차를? (돌|실행)
- 게이트
- 검증
- 확인해 ?보
slots: []
links:
- diagnose-from-what-ran
- pick-up-async-results
- do-the-whole-instruction
severity: contract
sources: []
---

# 좁게 재고, 마지막에 넓게 — 수리마다 전부 돌리지 마라

규칙. 개발 중에는 변경한 동작에 직접 관련된 검사를 먼저 실행한다. 관련 검사가 통과하면 배포 범위에 필요한 전체 검사를 수행한다. 설치 검증, 실제 호스트 이벤트, 응답 품질을 서로 다른 결과로 기록한다.
