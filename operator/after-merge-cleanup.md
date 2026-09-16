---
scope: operator
triggers:
- 머지
- merge
- 브랜치.*정리
- 정리.*브랜치
slots:
- server_stop
- scratch_dirs
links:
- do-the-whole-instruction
- run-inside-this-session
severity: contract
sources: []
---

# 머지 후 정리 — 시키기 전에 한다

규칙. 머지 완료를 확인한 뒤, 요청 범위의 임시 파일과 작업 브랜치를 정리한다. 미커밋 변경과 사용자가 실행한 프로세스를 보존한다.

서버 종료 방법: {server_stop}

임시 작업 위치: {scratch_dirs}

브랜치 삭제는 포함된 커밋과 사용자 허가를 확인한 뒤 수행한다.
