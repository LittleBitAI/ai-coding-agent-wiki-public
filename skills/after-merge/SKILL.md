---
name: after-merge
description: Check merge completion and safely tidy the authorized working area.
---

# 머지 뒤 확인

`operator/after-merge-cleanup`과 `craft/destructive-git-guards`를 따른다.
실제 머지 상태와 남은 커밋을 확인한다. 미커밋 작업과 사용자가 실행한 서버를 보존한다.
삭제가 허용된 임시 파일·브랜치만 확인 후 정리한다. 완료한 일과 남은 일을 보고한다.
