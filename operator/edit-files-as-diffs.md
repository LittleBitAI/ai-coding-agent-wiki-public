---
scope: operator
triggers:
- edit\s*(만|diff)
- diff\s*(로|형태|방식)
- ran\s*(형식|으로)\s*(수정|하지|작성)
- 스크립트로\s*(수정|고쳐|바꾸)
- sed\s+-i
- here-?string
slots: []
enforce:
  deny:
  - Bash(sed -i*)
  - Bash(perl -pi*)
  - Bash(perl -i*)
  - Bash(perl -0pi*)
  - Bash(dos2unix*)
  - Bash(unix2dos*)
  pretooluse: edit_as_diff.py
links:
- destructive-git-guards
severity: contract
sources: []
---

# 파일은 diff 로 고친다 — 스크립트로 다시 쓰지 마라

규칙. 기존 파일은 변경 전후를 확인할 수 있는 패치로 수정한다. 파일 전체를 다시 쓰거나 셸 치환으로 미커밋 내용을 덮어쓰지 않는다. 새 파일을 만들 때에도 UTF-8 without BOM과 LF를 사용한다.
