---
scope: operator
triggers:
- pwsh
- powershell
- 파워\s*셸
- 파워쉘
- Start-Process
- 서버를? (띄|올|켜|실행|재시작)
- server 를? (띄|올|켜)
- uvicorn
- npm run dev
- 런처
- \.cmd 를?
- 이 셀(에서|에|안)
- 백그라운드로 (띄|돌)
slots:
- server_stop
enforce:
  deny:
  - Bash(powershell -*)
  - Bash(powershell.exe*)
links:
- after-merge-cleanup
- pick-up-async-results
- hooks-fail-open
- name-the-build-on-screen
severity: contract
sources: []
---

# 셸은 `pwsh` 이고, 서버는 이 셀에서 띄운다

규칙. 서버는 종료할 수 있는 관리된 세션에서 실행하고 PID와 포트를 기록한다. 사용자 요청 없이 새 창을 열거나 사용자가 실행한 서버를 종료하지 않는다.

종료 방법: {server_stop}

Windows의 백그라운드 프로세스는 숨김 창으로 실행한다. 실행한 프로세스의 소유자와 작업 범위를 확인한 뒤 종료한다.
