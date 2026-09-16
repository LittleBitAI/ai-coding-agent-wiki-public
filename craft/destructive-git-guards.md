---
scope: craft
triggers:
- reset\s+--hard
- git\s+clean
- checkout\s+--
- git\s+restore
- 되돌려|되돌리
- 작업.{0,4}(날아|잃|사라)
slots: []
enforce:
  deny:
  - Bash(git reset --hard*)
  - Bash(git clean -fdx*)
conflicts_with: []
links:
- edit-files-as-diffs
severity: contract
sources: []
---

# 되돌릴 수 없는 git 은 차단한다

규칙. git reset --hard와 git clean -fdx는 차단한다. git restore나 git checkout --로 파일을 되돌리기 전에는 그 파일의 미커밋 변경을 확인하고 보존한다.

검사를 위해 파일을 바꿔야 한다면 임시 사본을 사용한다. Git 이력은 커밋하지 않은 작업의 복구 수단이 아니다.
