# 1묶음 — 측정과 훅 양 (1~4단계)

전체 설계와 단계 표는 [개요](token-diet.md)에 있다. 이 문서는 1~4단계를 코드 단위로
풀고, 이 묶음 PR 들의 9단계 게이트를 적는다.

목표. 훅이 같은 세션에 같은 규칙을 다시 싣지 않는다. 그 전에 "지금 얼마나 싣나" 와
"무엇을 놓치나" 를 재는 도구가 먼저 선다.

## 2026-09-25 구체화에서 정한 것

| 질문 | 고른 것 |
| --- | --- |
| 발화 원문 보존 | `trajectory.KEEP` 500 → 4000 (`inject.MAX_RENDERED` 와 같은 값). 과거 행은 500자 한계로 적는다 |
| 지연 측정 | 번역을 끄고 20회. 번역 포함 종단 수치는 참고로 5회 |
| 리콜 정답 | Haiku 가 만들고 sol(GPT 6.0, medium) 이 `codex exec` 로 검토, Haiku 가 고친다. 이견 0 또는 3회에 멈춘다 |
| 라벨 표본 | 200턴 층화 표본 |
| SCHEMA 와의 충돌 | SCHEMA 에 예외 한 줄을 넣는다 |
| 이미 본 페이지 | 페이지가 "매번 실릴 부분" 을 가진다 — `Rule.` 문단. 두 번째부터는 그 문단 전문과 경로만 싣는다 (리뷰 1회차 뒤 다시 고름) |
| 전문 재전송 | compact 때만 |
| compact 감지 | transcript 에서 두 호스트 공통으로 |
| compact 후 SessionStart | 표지 + 현재 상태 보고 재주입 (지금 동작 그대로) |
| `codex-review-loop` | 절차만 스킬로. `Rule.` 과 "What goes wrong" 은 페이지에 남기고 `landmine` 유지 |
| Codex 스킬 | 설치가 Codex 스킬 폴더에도 링크한다 |
| 게이트 | pytest 고정 표본 + PR 마다 사람이 두 저장소를 재생 |

## PR 과 단계

| PR | 단계 | 게이트에서 볼 것 |
| --- | --- | --- |
| ① | 1 측정 + 라벨 | 도구가 출발점 숫자를 재현한다 |
| ② | 2·3 중복 제거 + compact 리셋 | 세션 누적 주입량 60% 이상 감소, 리콜 불변식 녹색 |
| ③ | 4 스킬로 옮기기 | 두 페이지의 전문 크기, 두 호스트에서 스킬이 보인다 |

2·3 은 떼지 않는다. 3 없이 2 가 나가면 compact 뒤로 규칙 전문이 영영 안 실린다.

## 1단계 — 측정 도구 (PR ①)

새 파일은 만들지 않는다. `tool/trigger_audit.py` 에 하위 명령 셋을 더하고, 지금의
센서스 대조는 인자 없이 부를 때 그대로 둔다.

### 기록 쪽 — `tool/trajectory.py`, `tool/inject.py`

측정할 거리를 PR ② 보다 먼저 쌓기 시작한다.

- `KEEP = 4000`
- 행에 `sent` 를 더한다. 이번 턴 `additionalContext` 전체 길이(색인·영어본·출처·구분자 포함)다.
  지금의 `cost` 는 규칙·결정 블록만 센다 — 호스트 한도와 견줄 수는 `sent` 뿐이다
- `record()` 인자는 키워드 하나만 는다. 기존 호출과 테스트는 그대로 돈다

### `trigger_audit.py replay`

```
python tool/trigger_audit.py replay <trajectory.jsonl>... --project <repo> [--until 2026-09-25T03:00]
```

세션별로 행을 시각 순으로 다시 흘려 두 방식을 나란히 낸다. 페이지는 지금의 페이지다 —
과거 실행의 재현이 아니라 "지금 규칙으로 그 발화를 받았다면" 이다.

