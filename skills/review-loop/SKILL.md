---
name: review-loop
description: Review a change through an already authorized independent reviewer and result files.
---

# 코드 리뷰

`operator/codex-review-loop`와 `craft/pick-up-async-results`를 따른다.
사용자가 허용한 기존 리뷰 세션을 확인하고 지시 파일에 목적, 변경 범위, 검사 결과, 보호할 파일을 적는다.
결과 파일 경로를 지정하고 감시를 준비한 뒤 지시를 전달한다. 하위 에이전트를 임의로 만들지 않는다.
결과 파일의 작업 번호와 시각을 확인한다. 지적은 재현한 후 수정하고 관련 검사를 다시 실행한다.
완료 조건과 남은 문제를 보고한다. push·merge는 사용자에게 허용된 범위에서만 실행한다.
