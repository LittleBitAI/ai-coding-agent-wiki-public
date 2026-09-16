---
scope: craft
triggers:
- 훅
- hook
- cp949
- UnicodeEncodeError
- UnicodeDecodeError
- 인코딩
- settings\.json
- 주입
- 안 (뜨|붙|실)
slots: []
links:
- korean-progress
- diagnose-from-what-ran
severity: contract
sources: []
---

# 훅은 무슨 일이 있어도 세션을 멈추지 않는다

규칙. 훅 진입점은 예상하지 못한 예외로 세션을 멈추지 않도록 처리하고 진단에는 비밀정보를 남기지 않는다. stdin과 stdout은 UTF-8로 고정한다.

파이썬 CLI 출력도 UTF-8로 고정하고, 텍스트 subprocess는 encoding="utf-8", errors="replace"를 사용한다. 설치된 설정 검사와 실제 호스트가 이벤트를 전달했는지의 확인은 별개다. 의도적인 정책 차단은 예외 처리와 구별한다.