| 낼 값 | 셈 |
| --- | --- |
| 반복률 | 같은 세션에 이미 실린 페이지를 또 실은 횟수 / 전체 페이지 적재 수. 출발점의 624회 중 457회 |
| 턴당 주입 크기 | 중앙값·p90. 지금 방식과 새 방식 |
| 세션 누적 주입량 | 세션별 합, 그 합의 중앙값과 전체 합. 감소율 |
| 한도 초과 턴 | `sent` 가 호스트 한도를 넘은 턴 수. 과거 행은 `sent` 가 없어 새 방식 재생값으로만 |
| 리콜 불변식 | 턴마다 정규식이 고른 페이지 각각의 `Rule.` 문단 전문이 새 방식의 주입에 글자 그대로 들어 있는가. 이름만 보면 강제 조항이 빠져도 녹색이 된다. 하나라도 빠지면 종료 코드 1 |
| 유휴 뒤 복귀 | 7단계용. [3묶음](token-diet-3-session.md#7단계--측정-먼저)에 셈이 있다 |

새 방식의 compact 리셋은 transcript 를 찾아 쓴다. Claude 는
`~/.claude/projects/*/<session>.jsonl`, Codex 는 `~/.codex/sessions/**/rollout-*-<session>.jsonl`.
못 찾은 세션은 "compact 없음" 으로 재생하고, 그런 세션 수를 따로 적는다 — 그 세션의 절감은
과대 추정이다.

`--until` 은 출발점 재현용이다. 데이터는 매 턴 늘어나니, 같은 끝 시각으로 잘라야 같은 수가 나온다.

완료 기준. `--until` 을 2026-09-25 측정 시각으로 두면 개요의 "출발점" 표의 반복률과
두 저장소의 중앙값·p90 이 나온다. 번역 전 크기 차이(`measure` 독스트링)는 표에 적는다.

### `trigger_audit.py latency`

```
python tool/trigger_audit.py latency --project <repo> [--runs 20]
```

- 고정 발화 3개(규칙이 0개·상시 3개·많이 걸리는 것)로 `inject.py` 를 하위 프로세스로 돌린다.
  훅이 실제로 치르는 파이썬 기동이 들어가야 한다
- 번역 끄기는 새 스위치 없이 기존 변수로 한다. `GEMINI_API_KEY=""`,
  `TRANSLATE_ENV=<없는 경로>`, `TRANSLATE_CACHE=<임시 파일>` — `test_inject.py` 가 이미 쓰는 방법이다
- p50·p95 를 낸다. 번역 포함은 `--with-translation --runs 5` 로 따로
- 데몬 있음 / 없음 두 경우는 PR ④ 부터 의미가 있다. PR ① 에서는 "없음" 만 잰다

### `trigger_audit.py label` — 리콜 정답 만들기

5단계 문턱의 근거다. 정규식이 놓쳤지만 실렸어야 할 페이지를 턴마다 적는다.

1. 표본. 두 저장소 trajectory 에서 200턴. 저장소 비율대로 나누고, 한 세션이 20턴을 넘지
   않게 하고, 상시 규칙 셋 말고는 아무것도 안 걸린 턴을 절반 이상 넣는다. 시드를 고정해
   다시 뽑아도 같은 표본이 나오게 한다
2. 후보 목록. 주입 대상 페이지 전부의 이름과 `Rule.` 첫 문장 — `rule_index` 와 같은 추출이다.
   약 40장, 6KB
3. Haiku. `claude -p --model haiku` 에 20턴씩 10묶음. 턴마다 "실렸어야 할 페이지와 한 줄 이유" 를
   JSON 으로 받는다. 정규식이 이미 고른 것도 답에 포함시키고, 비교는 도구가 한다
4. sol 검토. `codex exec --model <sol 모델 id> -c model_reasoning_effort="medium"` 에 같은 턴과
   Haiku 의 답을 파일로 준다. 라벨마다 동의·반대와 이유, 빠진 페이지를 JSON 으로 받는다
5. Haiku 수정. 반대 의견만 돌려주고 고친 답을 받는다. 반대가 0이거나 3회째면 멈춘다
6. 끝까지 남은 반대는 `disputed` 로 표시한다. 문턱을 정할 때 그 턴은 빼고, 그 수를 보고에 적는다

두 호출 방식은 `chat_session._spawn` 이 이미 쓰는 명령 모양을 따른다. 결과는
`raw/recall-labels.jsonl` 이다. `raw/` 는 커밋하지 않는다 — 이 저장소는 공개본이고, 표본에는
다른 저장소의 발화 원문이 든다. 커밋하는 것은 5단계 문서에 적는 요약 수치뿐이다.

비용. 최악의 경우 Haiku 30회와 sol 30회다. 한 번에 수십 KB 입력이라 한 번 돌리는 값은 작다.
다시 돌리는 것은 페이지가 크게 바뀌었을 때뿐이다.

착수 전에 확인할 것.

- sol 의 정확한 모델 id. `codex` 의 모델 목록에서 읽어 상수 하나로 둔다
- 과거 행은 발화가 500자에서 잘렸다. 잘린 행(`chars > 500`)은 표본에서 빼거나 따로 센다

### SCHEMA 의 예외

`SCHEMA.md` "What is not done" 의 "Nothing that needs judgement is mechanised." 뒤에 한 줄.

> The one exception is measurement labels: a model may draft them if a second,
> different model reviews every one. They choose thresholds; they never add or
> remove what the hook injects.

PR ① 에 넣는다. 기계 판정이 시작되는 PR 이 그 경계를 적는다.

## 2·3단계 — 세션 내 중복 제거와 compact 리셋 (PR ②)

### "봤다" 의 정의

한 페이지를 이 세션이 봤다고 치는 것은 세 가지가 모두 맞을 때다.

1. 그 턴에 전문으로 실렸다 (색인 줄이나 축약형이 아니라)
2. 그 턴의 `sent` 가 호스트 한도 이하였다. 넘은 턴은 호스트가 파일로 빼고 2KB 미리보기만
   줬으므로, 그 턴에 실린 전문은 안 본 것으로 친다
3. 그 턴이 마지막 compact 보다 뒤다

호스트 한도는 호스트별 상수이고, 단위가 호스트마다 다르다.

- 단위. `sent` 는 UTF-8 바이트로 적는다. 바이트 단위 BPE 에서 토큰 수는 바이트 수를 넘지 않으므로,
  바이트가 한도 이하면 토큰도 한도 이하다. 문자 수로는 이 보장이 없다 — 한글 한 글자가 토큰 여럿일 수 있다
- Codex. 설치가 `additionalContextLimit = 12000` 을 건다. 이 값은 토큰이다(`tool/apply.py` 의 주석이
  기본값을 "2,500 tokens" 로 적는다). 문턱은 12,000 바이트로 둔다 — 위 부등식으로 안전한 쪽이다
- Claude. 공개된 단위가 없다. 이 세션에서 11.6KB 와 12.1KB 의 주입이 `persisted-output` 으로 빠졌다.
  1단계 `replay` 가 transcript 에서 파일로 빠진 가장 작은 주입과 전문으로 들어간 가장 큰 주입을 찾아
  그 사이에서 정한다. 그 전까지 문턱은 8,000 바이트

문턱을 실물로 확정하지 못한 호스트는 중복 제거를 켜지 않는다. 낮게 잡을수록 전문을 더 자주 보내는
쪽으로 틀린다. 그 방향이 맞다.

### trajectory 행에 더하는 것

| 키 | 뜻 |
| --- | --- |
| `full` | 이번 턴에 전문으로 나간 페이지의 `[이름, 본문 해시]`. 해시는 슬롯을 채우고 번역한 뒤, 실제로 나간 본문의 sha256 앞 12자 |
| `tx` | 이번 턴 시점의 transcript 파일 크기(바이트) |
| `reset` | 이번 턴에서 compact 를 감지했으면 `true` |

새 상태 파일은 없다. 계획서 그대로 trajectory 가 상태다.

### 읽는 쪽 — `inject.py`

1. trajectory 를 한 줄씩 읽되, `session` 값이 문자열로 들어 있지 않은 줄은 `json.loads` 없이
   건너뛴다. 1,000행에서 몇 ms 다. 파일이 수만 행으로 커지면 그때 꼬리만 읽는다
2. 같은 세션의 마지막 `reset` 행 이후에서, "봤다" 조건을 만족한 행의 `full` 을 모은다. 본 집합의
   키는 이름과 해시의 짝이다. 세션 도중 페이지가 고쳐지면 이번 턴 본문의 해시가 달라 안 본 것이 되고,
   고친 전문이 다시 한 번 나간다(리뷰 2회차). 저장소 `.wiki` 페이지의 번역이 턴마다 조금씩 달라도
   같은 결과다 — 전문을 더 보내는 쪽으로만 틀린다
3. compact 감지. 직전 행의 `tx` 부터 transcript 끝까지만 읽어서 Claude 의 `"compact_boundary"`
   나 Codex 의 `"type":"compacted"` 가 있는지 본다. 매 턴 새로 붙은 부분만 읽으므로 transcript 가
   수십 MB 여도 작다. 있으면 본 집합을 비우고 이 행에 `reset: true`
4. 이번 턴에 정규식이 고른 규칙 중 본 집합에 있는 것은 전문 대신 "반복형" 으로 싣는다.
   `rule_index` 는 그대로 맨 앞이다

반복형은 제목, `Rule.` 문단 전문, 경로다.

```
<!-- wiki:operator/ask-with-arrow-key-options (contract, repeated) -->
# A decision the user owns is asked as options, not as prose

Rule. Where the user's judgement is needed, ... **Calling Codex's
`request_user_input_async` is forbidden outright.** ...

Loaded in full earlier this session: `operator/ask-with-arrow-key-options.md`
```

- `shrink` 가 지금 잡는 것은 `Rule.` 로 시작하는 한 줄뿐이라 80자에서 문장이 잘린다. 빈 줄까지의
  문단으로 고친다. 예산 축약(`fit`)도 같은 함수를 쓰니 함께 고쳐진다
- 반복형이 바닥이다. `fit` 은 예산이 남으면 둘째 바퀴에서 `shrink(hard=True)` — 제목과 경로만 — 로
  내려가는데(`tool/inject.py` 의 `fit`), 그러면 `Rule.` 문단이 빠진다. 둘째 바퀴는 `Rule.` 문단이 없는
  페이지에만 적용하고, 문단이 있는 페이지는 반복형 아래로 줄이지 않는다. 예산을 넘길 수 있지만,
  예산은 이미 "축약 목표" 이고 넘을 수 있다고 `trigger_audit` 이 적는다. 지금 `rule_budget` 을 거는
  어댑터는 없다
- 리뷰 1회차가 짚은 대로, 색인의 첫 문장만으로는 강제 조항이 빠진다. `ask-with-arrow-key-options` 의
  비동기 금지는 둘째 문장이고, `agent-delegation` 의 셀 배정은 문단 뒤 불릿과 표다
- 그래서 페이지 쪽 일이 있다. 매 턴 지켜야 하는 조항이 `Rule.` 문단 밖에 있는 페이지는 PR ② 에서
  그 조항을 문단 안으로 옮긴다. 대상은 주입 대상 허브 페이지 전부를 한 번 읽어 고르고, 목록을 PR 에
  적는다. 적어도 `agent-delegation`(불릿 넷과 셀 배정 표)과 `ask-with-arrow-key-options`(불릿의 추천
  순서·기본값 규칙)다
- `lint` 가 본다. 주입 대상 페이지에 `Rule.` 문단이 있고, 길이가 1,200자 이하인가. 문단이 길어지는
  것은 반복형이 커지는 것이라 상한을 둔다
- `Rule.` 문단이 없는 페이지(저장소 지식)는 반복형이 없으므로 중복 제거에서 빼고 매번 전문을 싣는다
- 상시 3장의 반복형은 합쳐 약 2KB 로 본다(지금 9KB). 조항을 옮긴 뒤의 실제 크기는 `replay` 로 잰다
- 결정 기록은 이미 두 줄 요약이라 건드리지 않는다
- `systemMessage` 에 `· 이미 실림 N장` 을 붙인다
- 모든 규칙이 이미 실린 턴에도 반복형은 전부 나간다. 머리말과 `source_map` 도 그대로 둔다 —
  합쳐 수백 자이고, 빼는 분기를 따로 두면 그 분기가 반복형까지 빼는 실수가 생긴다(리뷰 2회차)

두 호스트의 기록 형식은 2026-09-25 에 실물로 확인했다. Claude transcript 에
`"subtype":"compact_boundary"`, Codex rollout 에 `"type":"compacted"` 가 있다.

### 거꾸로 가는 쪽이 안전하다

- `--project` 가 없거나, `transcript_path` 가 없거나, 읽다가 예외가 나면 본 집합은 비어 있는
  것으로 친다. 오늘처럼 전부 싣는다. 틀리면 토큰을 더 쓰는 쪽으로만 틀린다
- 반대 방향 — 안 본 것을 봤다고 치는 것 — 이 이 위키가 막으려는 실패다
  (`craft/hooks-fail-open`)

### compact 뒤의 SessionStart

`session_state.py` 는 고치지 않는다. 설치된 `SessionStart` 훅에는 matcher 가 없어서 compact 에도
이미 불리고, 보고를 다시 싣는다. 그것이 고른 동작이다. 계획서가 적었던 "compact 표지 행" 은
transcript 감지로 대신하므로 필요 없다. 다만 compact 에서 실제로 불리는지는 PR ② 에서 한 번
실물로 확인하고 적는다.

### 착수 전에 확인할 것

- Codex 의 `UserPromptSubmit` 입력에 `transcript_path` 가 오는가. 안 오면 Codex 는 중복 제거를
  끄고 그렇게 적는다
- 자동 compact 가 훅 뒤에 일어나는 턴. 훅이 "봤다" 로 적은 뒤 같은 턴에 compact 가 나면, 다음 턴의
  감지가 리셋한다. 그 한 턴의 전문이 compact 요약에 살아남는지는 실물로 본다

### 테스트 — `tool/test_inject.py`

- 같은 세션 두 번째 턴: 전문 대신 반복형이 나가고, 그 안에 `Rule.` 문단 전문이 있다
- `sent` 가 한도를 넘은 턴의 전문은 본 것으로 치지 않는다
- 모든 규칙이 이미 실린 턴에도 각 페이지의 `Rule.` 문단 전문이 나간다
- `rule_budget` 을 아주 작게 건 어댑터에서도 `Rule.` 문단이 있는 페이지는 반복형 아래로 안 줄어든다
- 첫 턴 뒤 페이지 본문을 고치면 다음 턴에 전문이 다시 나간다
- transcript 의 새 부분에 `compact_boundary` 가 있으면 다시 전문이 나간다
- `--project` 없음, transcript 없음, 깨진 trajectory 줄: 전부 싣는다
- 리콜 불변식: 고정 표본 trajectory 를 `tool/` 테스트 자료로 두고, 턴마다 정규식이 고른 페이지의
  `Rule.` 문단 전문이 주입에 글자 그대로 있는지 본다. 이름이 아니라 내용을 본다. 9단계 게이트의 pytest 쪽이다. 표본은 이 저장소의 발화에서 개인 내용
  없는 것만 골라 만든다

완료 기준. 1단계 `replay` 에서 세션 누적 주입량이 60% 이상 준다. 리콜 불변식 녹색.

## 4단계 — 스킬로 옮기기 (PR ③)

두 스킬은 이미 있다. `skills/after-merge/SKILL.md` 와 `skills/review-loop/SKILL.md` 가 절차를
갖고 있어서, 지금은 페이지와 스킬에 같은 절차가 두 벌이다. 이 단계는 옮기기보다 페이지 쪽
사본을 지우는 일에 가깝다.

### 순서

1. 페이지의 번호 절차와 스킬 본문을 나란히 놓고, 페이지에만 있는 문장을 스킬로 옮긴다.
   빠뜨린 것이 없다는 확인이 이 PR 의 리뷰 대상이다
2. 페이지를 줄인다

| 페이지 | 남는 것 | 스킬로 가는 것 |
| --- | --- | --- |
| `operator/after-merge-cleanup` (`contract`, 2.7KB) | 제목, `Rule.` 문단, 슬롯 줄(`{server_stop}`·`{scratch_dirs}`), "스킬 `after-merge` 를 부른다" | 번호 절차 1~N |
| `operator/codex-review-loop` (`landmine`, 5.7KB) | 제목, 첫 문단(누가 리뷰어인가), `Rule.` 문단, "What goes wrong", 슬롯 줄(`{review_dir}`·`{gate_cmd}`·`{live_cmd}`), "스킬 `review-loop` 를 부른다" | 절차와 명령 예시 |

- 슬롯 줄이 페이지에 남는 이유. 스킬은 저장소마다 같은 파일이라 `fill()` 이 닿지 않는다. 이
  저장소의 서버 종료 명령이나 리뷰 폴더는 주입된 페이지만 안다
- 트리거와 `severity` 는 그대로다. 규칙이 실리는 턴은 같고 실리는 양만 준다
- 2단계와 겹치면, 줄어든 전문이 세션에 한 번 실리고 그 뒤로는 색인 한 줄이다

### Codex 에서도 스킬이 보이게

지금 `~/.claude/skills/after-merge` 와 `review-loop` 는 이 저장소의 `skills/` 를 가리키는 링크고,
Codex 쪽 스킬 폴더에는 없다. 링크는 README 가 "한 번 걸면 된다" 고만 적었고 도구가 만들지 않는다.

- `tool/setup_agents.py` 가 `skills/*` 를 Claude 와 Codex 스킬 폴더 양쪽에 링크한다. 이미 같은
  곳을 가리키면 아무것도 안 한다. 다른 곳을 가리키는 같은 이름이 있으면 건드리지 않고 알린다
- Windows 는 관리자 권한이 필요 없는 디렉터리 정션으로 건다
- Codex 가 읽는 폴더가 `~/.codex/skills` 인지 `~/.agents/skills` 인지는 설치된 버전에서 확인해
  하나로 정한다. 확인은 Codex 세션에서 스킬 목록에 `after-merge` 가 뜨는 것으로 한다
- README 의 스킬 문단을 이 동작으로 고친다

완료 기준. 두 페이지의 주입 크기(1단계 `replay` 의 페이지별 크기)가 줄고, 두 호스트 모두에서
스킬이 목록에 뜬다.

## 9단계 — 이 묶음의 게이트

PR ①②③ 각각 끝에 돌린다.

1. `pytest tool/`
2. `python tool/lint.py --check`
3. 두 저장소 `replay`. 전후 수치를 [개요](token-diet.md)의 단계 표 상태 칸에 적는다 — 예:
   "완료 — 세션 누적 12.4KB→4.1KB 중앙값, 반복률 73%→0%, 리콜 불변식 녹색"
4. `latency` 20회. PR ② 이후 p95 가 PR ① 기준보다 50ms 넘게 늘면 멈추고 원인을 본다

재생은 사람이 돌린다. trajectory 는 커밋하지 않는 파일이라 CI 나 다른 PC 에서는 비어 있다.
pytest 의 고정 표본이 그 사이를 막는다.
