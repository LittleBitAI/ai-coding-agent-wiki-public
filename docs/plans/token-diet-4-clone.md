# 4묶음 — 원본(wiki-agent)에 복제하고, 몇 % 줄었는지 잰다 (제안)

전체 설계와 단계 표는 [개요](token-diet.md)에 있다. 1~3묶음의 설계는
[1묶음](token-diet-1-hook.md)·[2묶음](token-diet-2-search.md)·[3묶음](token-diet-3-session.md)에 있다.

상태. 제안이다. 착수 전에 아래 "착수 전에 물을 것" 을 묻는다.

## 왜 — 절감이 실제 세션에 실리지 않는다

1~3묶음은 이 저장소(공개 사본)에 머지됐다(#22·#23·#24·#26). 그런데 이 PC 의 사용자 수준 훅은
`wiki-agent/tool/hook.py` 를 부른다. 원본의 훅에는 1~3묶음이 없다.

- 원본 `tool/inject.py` 는 227줄이다. `--host`, 세션 내 중복 제거, compact 리셋, keep-alive 가 없다
- 2026-09-25 이 세션에서 `operator/english-progress` 가 같은 세션에서 두 번째 턴에도 전문으로 실렸다.
  중복 제거가 돌았다면 `(landmine, repeated)` 로 규칙 문단만 실렸어야 한다
- 실제로 켜진 것은 호스트 설정인 자동 compact 400K 하나와, 원본에도 있는 스킬 둘뿐이다

## 2026-09-25 에 정한 것

| 질문 | 고른 것 |
| --- | --- |
| 어디에 켜나 | 원본(wiki-agent). 옮겨 붙이지 않고 복제한다 — 원본의 구조를 보고 그 구조에 맞춰 다시 세운다 |
| 몇 % 줄었는지 | 둘 다. 켜는 날 고정 과제 A/B 로 바로 한 번, 켠 뒤 7일 실사용 전후 비교로 확정 |

## 원본의 구조 — 사본과 무엇이 다른가

2026-09-25 원본 `main`(`b34a0f4`) 기준.

| 사본 (이 저장소) | 원본 (wiki-agent) |
| --- | --- |
| `tool/inject.py` 한 파일에 매칭·렌더·중복 제거 | 매칭·렌더는 `tool/wiki/match.py`, 진입점은 `tool/inject.py`. 패키지의 `__all__` 이 계약이고 `lint.pipeline_surface` 가 지킨다 |
| `tool/sessions.py` | `tool/workspace/sessions.py`, `INJECTED` 는 `workspace` 가 내보낸다 |
| `tool/translate.py` | `tool/translate/` 패키지 |
| `tool/chat*.py` | `tool/agent/`(세션)와 `tool/main/`(서버·창). 위키 질의는 `tool/main/query.py`, 검색은 없다 |
| `tool/search.py`·`tool/searchd.py` | 없다 |
| `trigger_audit.py` 의 `replay`·`latency`·`label`·`suggest` | 119줄, census 비교만 |
| `trajectory.record` 의 `sent`·`full`·`tx`·`txp`·`reset` | 없다 — 중복 제거가 읽을 기록이 없다 |
| `hook.py` 가 `inject.py`·`keepalive.py` 에 `--host` | `--host` 를 주지 않는다 |
| `setup_agents.py --compact-window` | 없다 |
| `repeat: rule` 선언 25장 | 0장 |
| `after-merge-cleanup` 1,157B · `codex-review-loop` 1,846B | 2,715B · 5,750B. 스킬(`after-merge`·`review-loop`)은 이미 있다 |
| `operator/compact-before-idle` | 없다 |

원본 페이지의 본문은 사본과 다르다(예: `agent-delegation`, `hooks-fail-open`). 그래서 페이지 선언과 줄인
본문은 복사하지 않고 원본 문장을 보고 다시 쓴다.

원본 체크아웃은 지금 `loop-4-review` 브랜치다. 사용자 수준 훅은 원본 체크아웃의 파일을 그대로 부르므로, 원본 `main` 에 머지되고 그 체크아웃이 `main`
으로 돌아오는 순간이 "켜는" 순간이다.

## 원본에서 진행 중인 작업과 겹치는 곳 — 2026-09-25 확인

원본의 작업트리는 하나다. loop 4단계가 `loop-4-review` 브랜치에 있다 — 처음 볼 때는 미커밋이었고, 같은 날
`8adfe09` 로 커밋·푸시됐다(미머지). 파이썬 파일은 아래 표 그대로다.

| loop 4 가 지금 바꾸는 파일 | 이 계획이 건드리나 |
| --- | --- |
| `tool/main/query.py` (`hold` 를 `Held` 로) | 6단계 챗 검색만. 유일한 겹침이다 — 6단계는 loop 4 머지 뒤로 |
| `tool/workspace/__init__.py` (`adopt`·`folder_for` 를 `__all__` 에) | `INJECTED` 를 읽기만 한다. 그대로 내보낸다 |
| `tool/main/` 의 나머지, 새 `loop.py`, `tool/workspace/worktrees.py`, 테스트, `web/` | 안 건드린다 |

loop 5단계(착수 전)가 계획한 것과의 겹침.

| 파일 | loop 5 | 이 계획 | 위험 |
| --- | --- | --- | --- |
| `tool/hook.py` | `main()` 에 `WIKI_PROBE` 갈래 하나 | `main()` 에 `--host`·`--checkout` | 같은 함수, 다른 줄. 늦게 머지하는 쪽이 몇 줄 맞춘다 |
| `tool/setup_agents.py` | `install_global` 을 목록과 쓰기로 나눔, 스킬 링크, 시험 | 새 함수 `compact_window` 와 인자 하나 | 다른 함수. `main()` 의 인자 줄만 |
| `tool/lint.py` | 게이트로 돌린다. `sync`·`harvest`·`session_state` import 금지는 테스트로 | 규칙 문단 1,200자 검사, 훅 가드 목록에 `keepalive.py` | 다른 검사 |

그래서 작업 자리는 원본 `main` 에서 뻗은 별도 작업트리다. 사용자 수준 훅은 지금 `loop-4-review` 체크아웃의
파일을 부르므로, 이 계획의 코드는 그 체크아웃이 이 계획이 머지된 `main` 을 받은 뒤에 실제 세션에 실린다.

## 복제 단위 — 원본의 어디에 무엇을

| 단계 | 원본의 자리 | 사본과 달라지는 것 |
| --- | --- | --- |
| 1 측정 | `tool/trigger_audit.py` 에 `replay`·`latency`. `trajectory.record` 에 `sent`·`full`·`tx`·`txp`·`reset` | `label`·`suggest` 는 뺀다 — 5단계 훅 보조가 꺼져 쓸 곳이 없다. 새 명령 `usage`·`ab` 를 더한다(아래 측정) |
| 2 중복 제거 | 순수 렌더(`repeated`, `compose`, `remembered`, `LIMIT`)는 `tool/wiki/match.py` 에 두고 `__all__` 에 더한다. transcript 를 읽는 `recall`·`compacted` 는 진입점 `inject.py`. `trajectory.record` 는 출력과 `stdout.flush()` 뒤로 옮기되, 모든 발화에서 돈다 — 조기 반환 `if not parts and not english: return 0`(`inject.py:163`)은 출력만 거르는 조건으로 바꾼다(사본 `inject.main` 의 `if body:` 모양). 기록을 건너뛰는 출구는 빈 발화·깨진 입력과, 3단계 뒤의 keep-alive 핑 턴뿐이다 | `wiki` 는 번역하지 않는 패키지라는 원본의 경계를 지킨다. 원본은 지금 출력 전에 기록한다(`inject.py:150`, 출력은 `:204`) — 그대로 두면 출력에 실패한 턴의 `full` 이 남아 다음 턴이 보지 못한 전문을 본 것으로 센다(리뷰 1회차). 기록만 옮기고 조기 반환을 두면 걸린 규칙 없는 턴이 기록에서 사라진다 — 원본은 누락을 찾으려고 그 턴도 기록한다(리뷰 2회차) |
| 2 페이지 | 원본 페이지마다 규칙 문단을 확인하고 `repeat: rule` 선언. 규칙 문단 1,200자 검사는 원본 `lint` 에 | 사본 선언을 복사하지 않는다 |
| 3 compact 리셋 | `inject.py` 의 `recall`, `COMPACTED` | 같다 |
| 4 스킬 | 두 페이지 본문만 줄인다 | 스킬은 이미 있다 |
| 5 데몬 | `tool/search/` 패키지 — `__init__.py`(`ask`·`notify`·`spawn`·`PING`)와 `daemon.py`(색인·`Keeper`) | 훅 보조(`suggest`)는 복제하지 않는다. 데몬은 keep-alive 와 챗 검색에만 쓴다. 버전 해시는 패키지 파일 전부. 포트와 캐시 루트 전체를 사본(8790, `~/.cache/ai-coding-agent-wiki/`)과 다르게 둔다. 상태 파일이 같으면 한 기계의 두 데몬이 서로를 버전 불일치로 끄고, 모델 내려받기(`models/e5/*.part`)와 `vectors.sqlite3` 가 같으면 동시 첫 시작에서 한쪽의 교체가 다른 쪽 임베딩을 꺼뜨린다(리뷰 1회차) |
| 6 챗 검색 | `tool/main/query.py` 에 검색 호출 | 원본의 챗은 서버 경로라 사본의 `chat_session` 과 다르다. loop 계획과 겹치므로 착수 전에 묻는다 |
| 7 keep-alive | 진입점 `tool/keepalive.py`, `hook.py` 의 `--host`·`--checkout`, `apply.py` 배선 | 같다. 리뷰 1~3회차에서 고친 두 경로(`/busy` 재시도, 잠금 안의 확인과 보내기)를 처음부터 넣는다 |
| 8 compact | `operator/compact-before-idle`, `setup_agents.py --compact-window` | 설정 값은 이미 이 PC 에 들어가 있다. 도구와 페이지만 |
| 9 게이트 | 원본의 `pytest tool`·`lint --check`·`replay` | 원본은 `lint.pipeline_surface` 가 더 있다 |

## 측정 — 몇 % 줄었는지

토큰은 한도 환산으로 센다. 구독 한도의 실제 가중치는 공개되지 않아 API 요율을 대리값으로 쓴다 — 입력 1,
캐시 쓰기(1시간) 2, 캐시 읽기 0.1, 출력 5. 표에는 환산값과 원 토큰 수를 같이 적는다.

### A. 고정 과제 A/B — 켜는 날 한 번

`trigger_audit.py ab` 를 새로 만든다.

- 과제. 두 저장소 trajectory 에서 사람 발화로 이어진 세션을 뽑는다(저장소마다 3세션, 세션당 발화 8개,
  원문 그대로). 발화가 이어져야 중복 제거가 보인다 — 첫 턴은 두 팔이 같다
- 흘리기. 대상 저장소의 임시 사본에서 `claude -p --output-format json`, 둘째 발화부터 `--resume`.
  `--permission-mode plan` 으로 파일을 바꾸지 않는다
- 팔. A 는 원본 `main` 의 훅, B 는 복제 브랜치의 훅. 모델·발화·사본이 같다. 팔마다 두 번 돌려 범위를 적는다
- 팔의 격리. 그냥 `claude -p` 를 부르면 두 팔 모두 사용자 설정의 `wiki-agent/tool/hook.py` 를 부른다(리뷰
  1회차). 팔마다 그 팔의 원본 작업트리(A 는 `main`, B 는 복제 브랜치)에서 `apply.configure(…, project=None)`
  로 만든 훅 배선만 담은 설정 파일을 쓰고, `--setting-sources ""` 로 사용자·프로젝트 설정을 끄고
  `--settings <그 파일>` 로 준다. 두 팔이 같은 설정을 끄므로 공정하다
- 경로 확인. 팔마다 첫 세션 뒤, 임시 저장소의 `.wiki/trajectory.jsonl` 에 행이 생겼는지와 그 행의 모양을
  본다 — B 행에는 `sent`·`full` 이 있고 A 행에는 없다. 어긋나면 그 팔을 멈춘다
- 잴 것. 세션 합계 환산 토큰(입력·캐시 읽기·캐시 쓰기·출력)과 그 감소율, 턴당 주입 바이트(`sent`)
- 보이지 않는 것. keep-alive 와 compact 문턱은 한 시간 유휴와 400K 문맥이 있어야 드러난다 — B 에서 본다
- 비용. 약 6세션 × 8발화 × 2팔 × 2회 = 192턴. 모델은 착수 전에 묻는다

### B. 실사용 전후 — 켠 뒤 7일

`trigger_audit.py usage --since --until` 을 새로 만든다.

- 이 PC 의 Claude transcript 와 Codex rollout 을 읽어 사람 발화(`INJECTED` 제외) 한 번당 환산 토큰을
  저장소별·호스트별로 낸다. 응답은 `message.id` 로 한 번만 센다(3묶음 8a 와 같은 방식)
- 기준선. 켜기 전 7일. 끝은 자동 compact 400K 를 넣은 2026-09-25 17시 무렵이다 — 그 뒤는 문턱이 이미
  바뀐 구간이라 기준선과 따로 적는다
- 비교. 켠 뒤 7일. 사람 발화당 환산 토큰의 중앙값·평균 감소율
- 분해. 훅 주입 몫(trajectory `sent`), 유휴 뒤 복귀의 캐시 다시 쓰기(C), compact 횟수와 compact 직전
  문맥. 어느 단계가 얼마를 줄였는지 나눠 보이기 위해서다
- 한계. 두 주의 일의 종류가 다르다. 발화당으로 나누고, 세션 길이 구간별로도 낸다

## PR 순서 (원본에서)

| PR | 무엇 | 켜짐 |
| --- | --- | --- |
| ① | 측정 — `replay`·`latency`·`usage`·`ab`, `trajectory` 새 필드. 머지 즉시 기준선을 뽑아 둔다 | 기록 필드만 |
| ② | 중복 제거·compact 리셋·페이지 선언·두 페이지 줄이기·`--host` | 머지 즉시 |
| ③ | `search` 패키지·keep-alive·`compact-before-idle`·`--compact-window` | 머지 즉시. 나라의 `keep_alive = 2` 커밋과 같이 |

A/B 는 ② 머지 전에 한 번(②만), ③ 머지 전에 한 번(②+③) 돌려 단계별 몫을 나눈다. 7일 뒤 `usage`
표를 [개요](token-diet.md) 단계 표에 적는다.

## 완료 기준

- A/B 표 — 세션 합계 환산 토큰 감소율(목표 수치는 두지 않는다. 잰다), 두 저장소 리콜 불변식 녹색
- 실사용 표 — 사람 발화당 감소율과 분해
- 3묶음이 남긴 실물 두 가지 — 7g(나라 셀 한 시간 유휴 뒤 캐시 생존), 8b(400K 근처 compact)

## 착수 전에 물을 것

- 작업 자리. 원본의 loop 4단계가 머지된 뒤 `main` 에서 시작할지, 지금 별도 작업트리에서 시작할지
- A/B 의 모델과 규모 — 한도를 쓴다
- 6단계 챗 검색을 이번에 넣을지, loop 계획 뒤로 미룰지

## 이번 범위 밖

- 사본 쪽 정리. 복제 뒤에는 두 저장소가 같은 기능을 따로 가진다. 이후 사본 갱신은
  [publishing](../publishing.md) 의 원본 → 사본 절차를 따른다
- 훅이 하네스 주입 발화에도 규칙을 싣는 것 — 3묶음 범위 밖 그대로
