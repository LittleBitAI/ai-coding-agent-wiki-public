---
scope: craft
triggers:
- 주석
- docstring
- 독스트링
- line ?length
- 줄 ?길이
- 리팩터|리팩토링
slots: []
links:
- diagnose-from-what-ran
- do-the-whole-instruction
severity: contract
sources: []
---

# 주석은 이유를 들고, 이력은 안 든다

규칙. 주석에는 코드만 읽어서는 알 수 없는 이유와 제약을 적는다. 코드 동작을 반복 설명하기보다 이름과 구조를 명확히 한다. 문장은 의미가 이어지는 단위로 줄을 나눈다.
