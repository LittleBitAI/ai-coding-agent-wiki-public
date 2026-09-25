# 3묶음 — 세션 운영 (7~9단계)

전체 설계와 단계 표는 [개요](token-diet.md)에 있다. 7단계의 측정은 [1묶음](token-diet-1-hook.md)의
`replay` 가 한다. 핑 타이머는 [2묶음](token-diet-2-search.md)의 검색 데몬이 겸한다.

목표. 세션을 오래 두었다 돌아올 때 문맥 전체를 캐시에 다시 쓰는 값을 줄이고, 긴 세션이 매 턴 읽는
문맥 자체를 줄인다. 만들기 전에 그런 복귀와 긴 문맥이 실제로 얼마나 있는지부터 잰다.

## 2026-09-25 구체화에서 정한 것

| 질문 | 고른 것 |
| --- | --- |
| keep-alive 범위 | 측정 먼저. 이득이 보이면 Orca 셀부터 구현 |
| 과금 | 구독(Pro/Max). 셈은 돈이 아니라 사용 한도로 적는다 |
| 운영 규칙 페이지 | `operator` 의 `contract`, 좁은 트리거 |

같은 날 확인한 사실. 이 PC 의 Claude Code transcript 는 캐시 쓰기가 전부 `ephemeral_1h_input_tokens`
이고 `ephemeral_5m_input_tokens` 는 0 이다. 1시간 캐시라는 전제가 이 환경에서는 맞다. 이 저장소의
한 세션은 `preTokens` 967,131 에서 자동 compact 됐고 155초가 걸렸다 — 세션이 1M 문맥 끝까지 간다.

## 2026-09-25 두 번째 구체화에서 정한 것

