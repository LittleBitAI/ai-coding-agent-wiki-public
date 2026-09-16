---
name: review-loop
description: >-
  Run one round of the external code-review loop against an already-open reviewer
  terminal. Use when the user says "리뷰 루프", "review loop", "라운드 N 보내",
  "codex 리뷰", or asks to send/receive a review round. Writes the round
  instruction to a file, arms the result watch BEFORE sending, sends one sentence
  to the terminal, and reads the result from the file — never from the terminal.
---

# 리뷰 루프 한 라운드

이 스킬의 존재 이유는 순서다. 감시를 거는 걸음과 보내는 걸음이 따로 있으면
순서를 틀린다. 여기서는 두 걸음이 한 절차이므로 틀릴 자리가 없다.

## 걸음

### 1. 라운드 번호와 주제를 정한다

```
artifacts/review/<topic>-round-<n>.md
```

`artifacts/review/` 를 훑어 `-result.md` 가 아직 없는 가장 최근 지시문의 다음
번호를 쓴다. 이전 라운드의 경로를 재사용하지 마라 — 새 결과가 옛 결과를 덮는다.

### 2. 지시문을 쓴다

첫 절이 결과 파일 경로다. 그다음이 워크트리 보호이고, 허용 목록을 먼저
쓴다 — 금지를 먼저 쓰면 그 금지가 예외를 삼켜 리뷰가 화면에만 남는다.

들어가야 할 것은 `operator/codex-review-loop` 페이지에 전부 있다. 그 페이지가
이 스킬과 함께 주입되므로 다시 적지 않는다.

보내기 전에 확인한다.

- `git diff --shortstat` 로 크기를 실제로 재서 적었나
- 지난 라운드의 지적이 각각 무엇이 됐는지 적었나 (거부한 것과 이유까지)
- 이미 돌린 것을 적어 다시 도출하지 않게 했나

### 3. 감시를 먼저 건다 — 이 걸음을 4번 뒤로 옮기지 마라

```
Monitor: artifacts/review/ 안에서 전송 시각보다 새로운 *-result.md
```

- 경로 하나가 아니라 디렉터리를 본다. 리뷰어가 옆 이름으로 쓰면 한 경로
  폴링은 영원히 안 끝난다.
- 폴링은 1초. 로컬 파일이다.
- 감시를 걸고 턴을 끝내지 마라. 다음 걸음까지 같은 응답에서 한다.

### 4. 한 문장만 보낸다

```
orca terminal send --terminal <handle> --text '그 파일을 읽고 리뷰하라' --enter
```

핸들은 보낼 때마다 다시 조회한다 — 리뷰어가 재시작하면 낡는다.
새 창을 절대 열지 마라.

### 5. 결과가 오면 읽는다

파일에서 읽는다. 터미널을 긁지 마라. 첫 줄이 그 라운드를 지목하는지 확인한다 —
아니면 그 세션이 지시문을 안 읽고 자기가 보던 것을 리뷰한 것이다.

### 6. 지적을 사실로 전제하지 말고 재현한다

- P0·심각한 P1: 재현부터. 재현되면 고치고, 안 되면 안 된다고 적는다
- 고칠 때 셋을 확인한다
  1. 판단을 하나씩 지워 어느 테스트가 빨개지는지
  2. 응답 도착 전에 재는 가짜 초록이 아닌지
  3. 그 규칙을 따라야 할 자리를 전부 셌는지
- 지적이 짚은 자리만 고친다. 넓게 고치면 다른 것이 깨진다
- 동의 못 하면 근거를 적어 되묻는다
- P2 는 안 고친다. 라운드 파일 하단 `Deferred P2` 에 적는다

수리 방향이 여럿이면 사용자에게 넘긴다. 그때는 산문으로 묻지 말고 방향키
선택지로 낸다 — `operator/ask-with-arrow-key-options`. 각 선택지에 라벨이
아니라 결과를 적는다: 무엇을 치르고 무엇이 안 되는가.

### 7. 게이트 → 라이브 → 커밋 → 푸시

푸시는 안 물어보고 한다. 로컬에만 쌓으면 PR 은 리뷰 시작 전 상태로 남고,
밖에서 보면 버려진 작업과 구별되지 않는다.

### 8. 다음 라운드

바뀐 것·mutation 결과·새 `Deferred P2`·기존 P2 의 승격 여부를 다음 지시문에 적고
1번으로 돌아간다.

## 끝내는 조건

P0 와 심각한 P1 에 새 발견이 없고 테스트가 전부 통과하면 끝낸다.
P2 가 남아 있어도 끝낼 수 있다.

끝나면 `Deferred P2` 를 한 번 정리해 실행 가치가 있는 것만 PR 코멘트 하나로
남긴다. 사소한 스타일·취향은 폐기한다. `artifacts/` 는 임시 작업 공간이므로
영구 기록이 아니다.
