# 훅 시간 초과 자동 진단

10초 뒤 외부에서 죽인 프로세스의 종료 처리만으로는 증거를 남길 수 없다.

## 수집 범위

| 수집기 | 남기는 것 | 시점 |
| --- | --- | --- |
| `hook_diagnostics.py` | 위키 훅 이름, PID·부모 PID, 시작 UTC, Python 전체 스택, 정상 종료 시 경과 시간 | 10초 제한 훅은 8초, 세션 상태는 13초, 갱신은 28초 |
| `watch_hook_timeouts.ps1` | 실제 훅 프로세스 이름, PID·부모 PID, 시작·관측 UTC, 경과 시간, CPU 시간, 메모리, 직접 자식 프로세스 이름·PID | 0.5초 간격으로 관측해 8초를 넘겼을 때 |

파일은 `%LOCALAPPDATA%\wiki-hook-diagnostics\`에 UTF-8 without BOM으로 쓴다.
`wiki-*.log`는 스택, `process-*.log`는 외부 프로세스 관측이다.
Python 정상 단기 실행의 파일은 지운다. 느린 정상 종료는 `completed_ms`를 남긴다.
외부 관측은 프로세스가 사라지면 시각을 추가하지만 **종료 이유는 모른다**고 기록한다.
8초를 넘겼다는 사실을 Codex의 시간 초과 확정으로 해석하지 않는다.

입력 JSON, 발화, 도구 인자, 환경 변수, 토큰은 저장하지 않는다. 외부 수집기는
명령행을 훅 식별에만 사용하고 저장하지 않는다. 스택에는 파일 경로가 포함된다.
최근 60초 파일을 제외한 기록은 7일·최신 100개까지 보관한다. 위키 훅 실행 시와
외부 수집기의 매시간 정리로 적용한다. `observer-error.log`는 수집기 오류 타입만 보관한다.

## 현재 설치와 운영

위키 다섯 진입점은 첫 import에서 수집기를 켠다. 기존 hooks 명령·제한·신뢰 설정은
유지한다. 기록 디렉터리를 쓸 수 없어도 기존 P0 도구 차단은 동작한다.

`pwsh -NoProfile -NonInteractive -WindowStyle Hidden -File <위키>/tool/watch_hook_timeouts.ps1`
같은 로그 디렉터리의 수집기는 mutex로 하나만 실행된다.

```powershell
Get-ScheduledTask -TaskName WikiHookTimeoutObserver
Get-ChildItem "$env:LOCALAPPDATA/wiki-hook-diagnostics" -Filter '*.log'
```

비활성화할 때는 `Stop-ScheduledTask -TaskName WikiHookTimeoutObserver`와
`Disable-ScheduledTask -TaskName WikiHookTimeoutObserver`를 실행한다. 위키를 다른 경로로
옮기면 예약 작업의 `-File` 경로도 갱신해야 한다.

Orca의 `codex-hook.cmd`는 앱이 재생성한다. 따라서 그 파일을 패치하거나 복사본으로 대체하지 않고 외부에서 관측한다.
기존 Orca 원본과 전역 hooks 설정은 유지한다. 추가 훅 신뢰 승인은 필요 없다.

## 검증과 한계

스택은 Python 진입 이후만 보인다. 외부 관측은 시작 셸과 Orca 훅도 식별하지만 네이티브
스택이나 Codex의 실제 종료 판정을 얻지는 않는다. 관측 자체가 OS 부하·권한 문제로
지연되거나 중단되면 기록을 놓칠 수 있다. 원래 오류가 다음에 발생하면 같은 시각의
`process-*.log`와 `wiki-*.log`를 함께 읽는다.
