---
scope: craft
severity: landmine
triggers: ["훅", "hook", "cp949", "UnicodeEncodeError", "UnicodeDecodeError", "인코딩", "settings\\.json", "주입", "안 (뜨|붙|실)"]
slots: []
sources: []
sources_withheld: true
links: [korean-progress, diagnose-from-what-ran]
---

# 훅은 무슨 일이 있어도 세션을 멈추지 않는다

규칙. 훅 스크립트는 진입점에서 모든 예외를 통과로 바꾸고, `stdin` 과 `stdout` 의
인코딩을 스스로 UTF-8 로 고정한다. 실행 환경이 무엇을 주든 훅의 실패가 그 세션을
못 쓰게 만들어서는 안 된다.

**인코딩 고정은 훅만의 규칙이 아니다 — `tool/*.py` 전부다.** 죽는 조건은 훅이라는
것이 아니라 **stdout 이 파이프인 파이썬** 이고, CLI 도 파이프로 실행된다. 규칙의 이름이
범위를 좁히면 그 좁힌 자리가 다음 사고다.

진입점 가드는 훅만이다. 훅은 실패가 세션을 멈추니까 삼켜야 하고, CLI 는 사람이
결과를 보고 있으니 트레이스백이 오히려 답이다.

어겼을 때. 훅이 조용히 사라진다. 자동화가 안 도는 것보다
나쁜 것은 **안 도는데 도는 줄 아는 것**이다.

## 지키는 방법

- 진입점에서 잡는다. `main` 안의 `try` 는 그 안만 덮는다.
- 예외는 **이름만** stderr 로 남긴다. 메시지에 한글이 섞이면 그 stderr 쓰기가
  또 죽는다. 타입 이름은 ASCII 라 안 죽고, `UnicodeEncodeError` 한 단어면 진단에
  충분하다.
- `stdout` 만 고치면 절반이다. `stdin` 이 깨지면 발화가 트리거에 안 맞아
  **죽지도 않고 아무 일도 안 한다.** 트레이스백조차 안 남으므로 더 찾기 어렵다.
- 종료 코드는 0 으로 돌린다. CLI 는 0 이 아닌 코드를 실패로 표시하고, 실패한
  훅은 사용자 화면에 노이즈를 남긴다.

## 셋째 얼굴 — 남의 stdout 을 읽는 자리

앞의 둘은 **내가 쓰는** stdout 과 **내가 읽는** stdin 이다. 셋째는
`subprocess.run(..., capture_output=True, text=True)` 다 — 자식의 stdout 을
읽는데, 그 디코딩도 로케일이 정한다. 자식이 UTF-8 을 내면 부모가 cp949 로
읽다 `UnicodeDecodeError` 로 죽는다.

`sys.stdout.reconfigure` 는 이것을 못 막는다. 그건 내 스트림이지 파이프가 아니다.

죽는 자리도 다르다. 예외가 `subprocess` 의 리더 **스레드**에서 나고, 그 스레드는
조용히 죽고, `run.stdout` 이 `None` 이 되어 본문이 엉뚱한 줄에서 터진다 —
`TypeError: argument of type 'NoneType' is not iterable`. 인코딩 사고가 인코딩처럼
안 보이는 첫 자리다.

```python
subprocess.run(cmd, capture_output=True, text=True,
               encoding="utf-8", errors="replace")
```

`errors="replace"` 까지가 한 벌이다. 자식이 무엇을 내든 부모가 안 죽는 것이
목적이고, 깨진 글자 몇 개는 진단을 안 막는다.

조건은 파일이 어디 있느냐가 아니다. **파이프에 붙은 파이썬**이고, 한 번 쓰고 버릴
스크립트도 파이프에 붙는다.

## 이제 검사가 있다 — `lint` 의 "인코딩 미고정"

`tool/lint.py::fragile_tools`는 AST의 실제 출력 호출과 UTF-8 고정을 대조한다.
`fragile_io`는 stdin을 읽는 도구의 UTF-8 고정과 운영 도구의 텍스트 subprocess에
`encoding="utf-8", errors="replace"`가 있는지 본다. 바이트 파이프에는 디코딩이 없고,
테스트의 엄격한 디코딩은 잘못된 출력을 발견하는 검사이므로 replace를 강요하지 않는다.

`test_lint.py` 가 그 자리를 지킨다 — 문자열에만 이름이 있는 도구를
심어 빨개지는지 본다. 검사가 자기를 못 보는 자리는 *검사가 있다는 착각* 이 가장 오래
사는 자리다.

진입점 가드도 `missing_hook_guards`가 검사한다. 공통 이벤트 훅과 페이지가 선언한
PreToolUse 훅을 대상으로 하며, 모든 제어 흐름을 증명하는 분석기는 아니다.
`test_wiki_health.py`는 lint와 repo_lint 자신의 출력 고정, stdin 고정, 자식 출력 정책,
진입점 가드를 임시 사본에서 없애 검사가 빨개지는지 확인한다.

## 설치와 실행은 따로 확인한다

허브의 코드와 페이지는 절대 경로로 읽으므로 수정 뒤 다음 실행부터 반영된다.
새 이벤트·훅·Claude deny·명령 옵션은 설정에 복사되므로 `apply --write`가 필요하다.
대상 어댑터의 `agents`가 기대하는 에이전트를 선언한다. 설정 파일 전체가 사라져도
`lint`와 `repo_lint`의 배선 검사는 이를 발견한다. `sync`의 Stop 검진도 같은 검사를 쓴다.

허브 갱신 뒤 해당 저장소에서 두 에이전트의 `apply --check`를 실행한다.
차이가 있으면 해당 에이전트의 `--write`로 갱신하고 다시 검사한다. 허브도 예외가 아니다.
허브 게이트에는 실제 설정 검사가 포함된다. 대상 설정은 허브가 몰래 쓰지 않는다.
게이트의 `lint --check`는 슬롯 값 차이만 종료 코드에서 제외하고 실제 페이지·소스·배선 결함은 실패시킨다.
`apply`의 변경 미리보기는 기본적으로 종료 코드 0이며, 게이트에서는 반드시 `--check`를 쓴다.

배선 검사의 초록은 호스트가 이벤트를 실행했다는 증거가 아니다. Codex의 신뢰와 활성화,
실제 세션의 이벤트 전달은 별도로 확인한다. `trajectory.jsonl`은 주입기의 실행 흔적이며
다른 이벤트의 성공이나 세션 호스트를 식별하지 않는다. 직접 호출과 실제 이벤트를 구별해 기록한다.

`hook_diagnostics.py`는 늦은 실행과 강제 종료만 보존하고 빠른 정상 종료 기록은 지운다.
`watch_hook_timeouts.ps1`도 실행 중인 느린 프로세스만 본다. 둘 다 미설치·미실행이나
빠른 무주입을 잡는 장치가 아니다. 기록이 없다는 이유로 훅이 건강하다고 판정하지 않는다.

## 같은 문장이 진단에서도 쓰인다

이 페이지의 결론 — **안 도는 것보다 나쁜 것은 안 도는데 도는 줄 아는 것이다** — 은
자동화만의 규칙이 아니다. 무언가가 깨진 원인을 확인 없이 정하는 자리에서 같은 모양이
나온다: 모르는데 안다고 여기고, 그 위에서 행동한다. [[diagnose-from-what-ran]] 이 그
쪽 얼굴이고.
