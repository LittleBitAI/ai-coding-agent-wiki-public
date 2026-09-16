---
scope: craft
triggers:
- 리뷰\s*루프
- review\s*loop
- 기싸움
- 안 ?받
- 안 ?읽
- 왜 안
- 감시
- 폴링
- 자동으로 (감지|받|보내)
- 라운드\s*\d+\s*(결과|보냈|왔)
slots: []
links:
- codex-review-loop
- declared-continuation
- verify-narrow-then-wide
- report-without-stopping
severity: contract
sources: []
---

# 비동기 결과는 도착하면 곧바로 받는다

규칙. 결과를 기다리는 작업은 보내기 전에 결과를 받을 위치와 감시 방법을 정한다. 결과 파일의 작업 번호와 작성 시점을 확인하고, 오래된 파일을 새 결과로 읽지 않는다. 완료됐다는 안내만 보고 실제 결과 확인을 생략하지 않는다.