1·2묶음이 머지된 뒤(#22·#23·#24) 측정을 보고 다시 물었다. 위 표의 "keep-alive 범위: 측정 먼저" 는
측정이 나와 이 표가 대신한다.

| 질문 | 고른 것 |
| --- | --- |
| 어느 허브에 | 이 저장소. 지금 사용자 수준 훅은 `wiki-agent/tool/hook.py` 를 불러 1~6단계도 실제 세션에 안 실린다. 훅을 어느 허브에 걸지는 이 계획 밖에서 정한다. 그 전까지 실물 확인은 이 저장소 훅이 걸린 세션에서만 한다 |
| keep-alive | 저장소별로 켠다. `.wiki/adapter.toml` 에 `keep_alive = 2` 를 둔 저장소만, 세션당 상한 2. Claude 세션이 도는 Orca 셀만 |
| 자동 compact 문턱 | 값을 재서 고르고, 이 PC 의 Claude·Codex 사용자 설정에 실제로 넣는다 |

## 착수 전에 확인한 것 — 2026-09-25

### 유휴 뒤 복귀 — `replay` 의 7단계 절, 기간 전체

| 간격 | 이 저장소 복귀 | 나라 복귀 | 나라 C 측정 합 |
| --- | ---: | ---: | ---: |
| 60분 미만 | 220 | 712 | 3,720,757 |
| 60~115분 | 0 | 27 | 4,475,770 |
| 115~170분 | 0 | 11 | 2,334,279 |
| 170~225분 | 1 | 3 | 603,590 |
| 225~280분 | 0 | 4 | 1,085,503 |
| 그 이상 | 1 | 12 | 4,274,777 |
| 복귀 없음 (세션 끝) | 79 | 203 | 11,264,210 |

| 상한 k | 이 저장소 순절감 | 나라 순절감 |
| ---: | ---: | ---: |
| 1 | −384,215 | 6,100,150 |
| 2 | −768,430 | 8,579,044 |
| 3 | −887,934 | 8,003,057 |
| 4 | −1,258,217 | 8,403,064 |

토큰 환산, API 요율 대리값이다. 나라에서 60분을 넘겨 돌아온 57번은 복귀당 약 39만 토큰을 다시 썼다.
이 저장소는 60분을 넘긴 복귀가 두 번뿐이라 핑이 손해만 본다. 그래서 저장소별로 켠다.

이 표에는 두 가지 흠이 있고, 7단계의 첫 작업이 그것을 고친다.

- 간격이 사람 발화 사이다. 그 사이 에이전트가 일한 시간은 캐시를 살려 두므로, 실제 유휴는 더 짧다.
  다만 C 는 복귀 직후 실제로 다시 쓴 양이라, C 가 큰 복귀는 캐시가 정말 식은 경우다
- `<task-notification>` 같은 하네스 주입 발화도 행으로 적혀 복귀로 셌다. `sessions.INJECTED` 가 그
  목록을 이미 갖고 있다

### 설치된 버전의 설정 이름 — 바이너리 문자열로 확인

| 호스트 | 이름 | 뜻 (바이너리의 설명) |
| --- | --- | --- |
| Claude Code 2.1.282 | `autoCompactWindow` (settings) | "Auto-compact window size" |
| | `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (환경 변수) | 같은 값, 토큰 단위 ("set CLAUDE_CODE_AUTO_COMPACT_WINDOW=… tokens") |
| | `autoCompactEnabled` (전역 설정) | 켜고 끄기, 기본 `true` |
| | `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `DISABLE_AUTO_COMPACT` | 비율 덮어쓰기, 끄기 |
| Codex 0.156 | `model_auto_compact_token_limit` | 토큰 수 문턱 |
| | `model_auto_compact_token_limit_scope`, `model_post_turn_compact_threshold_percent` | 적용 범위, 턴 뒤 비율 문턱 |

바이너리의 문자열은 이름이 있다는 증거이지 뜻의 증거는 아니다. 8단계에서 값을 넣기 전에 각 호스트의
문서에서 단위와 적용 시점을 확인하고, 값을 넣은 뒤 실물로 한 번 본다.

### Orca 셀과 세션 잇기

`orca terminal list --json` 의 행에는 `handle`·`worktreePath`·`lastOutputAt` 이 있고 세션 id 는 없다.
대신 셀 안에서 도는 훅의 환경에 `ORCA_TERMINAL_HANDLE` 이 있다. 그래서 짝짓기를 나중에 추측하지 않고,
훅이 자기 셀의 handle 을 그 자리에서 데몬에 넘긴다.

### 데몬은 지금 챗만 띄운다

5단계에서 훅 보조를 껐으므로(`SUGGEST_MIN = None`) 작업 세션 중에는 데몬이 떠 있지 않을 수 있다.
keep-alive 의 `Stop` 훅이 상태 파일이 없으면 `search.spawn()` 으로 띄운다. 그 턴은 타이머가 안 걸리고
다음 턴부터 걸린다.

### 8단계 트리거 후보를 두 저장소 발화에 넣어 봤다

| 패턴 | 이 저장소 (302행) | 나라 (974행) | 본 것 |
| --- | ---: | ---: | --- |
| `compact` | 1 | 1 | 둘 다 오탐 — `<task-notification>` 한 건, `diskpart` 의 `compact` 한 건 |
| `토큰.{0,8}(아끼\|절약\|절감\|많이\|줄)` | 4 | 2 | 대부분 토큰 비용 이야기. 한 건은 `<task-notification>` |
| `퇴근`, `/compact`, 자리 비움 | 0 | 0 | — |

`compact` 한 단어는 트리거로 쓰지 않는다.

## PR 과 단계

| PR | 단계 |
| --- | --- |
| ⑥ | 7 keep-alive — 측정 보정, 그다음 구현 |
| ⑦ | 8 compact 문턱 측정·설정과 운영 페이지, 9 게이트 |

⑥ 의 측정 보정에서 나라의 상한 2 순절감이 0 이하로 떨어지면 구현하지 않고 다시 묻는다. 그러면 ⑦ 하나가 된다.

## 7단계 — keep-alive (PR ⑥)

### 셈

문맥 크기를 C 토큰이라 하자. API 요율(쓰기 2배, 읽기 0.1배)을 한도 소모의 대리값으로 쓴다.
구독 한도에서 캐시 읽기가 얼마로 세어지는지는 공개되지 않았으므로, 이 셈은 추정으로 적는다.

| 경우 | 핑 없음 | 핑 k번 |
| --- | --- | --- |
| 60분 뒤 돌아온다 | 2C (다시 쓰기) | 0.1C × (k + 1) |
| 안 돌아온다 | 0 | 0.1C × k (전부 손해) |

60분 안의 복귀는 캐시가 살아 있어 핑이 필요 없다. 55분마다 핑 k번이면 60 + 55k 분 안의 복귀를 구한다.

### 7a. 측정 보정 — `trigger_audit.py replay`

구현보다 먼저 한다. 위 표의 두 흠을 고쳐 다시 낸다.

- `sessions.INJECTED` 로 시작하는 발화의 행은 복귀로 세지 않는다. 간격 계산에서도 건너뛴다
- 간격의 시작은 직전 사람 행의 `at` 이 아니라, 그 세션 transcript 에서 그 뒤 마지막 활동의 시각이다.
  Claude transcript 의 마지막 `assistant` 행 `timestamp` 를 쓴다. `scan` 이 이미 `usage` 를 읽으며
  시각을 모으므로 같은 순회에 얹는다. transcript 를 못 찾은 세션은 지금처럼 행 사이 간격으로 두고 그
  수를 따로 적는다
- 보정 전·후 두 표를 나란히 낸다

멈출 곳. 보정 뒤 나라의 상한 2 순절감이 0 이하면 여기서 멈추고 `AskUserQuestion` 으로 다시 묻는다.
선택지는 "상한을 바꿔 구현", "안 한다" 이고 각각 보정 뒤 수치를 싣는다.

### 7b. 모양 — 셀의 상태는 훅이 알린다

데몬은 셀의 상태를 짐작하지 않는다. Orca 의 출력 시각이나 transcript 끝에서 "지금 한가한가",
"어느 세션인가", "핑 턴이었는가" 를 읽어 내는 설계는 리뷰 1회차에서 세 곳이 뚫렸다 — `/clear` 뒤 같은
셀의 다른 세션, 조용히 도는 긴 도구 실행, 도구 결과와 하네스 발화도 `user` 로 적히는 transcript.
셀에서 일어나는 일은 그 셀의 훅이 이미 전부 본다. 그래서 훅이 알리고 데몬은 받아 적는다.

| 훅 이벤트 | 보내는 것 | 데몬이 하는 일 |
| --- | --- | --- |
| `SessionStart` (모든 `source` — `startup`·`resume`·`clear`·`compact`) | `/own {handle, session}` | 그 셀의 주인을 이 세션으로 바꾸고, 같은 셀의 다른 세션 타이머를 지운다 |
| `UserPromptSubmit`, 발화가 핑 문구와 같다 | `/ping-turn {session}` | 상태를 "핑 도는 중" 으로. 계수는 둔다 |
| `UserPromptSubmit`, 발화가 `sessions.INJECTED` 로 시작한다 | `/busy {session, reset: false}` | 타이머를 지운다. 사람이 온 것은 아니니 계수는 둔다 |
| `UserPromptSubmit`, 그 밖 | `/busy {session, reset: true}` | 타이머를 지우고 계수를 0 으로 |
| `Stop` | `/idle {session, handle, project, limit}` | 계수가 상한보다 작으면 타이머를 "지금 + 55분" 으로 |
| `SessionEnd` | `/gone {session}` | 그 세션을 지운다 |

주인은 `/own` 만이 아니라 모든 알림이 정한다. 알림마다 `handle` 과 `session` 을 싣고, 데몬은 받을 때마다
그 셀의 주인을 그 세션으로 두고 같은 셀의 다른 세션 타이머를 지운다. 훅은 그 셀을 지금 차지한 세션의
프로세스 안에서 돌므로, 어떤 세션의 알림이 왔다는 것 자체가 그 세션이 지금 그 셀에 있다는 증거다.
밀려난 옛 세션은 더 알릴 수 없으니 셀을 되찾지 못한다. 그래서 데몬이 다시 떠 주인 기록을 잃어도 —
버전 교체 포함 — 다음 알림 하나로 되돌아온다(리뷰 2회차).

계수는 되찾지 않는다. 데몬이 처음 보는 세션은 무엇으로 알게 됐든 계수를 상한으로 두고, 계수를 0 으로
돌리는 것은 `/busy` 의 `reset: true` — 사람의 발화 — 하나뿐이다.

- `SessionStart` 는 새 세션의 증거가 아니다. `resume` 과 `compact` 는 이미 핑을 받은 세션에서도 온다(리뷰 4회차)
- 그래도 잃는 것이 없다. 새로 연 세션(`startup`·`clear`)은 사람이 첫 발화를 하기 전에는 `Stop` 이 없어
  쉴 수가 없고, 그 첫 발화가 계수를 0 으로 돌린다
- 데몬이 다시 뜬 세션은 사람이 돌아오기 전까지 keep-alive 가 없다. 틀리면 핑을 덜 보내는 쪽이고, 상한을
  넘겨 보내는 쪽으로는 틀리지 않는다(리뷰 3·4회차)

`StopFailure` 로 끝난 턴은 아무것도 보내지 않는다 — 타이머가 안 걸리는 쪽으로 틀린다.

타이머가 울리면 넣기 전에 다시 본다. 하나라도 어긋나면 보내지 않고 그 세션을 지운다.

- 그 세션이 아직 그 셀의 주인이고, 마지막으로 받은 이벤트가 `Stop` 이다
- Orca 에서 그 셀이 `connected`·`writable` 이고 `worktreePath` 가 `/idle` 의 저장소와 같다
- 화면 마지막 줄이 비어 있는 Claude 입력 줄이다 — 사람이 쓰다 만 글이 있거나 셸로 떨어졌으면 보내지
  않는다. `orca terminal read` 로 읽는다. Orca 안 Claude Code 의 빈 입력 줄 모양은 착수 때 실물로 확인해
  한 곳에 적는다. 확인하지 못하면 keep-alive 를 내지 않는다

보내면 계수 +1, 상태는 "핑 보냄". 10분 안에 `/ping-turn` 이 오지 않으면 그 세션을 지운다.

핑 문구는 고정한다: `keep-alive — reply "ok" and nothing else.`

### 7c. 파일

| 파일 | 무엇 |
| --- | --- |
| `tool/keepalive.py` | 새 훅 스크립트 하나가 `SessionStart`·`Stop`·`SessionEnd` 를 받는다(`--event` 인자). 조건 셋이 모두 맞을 때만 데몬에 알린다: `--host claude` · 환경에 `ORCA_TERMINAL_HANDLE` · 대상 저장소 `adapter.toml` 의 `keep_alive` 가 1 이상. `craft/hooks-fail-open` — 무엇이 실패해도 0 을 돌려주고 stderr 에 예외 이름만 |
| `tool/inject.py` | `UserPromptSubmit` 쪽. 핑 문구와 정확히 같은 발화는 아무것도 싣지 않고 trajectory 에도 적지 않고 `/ping-turn` 만 보낸다. 그 밖의 발화는 위 표의 `/busy` 를 보낸다. 셋 다 같은 조건일 때만 |
| `tool/searchd.py` | `/own`·`/ping-turn`·`/busy`·`/idle`·`/gone` (모두 토큰 필요). 세션별 `{handle, project, state, due, count, limit, expires}`, 셀별 주인. 30초마다 도는 타이머 스레드. `orca` 호출(목록·읽기·보내기)은 함수 하나로 모아 테스트에서 바꿔 끼운다 |
| `tool/search.py` | 위 알림들의 클라이언트 함수 하나. `ask` 와 같은 증명과 시간 상한(150ms)을 쓴다 |
| `tool/apply.py` | `SessionStart`·`Stop`·`SessionEnd` 에 `keepalive.py` 를 건다. `lint`·`repo_lint` 의 배선 검사가 같이 본다 |
| `ai-nara-shop/.wiki/adapter.toml` | `keep_alive = 2`. 대상 저장소 파일이라 그 저장소에서 따로 커밋한다 |

### 7d. 수명 — `craft/client-lifecycle-in-one-scope` 의 네 질문

| 질문 | 답 |
| --- | --- |
| 생성 | 타이머는 `/idle` 이 만든다. 데몬이 없으면 알리는 훅이 `search.spawn()` 으로 띄우고, 상태 파일이 생기기를 3초까지 기다린 뒤 그 알림을 보낸다. 그래도 없으면 그 알림은 버린다. `SessionStart` 도 알리므로 보통은 첫 `Stop` 전에 데몬이 떠 있다. 훅 하나가 쓰는 시간은 5초로 묶는다 |
| 공유 | 세션 id 가 키다. 셀의 handle 은 그 셀의 훅이 알려 준 것만 쓰고, 한 셀에는 주인이 하나다 |
| 닫기 | 상한 도달, 보내기 전 확인 불일치, `/busy`, 같은 셀에서 온 다른 세션의 알림, `/gone`, 핑 뒤 10분 무응답 때 지운다. 세션마다 만료 시각이 따로 있다 — 마지막 `Stop` + 55분 × 상한 + 10분. 어떤 이벤트도 더 오지 않아도 그때 지운다. 데몬의 유휴 종료(3시간)는 가장 늦은 만료 시각까지만 미뤄진다 |
| 소유 | 사용자. 타이머는 메모리에만 있다. 데몬이 죽으면 잃고, 다음 `Stop` 이 다시 건다 — 그 사이의 복귀는 핑 없이 다시 쓴다. `SessionEnd` 없이 세션이 죽어 셀이 셸로 떨어졌으면 화면 확인이 보내기를 막는다. 틀리면 토큰을 더 쓰는 쪽이다 |

### 7e. 같이 도는 훅이 핑 턴에 하는 일

- `inject.py` — 위 표대로 싣지도 적지도 않고 `/ping-turn` 만 보낸다
- `declared_continuation.py` — 답이 `ok` 한 단어면 약속 문형이 없어 걸리지 않는다. 테스트로 박는다
- `sync.py` — 핑 턴에도 돈다. 하는 일이 저장소 상태 확인이라 그대로 둔다
- 핑 턴이 쓰는 값은 문맥 읽기 0.1C 와 짧은 출력이다. 훅 주입은 0 이다

### 7f. 테스트 — `tool/test_keepalive.py`

- 훅: Codex 호스트, `ORCA_TERMINAL_HANDLE` 없음, `keep_alive` 없는 저장소 — 셋 다 아무것도 안 보낸다
- 훅: 데몬이 없을 때 띄우고 기다린 뒤 보낸다. 3초 안에 안 뜨면 버리고 0 을 돌려준다
- `inject.py`: 핑 문구 → 출력 없음, trajectory 행 없음, `/ping-turn`. `<task-notification>` 으로 시작하는
  발화 → `/busy` 에 `reset: false`. 사람 발화 → `reset: true`
- 데몬(가짜 시계와 가짜 `orca`):
  - 55분에 한 번 보내고, 상한 2 뒤에는 안 보낸다
  - 핑 뒤 `/busy` 가 `reset: false` 로 와도 계수가 0 이 되지 않는다 — 상한을 넘지 않는다
  - 같은 셀에서 다른 세션의 알림이 오면 옛 세션 타이머가 사라진다 (`/clear` 의 모양)
  - 데몬을 다시 띄워 주인 기록이 비어도 주인은 다음 알림으로 되돌아온다. 그 세션이 사람 발화(`reset: true`)
    뒤의 `Stop` 이면 타이머를 걸고, 처음 받은 것이 `/idle` 이면 걸지 않는다
  - 첫 핑 뒤와 둘째 핑 뒤에 각각 데몬을 다시 띄워도, 사람 발화 없이는 세션당 핑이 2번을 넘지 않는다.
    다시 띄운 뒤 `SessionStart` 가 `source=compact` 와 `source=resume` 으로 와도 마찬가지다
  - 마지막 이벤트가 `Stop` 이 아니면, 셀이 사라졌거나 다른 저장소면, 화면 마지막 줄에 글이 있거나 셸이면 안 보내고 지운다
  - 핑 뒤 10분 무응답이면 지운다. 이벤트가 끊겨도 만료 시각에 지운다
  - 유휴 종료가 가장 늦은 만료 시각까지만 미뤄진다
- `declared_continuation.py`: 답이 `ok` 인 핑 턴 → 통과

### 7g. 완료 기준

- 7a 보정 뒤 나라의 상한 2 순절감이 0 보다 크다
- 실물 한 번. 나라의 Orca 셀 하나를 한 시간 넘게 비워 두고 돌아온다. 그 사이 핑이 한 번 들어갔고,
  복귀 첫 응답의 `cache_creation_input_tokens` 가 문맥 크기보다 훨씬 작다 — 캐시가 살아 있었다

## 8단계 — compact 문턱과 운영 규칙 페이지 (PR ⑦)

### 8a. 문턱을 잰다 — `replay` 에 "compact 문턱" 절

긴 세션은 매 턴 문맥 전체를 캐시에서 읽는다. 문맥이 90만이면 한 턴에 읽기 9만(0.1배)이다. 문턱을
낮추면 그 읽기가 줄고, 대신 compact 가 잦아진다.

셈. Claude transcript 의 `assistant` 행을 세션별로 시각 순으로 흘린다. 한 API 응답이 내용 블록마다
행을 따로 적고 같은 `usage` 를 되풀이하므로, `message.id` 로 묶어 응답 하나를 한 번만 센다. 이 저장소의
한 transcript 에서 `assistant` 행 2,799개가 응답 2,139개였다(같은 id 묶음 530개). 응답마다 문맥
c = `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`.

- 문턱 W 를 모의한다. 모의 문맥 s = c − 오프셋. s 가 W 를 넘으면 그 자리에서 compact 가 났다고 치고
  오프셋을 c − S 로 둔다. S 는 요약 크기로, transcript 에서 실제 compact 직후 첫 문맥의 중앙값이다
  (이 저장소 실측 11K). 실제 compact 로 c 가 오프셋보다 작아지면 오프셋을 0 으로 되돌린다
- 절감 = Σ (c − s) × 0.1
- 비용 = 늘어난 compact 수 × (0.1W + 2S). 요약을 만드는 읽기와 요약을 다시 쓰는 값이다
- 재지 못하는 것. compact 가 잦아지며 요약에서 빠지는 맥락. 그래서 늘어난 compact 수를 같이 적어
  사람이 본다

낼 표. W 는 200K, 300K, 400K, 600K 와 지금(자동, 약 1M). 두 저장소 각각.

| W | compact 가 난 세션 | 늘어난 compact | 절감 | 비용 | 순 |
| ---: | ---: | ---: | ---: | ---: | ---: |

수치가 나오면 `AskUserQuestion` 으로 W 를 묻는다. 각 선택지에 순절감과 늘어난 compact 수를 싣는다.
이 문서에 수치와 답을 적는다.

### 8b. 이 PC 에 설정한다

- 값을 넣기 전에, 각 호스트의 문서에서 `autoCompactWindow` 와 `model_auto_compact_token_limit` 의 단위와
  적용 시점을 확인하고 출처를 이 문서에 적는다. 위 표의 이름은 바이너리 문자열로만 확인했다
- `tool/setup_agents.py --compact-window <토큰>` 을 더한다. 이 두 키만 쓰고 훅 배선은 건드리지 않는다
  — 지금 훅은 `wiki-agent` 를 가리키고, 그것은 이 계획 밖의 결정이다
  - Claude: `~/.claude/settings.json` 의 `autoCompactWindow`
  - Codex: `apply.user_files("codex")` 가 찾는 모든 홈(기본 `~/.codex` 와 Orca 계정 홈)의 `config.toml`
    `model_auto_compact_token_limit`
  - 이미 같은 값이면 아무것도 안 한다. 다른 값이 있으면 덮지 않고 알린다 — 사람이 고친다
- 테스트는 `WIKI_USER_HOME` 아래 가짜 홈에서 한다. 실제 설정 파일을 읽지도 쓰지도 않는다

실물. 설정 뒤 처음 W 를 넘는 Claude 세션과 Codex 세션에서 compact 가 W 근처에서 났는지 transcript 로
본다 — Claude 의 `compact_boundary`, Codex 의 `compacted`. 자연히 일어날 때 적는다.

### 8c. 운영 규칙 페이지 — `operator/compact-before-idle.md`

`severity: contract`, `repeat: rule`. 허브 페이지라 본문은 영어다.

규칙 문단에 둘 것. `repeat: rule` 이라 두 번째부터는 이 문단만 나간다.

- 한 시간 넘게 자리를 비우기 전에 `/compact`. 돌아와서 다시 쓰는 양이 C 에서 요약 크기로 준다
  (이 저장소 실측 967K → 11K)
- 이 PC 의 자동 compact 문턱은 W 이고 `setup_agents --compact-window` 로 바꾼다
- keep-alive 가 켜진 저장소(`keep_alive` 를 둔 저장소)에서는 `keep-alive —` 로 시작하는 발화에 `ok` 만 답한다

문단 밖에 둘 것. 7단계의 셈과 보정 뒤 수치, keep-alive 를 이 저장소에서 켜지 않는 이유, 8a 의 표.

트리거. `compact` 한 단어는 쓰지 않는다(위 표).

```
/compact|compact.{0,10}(해|할|하기|전|문턱|window)|퇴근|토큰.{0,8}(아끼|절약|절감|많이|줄)|자리.{0,6}(비우|비울)
```

## 9단계 — 이 묶음의 게이트

PR ⑥·⑦ 각각 끝에 돌린다.

1. `pytest tool/`. 7f 의 테스트와 8b 의 설정 테스트
2. `python tool/lint.py --check`. 새 페이지의 front matter, `repeat: rule` 문단 길이(1,200자 이하), 링크, 강조
3. 두 저장소 `replay`
   - 리콜 불변식 녹색
   - 7a 보정 전·후 유휴 복귀 표
   - 8a 문턱 표
   - 8c 트리거가 걸리는 발화 수와 표본. 하네스 주입 발화에 걸린 것이 있으면 트리거를 고친다
4. `latency` 20회. `inject.py` 가 이제 데몬에 알리므로 `keep_alive` 를 둔 저장소 사본과 `ORCA_TERMINAL_HANDLE`
   을 준 채로 잰다. 핑 문구 발화와 보통 발화의 p95. 보통 발화는 `main` 과 번갈아 재서 잡음 안이어야 한다
5. 실물 — 7g 와 8b. 이 저장소 훅이 걸린 세션에서 한다
6. [개요](token-diet.md)의 단계 표 상태 칸에 수치를 적는다

## 구현 기록 — 2026-09-25

### 7a 보정 결과

| 상한 k | 이 저장소 보정 전 | 보정 뒤 | 나라 보정 전 | 보정 뒤 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | −396,066 | −396,066 | 6,088,838 | 6,748,666 |
| 2 | −792,131 | −792,131 | 8,556,421 | 8,901,757 |
| 3 | −923,485 | −923,485 | 7,969,123 | 7,719,979 |
| 4 | −1,305,618 | −1,305,618 | 8,357,818 | 8,108,674 |

보정 뒤 나라에서 60분을 넘긴 복귀는 52번(보정 전 57번)이다. 상한 2 순절감이 0 보다 커서 멈추지 않고
구현했다. transcript 를 못 찾아 행 사이 간격으로 둔 복귀는 이 저장소 7개, 나라 5개다.

### 착수 때 실물로 보고 계획에서 바꾼 것

| 계획 | 바꾼 것 | 왜 |
| --- | --- | --- |
| 셀 확인은 `orca terminal list` 의 행 | `orca terminal show --terminal <handle>` | 같은 셀이 `list` 에서 다른 handle 로 나온 적이 있다. 훅 환경의 `ORCA_TERMINAL_HANDLE` 은 `show` 로 같은 PTY 에 풀린다 |
| 화면 마지막 줄이 빈 입력 줄 | `─` 줄 둘 사이의 `❯` 한 줄, 그 아래 들여 쓴 상태 줄 3줄 이하 | Orca 1.4.167 안 Claude Code 2.1.282 의 실물. 모양은 `searchd.input_empty` 한 곳에 적었다. 작업 중에도 입력 칸은 비어 있으므로 판단은 여전히 마지막 알림이 `Stop` 인지가 먼저다 |
| `/idle {project}` | `/idle {checkout}` | Orca 의 `worktreePath` 는 작업트리 경로이고, `hook.py` 의 project 는 주 클론이다. `hook.py` 가 `--checkout` 을 준다 |
| `keepalive.py --event` | payload 의 `hook_event_name` | 사용자 수준 배선의 모양 검사(`apply.ours`)가 값 있는 플래그를 받지 않는다. 세 이벤트가 한 명령이 된다 |
| 핑 문구는 고정 | `search.PING`, 데몬 버전 해시에 `search.py` 를 더했다 | 옛 데몬이 옛 문구를 치면 훅이 그것을 사람 발화로 읽어 계수를 0 으로 돌린다 — 상한이 풀린다 |
| 데몬 쪽 `orca` 호출 | `shutil.which("orca")`, 출력은 UTF-8 로 읽는다 | 셀 환경변수 없이도 돈다(챗이 띄운 데몬). 콘솔 코드 페이지로 읽으면 `❯` 와 `─` 가 깨진다 |

`--host` 는 사용자 수준 배선(`hook.py`)만 준다. 프로젝트별 배선에서는 `keepalive.py` 와 `inject.py` 둘 다
`--host` 가 없어 같이 꺼진다. 한쪽만 켜지면 사람이 말해도 `/busy` 가 없어 타이머가 남는다.

작업 중인 턴에 핑이 들어가는 길 (리뷰 1회차). 처음 적은 "55분 넘는 턴에서만" 은 틀렸다 — `/busy` 가
타이머 직전에 버려지면 짧은 턴에도 들어간다. 사용자 선택으로 창을 좁히고 남는 틈을 적는다.

- `/busy` 는 번역과 나란히 스레드로 보내고, 데몬이 있는데 늦으면 2초까지 다시 보낸다(`keepalive.RETRY`).
  이 호출이 데몬을 띄웠으면 기다리지 않는다 — 떠 있지 않던 데몬에는 타이머가 없다
- 데몬은 화면 읽기 뒤 마지막 상태 확인과 보내기를 잠금 안에서 붙여 한다. 그 사이에 알림이 끼지 못한다
- 남는 틈. Orca 에는 "확인하고 치기" 가 없다. 화면을 읽고 글자가 닿기까지 약 0.5초(`orca` 호출 한 번이
  약 0.25초) 사이에 사람이 Enter 를 누르면 그 턴에 핑이 들어간다. 2초 재시도 뒤에도 못 간 `/busy`, 그리고
  `Stop` 훅이 되돌려(`declared_continuation.py`) 55분 넘게 이어진 작업도 같다

### 8a 결과와 선택

| W | 이 저장소 세션 / 늘어난 compact / 순 | 나라 |
| ---: | --- | --- |
| 200K | 10 / 37 / 128,179,863 | 29 / 88 / 189,253,921 |
| 300K | 6 / 18 / 111,557,649 | 19 / 42 / 156,569,109 |
| 400K | 5 / 13 / 92,379,390 | 15 / 27 / 130,696,713 |
| 600K | 3 / 5 / 67,655,771 | 8 / 10 / 88,965,215 |
| 지금 (약 967K) | 실제 compact 2 세션 | 5 세션 |

Claude transcript 이 저장소 61개(응답 4,810), 나라 93개(응답 8,219). 요약 크기 S 는 실측 59,318 과
54,121 이다. 위의 11K 는 요약 자체이고, compact 직후 첫 문맥에는 시스템 프롬프트와 도구가 같이 있다.

사용자 선택(2026-09-25): 400K. 200K 절감의 약 70% 를 늘어난 compact 1/3 로 얻는다.

### 8b 문서 출처와 설정

- Claude — "Model configuration"(code.claude.com/docs/en/model-config). `autoCompactWindow` 는 토큰 수,
  100K~1M. 설정이 없으면 1M 창 모델은 약 967K 에서 compact 한다. `/autocompact` 는 같은 키를 사용자 설정에
  쓰고 현재 세션에도 적용한다. `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 가 있으면 그것이 이긴다
- Codex — "Config reference"(learn.chatgpt.com/docs/config-file/config-reference).
  `model_auto_compact_token_limit` 는 number, "Token threshold that triggers automatic history compaction".
  `model_auto_compact_token_limit_scope` 기본은 `total`. `model_post_turn_compact_threshold_percent` 는 문서에 없다
- 이 PC 에 넣었다. `~/.claude/settings.json`, `~/.codex/config.toml`, Orca Codex 계정 홈의 `config.toml` 하나.
  셋 다 전에는 키가 없었다

### 8c 트리거

계획의 패턴이 이 저장소의 하네스 행 2건에 걸렸다 — 셸 명령을 실은 `<task-notification>` 둘, 그중
하나는 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`. 사람 발화는 `<` 로 시작하지 않으므로 `\A(?!\s*<)` 로 묶었다.
걸리는 발화는 이 저장소 3, 나라 2 이고 모두 사람 발화다. 표본: "토큰을 너무 많이 사용하는 문제",
"토큰 절감 계획의 5단계에서…", "토큰을 굉장히 많이 쓰는데, SONNET 5로 내리자".

### 9단계 게이트

| # | 결과 |
| --- | --- |
| 1 | `pytest tool` 336 통과(새 테스트 `test_keepalive.py` 15, `test_setup_agents.py` 1), `ruff` 통과 |
| 2 | `lint --check` 는 훅 배선 드리프트 15건만. `main` 에서 이미 12건 — 이 checkout 의 훅 파일이 비었고 사용자 수준 훅은 `wiki-agent` 를 부른다. 더해진 3건이 keep-alive 배선이다 |
| 3 | 두 저장소 `replay` 리콜 불변식 녹색. 위 7a·8a 표 |
| 4 | `latency --keepalive` 20회, 나라 사본. 보통 발화 p95 382·485ms 와 `main` 392·378ms 를 번갈아 쟀다 — 잡음 안. 핑 문구 p95 220·209ms |
| 5 | 실물 — 미완. 아래 |
| 6 | [개요](token-diet.md) 단계 표에 적었다 |

### 남은 것

- 7g 실물. 사용자 수준 훅이 `wiki-agent/tool/hook.py` 를 부르는 동안에는 나라 셀에서 `keepalive.py` 가
  돌지 않는다. 훅을 어느 허브에 걸지 정한 뒤에 한다
- 8b 실물. 설정 뒤 처음 400K 를 넘는 Claude·Codex 세션에서 `compact_boundary` 의 `preTokens`, Codex 의
  `compacted` 가 400K 근처인지 본다
- `ai-nara-shop/.wiki/adapter.toml` 의 `keep_alive = 2` 는 그 저장소 작업 트리에만 넣었다(사용자 선택). 커밋은
  그 저장소에서 한다

## 이번 범위 밖

- 훅을 어느 허브에 걸지(`ai-coding-agent-wiki-public` 과 `wiki-agent`). 1~6단계를 `wiki-agent` 로 옮길지도 같이
- 훅이 하네스 주입 발화(`<task-notification>` 등)에도 규칙을 싣는 것. 8c 의 트리거 점검에서 드러났다.
  모든 페이지의 주입이 바뀌는 일이라 따로 묻는다
- Codex 세션의 keep-alive. Codex 의 캐시 보존 시간과 비용을 재지 않았다
