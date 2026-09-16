---
scope: craft
triggers:
- 프[런론]트 ?엔드|front-?end
- (?<![A-Za-z])design(?:[.]md|ing|s)?(?![A-Za-z])|디자인
- (?<![A-Za-z_-])UI(?![A-Za-z_-])|(?<![A-Za-z_-])UX(?![A-Za-z_-])
- 레이아웃|layout|여백|패딩|ai ?slop
- 타이포|typograph|폰트|글꼴
- 색 ?(배합|조합|감)|팔레트|palette|컬러|color ?(scheme|palette|token)
- 대시보드|dashboard|랜딩 ?페이지|landing ?page|상세 ?페이지
- 애니메이션|animation|모션|(?<![A-Za-z])motion(?![A-Za-z])|트랜지션
- 화면을? ?(짜|그리|만들|다듬|손보)
- Tailwind|shadcn|(?<![A-Za-z])CSS(?![A-Za-z])|스타일링
slots: []
links:
- screen-ownership-before-wiring
- ask-with-arrow-key-options
- do-the-whole-instruction
- run-inside-this-session
severity: contract
sources: []
---

# 화면은 목적을 따르고, 손질은 순서를 따른다

규칙. 먼저 사용자가 화면에서 하려는 일을 한 문장으로 정한다. 그 목적에 맞춰 화면 구성, 버튼 동작, 글자 크기, 색, 여백 순서로 확인한다. 값이 없는 장식으로 공간을 채우지 않는다. 선택이 필요한 디자인은 사용자에게 구체적인 대안을 보여 준다.
