# ai-coding-agent-wiki

코딩 에이전트가 프로젝트를 옮겨 다녀도 같은 실수를 다시 하지 않게 하는 위키와
그것을 프로젝트에 붙이는 어댑터.

Karpathy 의 [LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
명세를 코딩 에이전트 쪽으로 각색했다. 원안의 원시 소스가 논문·기사라면 여기서는
대화 로그와 실행 기록이고, 그래서 수집이 "읽고 요약"이 아니라 "세고 대조"다.

병목은 저장도 검색도 아니었다. 적힌 것이 행동을 지배하지 못하는 것이었다.
그래서 이 위키는 페이지를 더 만드는 도구가 아니라, 두 가지를 하는 도구다.

1. 반복 지시를 관습으로 굳힌다 — 지시문을 스킬 하나로
2. 가능한 규칙을 검사로 바꾼다 — 실제로 지켜진 규칙들은 산문이 아니라 던지는
   가드였고 빨개지는 게이트였다

규약은 [`SCHEMA.md`](SCHEMA.md), 강제 방식은 [`ENFORCEMENT.md`](ENFORCEMENT.md),
검진과 갱신 절차는 [`MAINTENANCE.md`](MAINTENANCE.md) 에 있다. 페이지를 쓰거나
고치기 전에 읽는다.

## 구조

```
tool/        census · intersect · apply · inject · korean_progress
             trigger_audit · lint · repo_lint · graph · repo_graph
  markers/   census 표지 (언어별)
operator/    사람을 따라다니는 지식 — 리뷰 루프 · diff 로 수정 · 한국어 진행
craft/       기술을 따라다니는 지식 — 비동기 수신 · 끝까지 수행 · git 차단
skills/      반복 지시를 굳힌 절차 (강제 3층) — 리뷰 루프 · 머지 후 · 회고
adapters/    프로젝트별 슬롯 값
raw/         census 출력과 측정 기록. 불변
graph.json   graph 가 만드는 정책 그래프. 뷰는 이것을 읽는 소비자다
web/         채팅 화면과 위키 지도. `chat.py` 가 `/api/graph` 로 자료만 준다
```

`project` 범위의 지식은 여기 없다. 대상 저장소에 살고, 어댑터가 읽어 합성만
한다. 남의 지뢰를 들이지 않는다 — 그 자체가 사고다.

## 쓰는 법

새 프로젝트를 붙일 때는 census 부터 돈다. 무엇이 고장 나는지 모르면 무엇을
적어야 하는지도 모른다.

```bash
python tool/census.py --project ~/PycharmProjects/<name> --out raw/census-<name>.jsonl
python tool/intersect.py raw/census-*.jsonl
```

출력이 그 프로젝트의 어댑터 초안이 된다. 슬롯 값을 대상 checkout의 `.wiki/adapter.toml`에
채우고 붙인다. 로컬 adapter가 없는 기존 설치는 `adapters/<이름>.toml` 조회를 유지한다.

```bash
python tool/apply.py --project ~/PycharmProjects/<name>            # 미리 본다
python tool/apply.py --project ~/PycharmProjects/<name> --write    # 쓴다
```

기본 `apply` 가 쓰는 것은 `.claude/settings.json` 하나뿐이다 — 페이지가 선언한
`enforce.deny`(1층)와 주입 훅(2층). 기존 설정은 합치고 덮지 않는다.

### 팀원 설치 도구

`tool/setup_agents.py`는 환경·위키 버전·호스트를 검사한 다음 기존 `apply.py`로 설치·검증한다.
프로젝트명이나 형제 폴더명에 의존하지 않으며 adapter를 허브에 복사하지 않는다.
Python 3.11 이상·PyYAML·Git과 선택한 호스트 CLI가 필요하다.
Windows의 이 위키 명령은 Claude에 Git Bash, Codex에 PowerShell을 사용한다.

```powershell
python tool/setup_agents.py --project "D:/팀 작업/checkout" --agent both
python tool/setup_agents.py --project "D:/팀 작업/checkout" --agent both --check
```

대상에는 `.wiki/wiki-revision`(사용할 위키의 40자리 커밋 SHA), `.wiki/adapter.toml`을 둔다.
`agents = ["claude", "codex"]`와 `[slots]`의 `review_dir`, `gate_cmd`, `live_cmd`,
`server_stop`, `scratch_dirs`를 프로젝트에 맞춘다. Codex는 `.codex/config.toml`의
`[features] hooks = true`가 필요하다. `AGENTS.md`·`CLAUDE.md` 등 프로젝트 규칙 진입점은 프로젝트가 소유한다.
도구는 의존성 다운로드·버전 변경·신뢰 승인을 자동 수행하지 않는다.

`--agent claude|codex|both`로 고른 설치와 이미 설치된 호스트를
대상의 `.wiki/installed-agents.json`에 보존한다. 이 파일과 생성 hook 설정은 프로젝트 Git에서 제외한다.
기존 사용자 hook·설정은 병합하고, 실패하면 이번 설치가 쓰던 파일을 원래 바이트로 복구한다.
재설치·폴더명 변경·동명 checkout도 각자의 로컬 adapter를 사용한다. 이동 뒤에는 새 경로로 재설치한다.
성공은 종료 코드 0, 실패는 2다. `--check`는 읽기 전용이다.

기본 설치는 고정 SHA와 실행 코드·규칙이 다른 작업본을 거부한다.
`--allow-dirty-wiki`는 미커밋 개발 검증 전용이며 SHA 일치는 여전히 요구한다.
프로젝트의 고정 SHA는 공용화 코드를 포함하고 설치 검증을 통과한 커밋으로 지정한다.
위키를 갱신할 때도 후보 커밋의 설치를 확인한 뒤 고정 SHA를 함께 갱신한다.

설치 검사와 호스트의 자동 이벤트·질문 UI는 별도 증거다. 새 세션에서 프로젝트와 hook을 직접
검토·신뢰하고 네 이벤트의 실제 전달을 확인한다. Codex의 프로젝트 신뢰와 hook 정의 신뢰는
[공식 hook 안내](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)를 따른다.
선택형 질문은 그 세션에서 허용된 `request_user_input`으로 직접 확인하며 async로 우회하지 않는다.

### 이 저장소에도 붙인다

위키를 고치는 세션에도 위키가 실려야 한다.

허브도 두 agent 가 다 설치 대상이다. Claude 만 붙이면 이 저장소에서 도는
Codex 셀은 위키 훅이 하나도 안 걸린 채 돈다

```bash
python tool/apply.py --project . --write                 # Claude
python tool/apply.py --project . --agent codex --write   # Codex
```

`.claude/` 와 `.codex/` 는 담지 않는다. 인터프리터 경로가 기계마다 다르므로
클론한 쪽에서 이 명령을 다시 돌린다.

설치와 실행은 다른 증거다. 위 명령이 성공했다는 것은 설정 파일이 생겼다는
뜻이지 호스트가 그 이벤트를 실제로 전달한다는 뜻이 아니다. Codex 는 `/hooks`
에서 신뢰해야 돌고, 신뢰 설정은 `apply` 가 자동으로 쓰지 않는다. 걸렸는지는
`.wiki/trajectory.jsonl` 에 그 세션의 줄이 실제로 생기는지로 확인한다.

설치 상태만 보는 검사는 따로 있다 — 종료 코드로 답한다.

```bash
python tool/apply.py --project . --check                 # 이 저장소의 Claude 배선
python tool/apply.py --project . --agent codex --check   # 같은 것의 Codex 배선
python tool/lint.py --check                              # 기대 agent 전부
```

`CLAUDE.md` 는 안 건드린다. 거기엔 이 위키가 소유하지 않는 project 범위 지식이
있고, 항상 로드되는 파일에 문장을 더 넣는 것은 이 위키를 만들게 한 문제
그 자체다. 스킬은 `operator` 범위라 `~/.claude/skills/` 에 한 번 걸면 된다.

### Codex에 연결

이 모드는 대상의 `.codex/hooks.json`만 합쳐 쓴다. 인터프리터와 위키 경로는
설치 시 결정되므로 다른 기계에서는 다시 설치한다. 기존 Claude 설정과 사용자
`CODEX_HOME`의 Orca hooks는 건드리지 않는다. Codex의 hooks 기능과 프로젝트
신뢰가 켜져 있어야 하며, 설치 후 `/hooks`에서 새 위키 hooks 다섯 개를 검토하고
신뢰해야 실행된다. 신뢰 해시를 설치 도구가 대신 쓰지는 않는다.

발화 주입·세션 상태·자동 갱신은 Claude와 같은 도구를 쓴다. 종료 검사는 Codex의
공식 `last_assistant_message`를 읽으며, 전사 파일 형식을 추측하지 않는다.
`codex_pretool.py`는 위키의 도구 이름 차단·`Bash(...)` 인자 패턴과 기존 diff·한국어 검사를
적용한다. `request_user_input_async`와 `functions.request_user_input_async`는 기존
`enforce.deny` 선언으로 호출 자체를 금지한다. 선택지 유무와 관계없으며, 허용된
`request_user_input`을 사용한다. Codex가 도구 설명을 제공하지 않으면 한국어 검사는 판정할 값이 없다.
셸 검사는 알려진 직접 명령 형태에 한정된다. 중첩 셸, 동적 명령, 모든 PowerShell
쓰기 방식까지 막는 보안 경계가 아니며 `permissions.deny` 전체를 이식하지 않는다.

주입 한 건의 파일 미리보기 전환 문턱은 12,000 토큰이다. 그보다 커지면 Codex가 전문 경로를 준다.

검증: `python -m pytest -q tool/test_codex_hooks.py`. 임시 저장소에 설치한
명령을 실행해 실제 주입·차단·허용·갱신과 기존 설정 보존을 확인한다.
Windows에서는 `pwsh`로 검사한다. Codex용 명령에는 PowerShell의 호출 연산자
`&`를 붙이며, 기존 설치는 위 `--write` 명령으로 갱신한 뒤 `/hooks`에서 다시 신뢰한다.
Codex의 이벤트 자동 실행은 신뢰 승인 뒤 별도로 확인해야 한다.

### census 가 세는 것

| 부류 | 무엇 |
| --- | --- |
| 반복 지시 | 같은 말을 몇 번 다시 쳤나. 이미 적혀 있는데 다시 쳤다면 그 규칙은 작동하지 않는다 |
| 교정 | 내가 틀렸다고 말한 자리 |
| 재개 요구 | 멈추지 말았어야 할 자리에서 멈춰 다시 밀어야 했던 자리 |
| 부분 수행 | 시킨 것 중 일부만 하고 나머지를 다시 시킨 자리 |

표지에 안 걸린 표본을 찍어 준다. 그 절이 없으면 census 는 표지를 쓴 사람의
편향을 잰다.

백분율은 안 낸다. 문자열 대조로는 같은 규칙이 다른 말로 적힌 것을 못 잡는다. 대신 대조할 문장을
뽑아 주고 판정은 사람이 한다.

## 보기

```bash
python tool/graph.py --project ~/PycharmProjects/<name> --project ...
tool/chat.cmd                      # http://127.0.0.1:8787 · 왼쪽 아래 "위키 지도"
tool/chat.command                  # macOS·Linux에서는 이쪽
```

지도는 `web/` 안에 있다. 옵시디언에서 살아 있는 힘 배치,
끌기, 확대·이동, 이웃 강조, 검색은 가져오고 노드의 뜻은 바꿨다. 옵시디언의
노드는 사람이 쓴 생각이고 크기는 링크 수다. 여기 노드는 세션 로그를 세서 만든
규칙이고 크기는 그 규칙이 한 턴에 싣는 글자수다 — 페이지가 느는 것 자체가
비용이라는 것을 화면에서 보이게 하려고 그렇게 뒀다.

옵시디언에 없는 축이 둘이다.

- 공동 주입. 두 페이지가 실제 발화에서 같은 턴에 함께 실린 횟수이고, 점선의
  굵기가 그것이다.
- 프로젝트. 탭을 바꾸면 그 저장소의 `.claude/settings.json` 을 읽어 실제로
  붙은 규칙만 진하게 보인다. 안 붙은 것은 비어 보이고, 어댑터에 안 채워진
  슬롯도 같이 뜬다. 옵시디언 그래프는 한 보관함 안이라 이 물음이 없다.

## 채팅: 정확한 답변과 쉬운 설명

팀원은 [채팅 설치·본인 계정 로그인 안내](docs/chat-setup.md)를 따른다.
처음에는 `python tool/setup_chat.py install --agent codex` 또는 `--agent claude|both`로 준비한다.
작성자의 개인 경로·로그인 정보를 사용하지 않고, 각 PC의 CLI와 계정을 사용한다.
프로젝트 위치는 위키의 상위 폴더가 기본이며 설치 때 `--workspace`로 바꿀 수 있다.

`tool/chat.cmd`(macOS·Linux는 `tool/chat.command`)로 켜고 프로젝트·모델·추론 강도를 고른다. 선택한 CLI에 먼저 로그인해야 한다.
Codex 모델은 이름을 고정하지 않고 설치된 CLI의 `model/list`에서 가져온다.
모델마다 지원하는 추론 강도만 표시하고, 선택한 모델 ID를 두 호출의 `--model`에 명시한다.
목록을 읽지 못하면 오류를 표시한다. 계정이나 CLI를 바꿨다면 서버를 다시 켜 목록을 갱신한다.
조회 형식은 [Codex App Server의 모델 목록](https://learn.chatgpt.com/docs/app-server#models)을 따른다.

답변 위의 **1. 정확한 답변 / 2. 쉬운 설명** 버튼으로 전환한다. 원문이 먼저 나오고
쉬운 설명을 추가로 생성하므로 두 번째 호출의 시간·사용량이 더 든다. 둘 다 기록에 저장하며,
쉬운 설명 생성이 실패해도 원문은 남긴다. 예전 기록에는 쉬운 설명을 소급 생성하지 않는다.

- [원문 프롬프트](tool/prompts/chat-answer.md): 문서 탐색·출처 확인·충돌 대조·검증 범위 구분.
  저장소 안에서 근거를 읽고 인용하며, 실제 확인하지 못한 부분은 구분한다.
  내부 작업 이름의 뜻과 수치가 무엇을 센 것인지도 출처에서 확인해 응답에 포함한다.
- [쉬운 설명 프롬프트](tool/prompts/chat-explain.md): 완성된 원문만 JSON으로 받아 의미를 보존하며 풀어쓴다.
  원문 프롬프트·질문·검색 기록·채널 지시는 전달하지 않는다. 별도 임시 폴더와 새 세션에서
  검색 도구 없이 실행한다. 수치·조건·부정·미확인 사항·출처를 보존하고 전문 용어를 풀어쓴다.
  기준 독자는 오늘 처음 참여한 사람이다. 이전 대화나 개발 지식을 요구하는 표현 대신
  무엇을 하는 작업인지·끝난 일·확인이 필요한 일부터 설명한다. 원문에 없는 배경은 만들지 않는다.

각 프롬프트는 영어이며 한국어 출력을 지정한다. 역할 선언보다 수행 순서·입출력 경계·
보존 조건·충실한/잘못된 변환 예시에 집중한다.
[공식 프롬프트 지침](https://developers.openai.com/api/docs/guides/prompt-engineering)과
[추론 모델 지침](https://developers.openai.com/api/docs/guides/reasoning-best-practices)을 참고했다.
쉬운 설명은 원문에 대한 별도의 사실 검증이 아니다. 각 답변의 `파일:줄`을 눌러 근거를 직접 볼 수 있다.

‘공통 프로젝트’는 진척도·진단·회고·리뷰·위키 다섯 채널이 함께 사용한다. 대화 문맥과
기록은 프로젝트·채널별로 보존하므로 다른 프로젝트에 갔다 돌아와도 이어진다.
서버 재시작 때도 프로젝트 선택과 기록에 남은 CLI 세션을 복원한다. ‘문맥 비우기’는
선택한 프로젝트의 해당 채널에만 적용하며 기록은 지우지 않는다. 프로젝트 정보가 없는
옛 기록은 ‘프로젝트 미분류 이전 기록’에서 확인하며 인계문에는 섞지 않는다.
외부 브리핑을 넣는 `chat_post.py`도 `--project <경로>`를 지정해야 한다.
같은 CLI 안에서는 모델을 바꿔도 원래 대화를 이어간다. Claude와 Codex 사이를 바꾸면
새 문맥을 시작한다. 화면의 ‘관련 규칙’은 표시용 대조이며
실제 호스트가 훅을 전달했다는 증거가 아니다. 표시 때문에 훅을 재실행하지 않는다.

검사: `python -m pytest -q tool/test_chat.py`, `npm --prefix web run build`,
`npm --prefix web run lint`. CLI 이벤트·세션 분리·실패 시 원문 보존·모델/추론 강도 검증을 확인한다.
이 자동 검사는 모든 모델 응답의 정확도나 쉬운 설명의 품질을 보장하지 않는다.
실제 진척도 응답의 품질을 시험할 때는 먼저 화면의 ‘이 채널 문맥 비우기’를 누르고
초기화가 끝난 뒤 새로 질문한다. 과거 원문을 다시 풀어쓰는 검사는 이 전체 흐름 검사와 구분한다.
검수할 때는 본문만 읽어도 작업의 목적·현재 상태·남은 일이 이해되는지와, 원문의 수치가
무엇을 세는지·조건·미확인 사항이 그대로인지 따로 대조한다. 용어에 괄호 설명만 붙이거나
‘지시가 빠졌다’를 ‘답변이 틀렸다’로 바꾼 응답은 통과시키지 않는다.

## 유지보수

Codex 훅이 시간 초과되기 전 실행 스택과 프로세스 정보를 로컬에 자동 수집한다.
설치 상태·로그 위치·보관 기간은 [훅 자동 진단](tool/hook-diagnostics.md)에 있다.

```bash
python tool/lint.py --repo ~/PycharmProjects/<name>      # 허브 위키
python tool/lint.py --check                              # 실제 배선까지 (종료 코드 1 로 실패)
python tool/repo_lint.py --repo ~/PycharmProjects/<name> # 붙은 저장소
python tool/trigger_audit.py raw/census-*.jsonl          # 공유 규칙만 — 지식 축은 미측정
```

`trigger_audit` 의 기본은 공유 규칙만 잰다. 지식 축(결정 기록)까지 재려면
그 저장소의 census 와 `--project` 를 같이 준다.

```bash
python tool/trigger_audit.py raw/census-<name>.jsonl --project ~/PycharmProjects/<name>
```

`--project` 없이 돌린 출력의 지식 축은 `0` 이 아니라 미측정이다.

`lint` 는 구조가 썩는 자리를 잡고, census 재실행은 내용이 썩는 자리를 잡는다 —
페이지를 썼는데도 그 실패가 안 줄었다면 산문을 다시 쓸 게 아니라 사다리를
올려야 한다. 언제 무엇을 돌리고 발견을 어떻게 처리하는지는
[`MAINTENANCE.md`](MAINTENANCE.md) 에 있다.

`tool/test_lint.py` 는 검사가 실제로 빨개지는지 본다. 발견 0건짜리 초록은
검사가 도는 증거가 아니다.

## 상태

서 있는 것과 붙어 있는 것은 다르다. 층이 다 섰다는 것은 이 저장소에 기계가
있다는 뜻이고, 어느 저장소에 실제로 걸렸는지는 `lint --check` 만 안다.

`python` 은 `yaml` 과 `tomllib` 를 읽을 수 있어야 한다. `apply` 가 훅을 쓰기
전에 대상 인터프리터로 확인한다 — 못 읽으면 훅이 조용히 아무것도 안 하고,
그게 강제 계층의 가장 나쁜 실패 모양이다.

## 공개 사본의 근거 기록

원본의 규칙·스킬·적용 조건·등급은 유지하고 실제 대화·사례·측정 기록만 제외했다.
`sources_withheld: true`는 원본 근거가 비공개임을 나타낸다. 이 표시가 있는 기존 규칙에만
lint의 근거 누락 예외를 적용하며, 새 규칙의 근거를 대신하지 않는다.
설치와 본인 CLI 로그인은 [설치 안내](docs/chat-setup.md), 공개본 관리는
[갱신 안내](docs/publishing.md), 검증 범위는 [검사 기록](docs/verification.md)을 따른다.
