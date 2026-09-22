---
scope: craft
severity: landmine
triggers: ["missing|not found|_missing", "state_missing", "왜 (안 되|안 나|없)", "어댑터|adapter", "선택자|selector", "DOM", "안 그려", "렌더", "리셋|reset", "건너뛰|스킵|skip"]
slots: []
sources: []
sources_withheld: true
links: [diagnose-from-what-ran, do-the-whole-instruction, verify-narrow-then-wide]
---

# 오류 이름은 증상이 난 자리를 가리킨다. 원인이 있는 자리가 아니다

규칙. `X_missing` 이 나오면 X 를 찾은 주체가 무엇을 보고 있었는지 먼저 확인한다.
X 가 없다고 결론 내리기 전에, 그 조회가 향한 대상이 내가 생각한 그 대상인지 본다.
그리고 그 실패가 막은 것이 규칙이면, 규칙을 건너뛰지 않는다.

어겼을 때. **멀쩡한 것을 고치려 든다.**

## 더 비싼 절반 — 막힌 규칙을 건너뛰었다

규칙이 도구 실패로 막히는 것은 규칙의 예외가 아니라 도구의 결함이다.
[[do-the-whole-instruction]] 이 "막힌 것을 이름과 이유로 말한다" 고 적은 것은
말하고 넘어가라는 뜻이 아니다.

## 순서

1. 조회의 대상을 먼저 확인한다. 무엇을 못 찾았나가 아니라, 어디서 찾았나.
   생성자·설정·인자에 그 대상을 정하는 값이 있으면 그것부터 본다.
2. 대상이 맞는지 직접 본다. 코드를 읽어 추론하지 말고 그 화면·그 응답을 연다.
   [[diagnose-from-what-ran]] 이 같은 말을 실행 기록에 대해 한다.
3. 폴백을 의심한다. "없으면 다른 걸 쓴다" 는 분기는 실패를 다른 이름으로
   바꿔 놓는다. 조용한 폴백은 오진의 공장이다.
4. 막힌 규칙은 우회하지 않는다. 우회한 회차는 나중에 버려야 하므로, 그것은
   시간을 아끼는 것이 아니라 두 번 쓰는 것이다.

## 나란히 있는 것

폴백이 실패를 감추는 같은 모양이 [[hooks-fail-open]] 과
`run-inside-this-session` 에도 있다. 셋이 한 문장으로 요약된다 —
안 도는 것보다 나쁜 것은 안 도는데 도는 줄 아는 것이다.
