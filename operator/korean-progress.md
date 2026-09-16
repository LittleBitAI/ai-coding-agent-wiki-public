---
scope: operator
triggers:
- 한국어
- 한글
- 영어로 (적|쓰|나오)
- 진행\s*상황
- 존댓말
- 우리말
slots: []
enforce:
  pretooluse: korean_progress.py
links:
- ask-with-arrow-key-options
- hooks-fail-open
severity: contract
sources: []
---

# 사용자 화면에 뜨는 말은 한국어로

규칙. 도구 설명, 진행 보고, 대화 응답은 한국어로 쓴다. 명령, 경로, 식별자는 원문을 유지한다. 사용자가 다른 출력 언어를 요청하면 그 요청을 따른다.
