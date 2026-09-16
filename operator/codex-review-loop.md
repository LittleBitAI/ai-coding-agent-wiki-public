---
scope: operator
triggers:
- 리뷰\s*루프
- review\s*loop
- codex.{0,12}(리뷰|보내|돌려)
- 라운드\s*\d+\s*(를|을)?\s*(보내|전송)
slots:
- review_dir
- gate_cmd
- live_cmd
links:
- pick-up-async-results
- ask-with-arrow-key-options
- agent-delegation
severity: contract
sources: []
---

# Codex 리뷰 루프 — 파일로 오간다, 터미널은 초인종이다

규칙. 리뷰 지시와 결과는 파일로 주고받는다. 지시문은 {review_dir}/<topic>-round-<n>.md에 쓰고 결과 파일 경로를 명시한다. 변경 목적, 검사 결과, 보호할 파일과 범위를 포함한다.

이미 허용된 리뷰어에게 보내기 전에 결과 파일 감시를 준비한다. 지적은 재현해 확인한다. 검사 명령: {gate_cmd}. 실제 동작 확인 방법: {live_cmd}. 외부 전송과 push는 사용자가 허용한 범위에서 수행한다.
