---
scope: operator
triggers:
- (?s).+
slots: []
links:
- codex-review-loop
- do-the-whole-instruction
severity: contract
sources: []
---

# 서브에이전트를 임의로 늘리지 않는다

규칙. 사용자가 명시적으로 요청하지 않았다면 하위 에이전트를 생성하거나 재위임하지 않는다. 사용자가 마련한 별도 리뷰 세션은 임의로 종료하지 않는다. 작업을 전달할 때 대상 세션과 범위를 확인한다.
