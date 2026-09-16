---
name: design-pass
description: >-
  Design or rework a frontend screen in a fixed order — purpose and layout first,
  then measure padding/width/alignment and button wiring in a real browser, then
  typography hierarchy, then propose a color palette to the user, then fill the
  leftover whitespace. Use when asked to design, build, lay out or polish a UI,
  dashboard, landing page or detail page, or when the user says "디자인",
  "프런트엔드", "레이아웃", "타이포", "색 배합", "UI 다듬어". For motion and
  animation work use emil's `animate` / `review-animations` instead.
---

# 디자인 한 바퀴 — 다섯 걸음

이 스킬이 드는 규칙은 `craft/screen-follows-the-purpose` 다. 왜 이 순서인지는
그 페이지에 있고, 여기는 어떻게 하는지만 적는다.

다섯을 다 한다. 순서를 바꾸지 않는다. 4번에서 한 번 사용자에게 넘긴다.

## 0. 무엇을 만드는지부터 한 줄

파일을 열기 전에 적는다.

```
누가:        <이 화면에 오는 사람>
무엇을 하러: <한 가지>
성공:        <무엇이 보이면 끝난 것인가>
```

이 세 줄이 화면 목록을 고르게 한다. 세 줄을 못 적으면 사용자에게 묻는다.
상세 페이지와 대시보드는 **답이 아니라 기본값**이다. 기본값으로 짓지 마라.

## 1. `DESIGN.md` 와 스케치

`DESIGN.md` 가 프로젝트 루트에 있으면 읽고, 없으면 만든다.

- 골라 오기 — <https://getdesign.md/> 에서 목적에 가까운 것을 고른다
- 형식 — <https://github.com/google-labs-code/design.md> 의 스펙
- front matter 에 토큰(`colors` `typography` `spacing` `rounded` `components`),
  본문에 그렇게 고른 이유

값이 아직 없으면 비워 두고 4번에서 채운다. **비어 있는 것과 안 정한 것은 다르다** —
비었으면 그 자리가 4번의 할 일이 된다.

스케치는 `better-layout` 을 부른다. 묶기·정렬·읽는 순서·점진적 공개까지가
그 스킬의 몫이다. 시안을 여럿 놓고 고를 거면 `prototype` 이나 `variant`.

## 2. 브라우저로 **잰다** — 눈으로 보지 않는다

띄우는 것은 이 셀 안에서 한다(`operator/run-inside-this-session`).
`claude-in-chrome` 으로 새 탭을 열고, 두 가지를 값으로 뽑는다.

### 2-1. 같은 역할이 같은 값을 쓰는가

`javascript_tool` 로 돌리고 `read_console_messages` 로 읽는다. **어긋나는 것만**
찍으므로, 출력이 `{}` 면 통과다.

```js
const seen = {};
for (const el of document.querySelectorAll('main *, [class*="card"], button')) {
  const s = getComputedStyle(el);
  const key = el.tagName + '.' + (el.className.baseVal ?? el.className).split(' ')[0];
  (seen[key] ??= new Set()).add(
    `pad=${s.padding} gap=${s.gap} w=${Math.round(el.getBoundingClientRect().width)}`
  );
}
console.log('[design-pass]', JSON.stringify(Object.fromEntries(
  Object.entries(seen).filter(([, v]) => v.size > 1).map(([k, v]) => [k, [...v]])
), null, 1));
```

폭은 두 번 잰다 — 넓은 창과 `resize_window` 로 400px. 가로 스크롤이 생기면
그 자체가 발견이다.

### 2-2. 버튼이 실제로 불리는가

눈에 보이는 버튼을 하나씩 누르고 콘솔·네트워크로 확인한다. 핸들러가 안 붙은
버튼은 **모양이 멀쩡해서 안 보인다** — 그게 이 걸음이 있는 이유다.

확인창(`alert`·`confirm`)을 띄우는 버튼은 누르지 마라. 세션이 멈춘다. 삭제처럼
확인창이 붙을 만한 것은 핸들러가 걸려 있는지만 코드에서 본다.

발견은 고치고 **2번을 다시 돈다.** 고친 뒤에 안 재면 안 고쳐진 것과 구별이 없다.

## 3. 타이포그래피 위계

`better-typography` 를 부른다. 통과 기준은 둘이다.

- 단계가 **세어진다** — 화면에 쓰인 크기·굵기 조합이 몇 개인지 답할 수 있다
- 쓰임이 안 겹친다 — 같은 단계가 두 가지 뜻으로 쓰이지 않는다

`DESIGN.md` 의 `typography` 와 대조한다. 대조할 것이 없으면 여기서 만들어 적는다.

## 4. 색 — 만들고, 고르는 것은 사용자다

`better-colors` 로 프로젝트에 맞는 후보를 **2~3개** 만든다. 각각 대비를 검사해
통과한 것만 남긴다.

그다음 `AskUserQuestion` 으로 넘긴다(`operator/ask-with-arrow-key-options`).
선택지에 색 이름을 적지 말고 **결과**를 적는다 — 무엇이 강조되고 무엇이
물러나는가, 어떤 인상이 되는가.

고른 것을 `DESIGN.md` 의 `colors` 에 적는다. 여기까지 해야 다음 세션이 같은
파랑을 쓴다.

## 5. 남은 여백

마지막에 한 번 훑는다. 허전한 자리가 있으면 채울 **값**이 있는지 먼저 본다.

| 자리 | 채울 것 |
| --- | --- |
| 숫자가 있다 | 차트 · 스파크라인 · 스탯 타일 → `dataviz` 스킬이 규칙을 든다 |
| 설명이 필요하다 | 큰 타이포 · 인용 · 섹션 도입부 |
| 관계를 보여야 한다 | 다이어그램 |
| 채울 값이 없다 | **안 채운다.** 여백을 메우려고 만든 숫자는 인포그래픽이 아니다 |

## 끝나는 조건

다섯 걸음을 다 돌고, 2번의 출력이 비어 있고, 4번을 사용자가 골랐으면 끝이다.
`DESIGN.md` 에 이번에 정한 값이 들어갔는지 마지막으로 확인한다.

## 이 스킬이 안 하는 것

- **모션.** 움직임은 emil 쪽이다 — 새로 만들면 `animate`, 있는 것을 보면
  `review-animations`, 넣을 자리를 찾으면 `find-animation-opportunities`.
- **배선.** 화면이 서버에 쓰기 시작하면 계정 경계와 비동기 소유권을 먼저 정한다
  (`craft/screen-ownership-before-wiring`). 이 스킬은 그 앞까지다.
