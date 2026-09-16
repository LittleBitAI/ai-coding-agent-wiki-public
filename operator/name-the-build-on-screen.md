---
scope: operator
triggers:
- 라이브 (확인|테스트|회차)
- 화면(에서|에|을)? ?(확인|봐|보이|나오)
- 재빌드
- 새로고침
- (또|아직도) (실패|안 ?[되돼]|그렇게)
- 직접 (확인|눌러|해 ?봐)
- 이렇게 나(온|왔)
slots: []
links:
- run-inside-this-session
- diagnose-from-what-ran
- verify-narrow-then-wide
severity: contract
sources: []
---

# 화면을 넘길 때는 그것이 어느 빌드인지 먼저 말한다

규칙. 사용자에게 화면 확인을 요청하기 전에 실행 중인 서버와 화면 빌드의 버전을 확인한다. 확인한 버전과 미확인 부분을 함께 알린다. 소스 수정만으로 실행 중인 화면까지 갱신됐다고 단정하지 않는다.
