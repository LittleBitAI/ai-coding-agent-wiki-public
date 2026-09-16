---
scope: craft
triggers:
- async|비동기
- 이벤트\s*루프|event\s*loop
- 커넥션\s*풀|연결\s*풀|connection\s*pool
- 클라이언트(를|가|는|도)?\s*(만들|들이|공유|캐시|닫|재사용)
- 리팩터|리팩토링
- SDK|httpx|AsyncOpenAI
- 라이프\s*스팬|lifespan|생명\s*주기
- 누수|leak
slots: []
links:
- screen-ownership-before-wiring
- diagnose-from-what-ran
- comments-carry-why
- verify-narrow-then-wide
severity: contract
sources: []
---

# 새 클라이언트를 들이면 생성·공유·닫기·소유를 같이 설계한다

규칙. 연결을 가진 클라이언트를 만들 때 생성, 공유 범위, 동시 사용, 종료 방법을 같은 변경에서 정한다. 연결 풀은 유효한 이벤트 루프 안에서 사용하며 정상 종료와 실패 경로에서 자원을 해제한다.
