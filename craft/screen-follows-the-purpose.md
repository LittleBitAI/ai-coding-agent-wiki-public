---
scope: craft
severity: contract
triggers: ["프[런론]트 ?엔드|front-?end", "(?<![A-Za-z])design(?:[.]md|ing|s)?(?![A-Za-z])|디자인", "(?<![A-Za-z_-])UI(?![A-Za-z_-])|(?<![A-Za-z_-])UX(?![A-Za-z_-])", "레이아웃|layout|여백|패딩|ai ?slop", "타이포|typograph|폰트|글꼴", "색 ?(배합|조합|감)|팔레트|palette|컬러|color ?(scheme|palette|token)", "대시보드|dashboard|랜딩 ?페이지|landing ?page|상세 ?페이지", "애니메이션|animation|모션|(?<![A-Za-z])motion(?![A-Za-z])|트랜지션", "화면을? ?(짜|그리|만들|다듬|손보)", "Tailwind|shadcn|(?<![A-Za-z])CSS(?![A-Za-z])|스타일링"]
slots: []
sources: []
sources_withheld: true
links: [screen-ownership-before-wiring, ask-with-arrow-key-options, do-the-whole-instruction, run-inside-this-session]
---

# 화면은 목적을 따르고, 손질은 순서를 따른다

규칙. 화면을 만들라는 말에 **상세 페이지와 대시보드부터 짓지 마라.** 먼저 누가
무엇을 하러 오는지를 한 줄로 적고, 그 한 줄이 고르게 한다 — 무엇을 한 화면에
두고 무엇을 미루는가. 스케치가 서면 아래 순서대로 훑는다. 순서를 바꾸지 않고,
네 번째에서 사용자에게 넘긴다.

| # | 무엇을 보나 | 무엇으로 | 통과 기준 |
| --- | --- | --- | --- |
| 1 | 이 프로젝트의 목적에 맞는 화면 구성 | `DESIGN.md` · `better-layout` | 화면 목록이 목적 한 줄에서 나왔다 |
| 2 | 패딩·폭·정렬이 일정한가, 버튼이 실제로 불리는가 | 브라우저 (`claude-in-chrome`) | 눈이 아니라 **잰 값**으로 답했다 |
| 3 | 타이포그래피 위계 | `better-typography` | 단계가 세어지고 쓰임이 안 겹친다 |
| 4 | 색 배합 | `better-colors` → **사용자에게 선택지로** | 사용자가 골랐다 |
| 5 | 남은 여백 | 타이포 · 인포그래픽 | 채울 **값**이 있는 자리만 채웠다 |

걸음의 구체는 `design-pass` 스킬이 든다. 이 페이지는 왜 그 순서인가를 든다.

어겼을 때. 되돌리는 단위가 화면이다. 목적을 안 정하고 지으면 상세 페이지와
대시보드는 나오는데 그 프로젝트가 무엇을 하는 곳인지는 어느 화면에도 안 보인다.
순서를 바꾸면 앞 걸음을 다시 한다 — 색을 먼저 고르면 레이아웃이 바뀔 때 다시
고르고, 여백을 먼저 채우면 무엇이 여백이었는지 모르게 된다.

## 순서가 그 순서인 이유

- 2번이 3번보다 먼저다. 위계는 화면이 실제로 서 있어야 판정된다. 정렬이
  어긋난 채로 글자 크기를 고치면 무엇 때문에 이상한지 안 갈린다. 그리고 이
  걸음의 판정은 소감이 아니라 값이다 — "일정해 보인다" 는 판정이 아니다.
- 4번은 사용자 차례다. 색은 취향이고 브랜드다. 에이전트가 골라 두면 사용자가
  다시 고르므로, 후보를 만들어 [[ask-with-arrow-key-options]] 로 넘긴다.
  선택지마다 라벨이 아니라 결과를 적는다 — 무엇이 강조되고 무엇이 물러나는가.
- 5번이 마지막이다. 채우는 것은 비어 있음을 확인한 뒤에 한다. 그리고 채울
  것이 없으면 안 채운다. 자리를 메우려고 만든 숫자는 인포그래픽이 아니다.

다섯을 다 한다. 하나씩 시킬 때까지 기다리지 않는다 — [[do-the-whole-instruction]].

## 어느 스킬을 부르나 — 용도가 정한다

| 일 | 스킬 | 어디 것 |
| --- | --- | --- |
| 묶기 · 정렬 · 읽는 순서 · 점진적 공개 | `better-layout` | jakub |
| 타이포 스케일 · 줄바꿈 · 잘림 | `better-typography` | jakub |
| 팔레트 · 시맨틱 토큰 · 대비 | `better-colors` | jakub |
| 반경 · 광학 정렬 · 표면 깊이 · 클릭 영역 | `better-ui` | jakub |
| 접근성 · 키보드 · ARIA | `better-accessibility` | jakub |
| 버튼 글자 · 오류 문구 · 빈 상태 | `better-writing` | jakub |
| 위 여섯을 한 번에 | `better-interface` · `interface-review` | jakub |
| 모션을 새로 만든다 | `animate` | emil |
| 있는 모션을 평가 · 감사한다 | `review-animations` · `improve-animations` | emil |
| 모션을 넣을 자리를 찾는다 | `find-animation-opportunities` | emil |
| 폴리싱의 판단 기준 | `emil-design-eng` · `apple-design` | emil |
| 시안을 여럿 놓고 고른다 | `prototype` · `variant` | 둘 다 |

경계는 하나다. 정지한 화면은 jakub, 움직이는 것은 emil.

모션은 이 다섯 걸음 안에 없다. 움직임을 만들거나 고치는 일이면 이 과정을 돌지
말고 emil 로 바로 간다 — 다른 일이다.

## 값은 `DESIGN.md` 가 갖는다 — 이 페이지는 형태만 든다

여기 적힌 것은 순서와 판정 기준이다. 색·글꼴·간격의 실제 값은 프로젝트마다
다르고, 그 값을 이 페이지에 적으면 다음 프로젝트에서 틀린다. 슬롯이 있는 이유와
같은 이유다.

값은 프로젝트 루트의 `DESIGN.md` 가 갖는다. Google Labs 의 공개 형식이고,
front matter 에 토큰(`colors` · `typography` · `spacing` · `rounded` ·
`components`)을, 본문에 그렇게 고른 이유를 담는다.

- 골라 오기 — <https://getdesign.md/>
- 형식 — <https://github.com/google-labs-code/design.md>

없으면 1번에서 만들고, 있으면 1번에서 읽는다. 2~5번의 판정은 전부 그 파일과의
대조다. "페이지마다 다른 파랑" 은 취향 문제가 아니라 대조할 값이 없었다는
뜻이다.

## 이 페이지가 끝나는 자리

여기까지는 화면이 무엇을 보여 주는가다. 그 화면이 서버에 쓰거나 다시 읽기
시작하면 정할 것이 셋 더 있고, 그것은 [[screen-ownership-before-wiring]] 이
든다. 브라우저를 띄우는 자리는 [[run-inside-this-session]] 의 규칙을 그대로
받는다 — 이 셀 안에서 띄운다.
