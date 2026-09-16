---
scope: craft
triggers:
- 머지했다
- 머지 완료
- merge 완료
- 브랜치.{0,6}정리
- 브랜치를 (모두|전부)?\s*지워
- 복귀하고
- 잔여물
- (그리고|또한|그 ?다음|아울러)[ ,]{0,2}[^\n?!]{0,80}(\?|해라|해줘|하라|알려줘|어떻게 생각)
slots: []
links:
- after-merge-cleanup
- declared-continuation
- comments-carry-why
severity: contract
sources: []
---

# 시킨 것을 끝까지 한다 — 나머지를 다시 시키게 하지 마라

규칙. 요청에 여러 항목이 있으면 각각의 완료 여부를 확인한다. 한 항목이 막혀도 독립적으로 할 수 있는 나머지는 진행한다. 끝내지 못한 항목과 이유를 명시하고 범위를 조용히 줄이지 않는다.
