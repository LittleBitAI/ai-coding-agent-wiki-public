---
scope: operator
severity: landmine
triggers: ["pwsh", "powershell", "파워\\s*셸", "파워쉘", "Start-Process", "서버를? (띄|올|켜|실행|재시작)", "server 를? (띄|올|켜)", "uvicorn", "npm run dev", "런처", "\\.cmd 를?", "이 셀(에서|에|안)", "백그라운드로 (띄|돌)"]
slots: [server_stop]
enforce:
  deny: ["Bash(powershell -*)", "Bash(powershell.exe*)"]
sources: []
sources_withheld: true
links: [after-merge-cleanup, pick-up-async-results, hooks-fail-open, name-the-build-on-screen]
---

# 셸은 `pwsh` 이고, 서버는 이 셀에서 띄운다

규칙 둘. **파워셸이 필요하면 `pwsh` 를 부른다** — `powershell` 은 다른 제품이다.
**서버는 이 셀 안에서 띄운다** — `Start-Process` 도, 분리된 창도, Git Bash 에서
부르는 `.cmd` 도 아니다.

어겼을 때. **실패가 실패로 안 보인다.** 아래 세 자리가 전부 그 모양이다.

## 태운 것 — Git Bash 가 `.cmd` 를 부르면 `exit 0` 이 나온다

런처가 시작조차 안 했는데 종료 코드는 0 이다. 부른 쪽은 성공으로 읽고 다음
걸음으로 간다. 서버가 뜬 줄 알고 라이브 회차를 시작하면 그 회차가 통째로 버려진다.

회차가 버려지는 길은 하나 더 있고, 그것은 띄운 **뒤**에 있다. 이 페이지는 무엇으로
어디에 띄우는가까지만 든다 — 띄운 화면을 사람에게 넘기는 자리는
[[name-the-build-on-screen]] 이 든다.

[[hooks-fail-open]] 과 `declared-continuation` 이 같은 문장으로 요약된다 —
**안 도는 것보다 나쁜 것은 안 도는데 도는 줄 아는 것이다.** 여기서는 종료 코드가
그 거짓말을 한다.

## `powershell` 은 `pwsh` 의 옛 이름이 아니다

이름이 닮아서 별칭처럼 읽히는데 아니다. `ConvertTo-Json` 의 기본 깊이,
`-ErrorAction` 의 전파, `?.`, `Test-Json`, `Invoke-RestMethod` 의 기본 인코딩이
서로 다르다. 읽기만 하는 조회는 교집합에 있어서 우연히 맞고, 그 우연은 다음
명령까지 안 간다.

## 서버는 이 셀이 소유한다

띄우는 것은 **이 셀의 도구로, `pwsh` 로** 한다. 배경으로 돌려야 하면 이 셀의
배경 작업으로 돌린다 — 그러면 끝날 때 알림이 오고, 이 셀이 죽으면 같이 죽고,
정리 걸음이 자기 것으로 알아본다. 그 알림을 받는 규율은
[[pick-up-async-results]] 가 든다: 기다릴 거면 기다리는 장치를 먼저 걸고,
걸기 전에 턴을 끝내지 않는다.

**금지되는 것은 이 셀이 추적할 수 없는 자리에 붙이는 것이다.**
`Start-Process`, 별도 창, 세션이 끝나도 남는 detached 프로세스. 사용자가 직접
실행해야 하는 것이 있으면 넘기지 말고 `!` 접두사로 이 셀에서 치라고 말한다.

### 포트로 확인한다, 프로세스 이름으로 말고

```
{server_stop}
```

머지 후 정리의 "서버를 끈다" 걸음이 여기 걸린다 — [[after-merge-cleanup]].

```powershell
Get-CimInstance Win32_Process -Filter 'ProcessId=<pid>' |
  Select-Object -ExpandProperty CommandLine
```

### `wsl --shutdown` 은 포트 하나를 끄는 명령이 아니다

Windows 에서 Docker Desktop 이 WSL2 위에 있으므로, 이 한 줄은 **이 기계의 모든
컨테이너를 멈춘다** — 남의 프로젝트 것까지.

다른 포트에 띄우고,
`/health` 의 200 이 아니라 **그 응답이 이 프로젝트의 것인지** 를 본다.

## 1층이 막는 것과 못 막는 것

`powershell` 만 명령 모양이다. `permissions.deny` 가 접두로 멈추고, 사다리는
거기서 끝난다.

**나머지 둘은 1층에 못 실린다.** `Start-Process` 는 `pwsh -Command "..."` 의
**안쪽**에 들어가므로 접두 규칙이 닿지 않는다. `.cmd` 를 Git Bash 로 부르는 것은
`.cmd` 자체가 정상적인 파일이라, 어떤 명령 모양으로도 "MSYS 를 거쳤는가" 가 안
보인다.

그래서 이 둘은 이 페이지가 2층으로 드는 산문이다. 막을 수 있는 척하지 않는 것이
요점이다 — 안 먹는 deny 규칙은 이 페이지가 세는 세 가지 조용한 거짓말에 넷째를
더하는 것이다.
