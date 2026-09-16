---
scope: craft
severity: contract
triggers: ["reset\\s+--hard", "git\\s+clean", "checkout\\s+--", "git\\s+restore", "되돌려|되돌리", "작업.{0,4}(날아|잃|사라)"]
slots: []
enforce:
  deny: ["Bash(git reset --hard*)", "Bash(git clean -fdx*)"]
sources: []
sources_withheld: true
conflicts_with: []
links: [edit-files-as-diffs]
---

# 되돌릴 수 없는 git 은 차단한다

규칙. `git reset --hard` 와 `git clean -fdx` 는 막는다. 되돌려야 하면 커밋을
만들고 그 위에서 되돌린다. 필요하면 사용자가 직접 친다.

왜. 이 둘은 커밋 안 된 작업을 확인 없이 지운다. 나머지 파괴적 git 명령과
다른 점은 되돌릴 방법이 아예 없다는 것이다 — reflog 도 워킹 트리는 못 살린다.

## `git checkout -- <path>` 도 같은 부류다 — 그런데 차단 목록에 없다

`git restore <path>` 도 같다. 셋 다 커밋 안 된 워킹 트리를 확인 없이 지우고
reflog 로 못 살린다.

## 차단이 아니라 전제로 막는다

`checkout -- <path>` 를 `deny` 에 넣지 않는다. 넣으면 그것을 정당하게 쓰는 것이
같이 막힌다 — 되돌리기 루프 자신이 그 명령으로 되돌린다.

대신 전제를 건다.

> **되돌리는 루프는 커밋된 트리에서만 돈다.** 시작할 때 `git status --porcelain`
> 로 대상 경로가 깨끗한지 확인하고, 안 깨끗하면 시작하지 않는다.

그러면 되돌리기가 복원할 수 있는 것은 방금 커밋한 것뿐이므로 잃을 것이 없다.
이 전제는 이 페이지의 첫 문장 — *"되돌려야 하면 커밋을 만들고 그 위에서
되돌린다"* — 을 루프에 적용한 것이고, 새 규칙이 아니다. 빠져 있던 것은 그
문장이 어느 명령까지 덮는지였다.

이것이 자주 걸리는 자리는 정해져 있다. 구현 단위마다 뮤테이션 검사를 요구하는
저장소에서는 매 단위 끝에 이 루프가 돈다.

그래서 위키에 들어오는 문이 반복 말고 하나 더 있다. 한 곳에서라도 이미
검사나 차단으로 서 있고 프로젝트를 옮겨도 말이 되면 들어온다.
`ENFORCEMENT.md` 의 "census 는 작동하는 규칙을 못 본다" 를 보라.

## `git stash` 는 여기 없다

프로젝트를 따라다니는 것이므로 그 저장소의 문서에 두고
여기 들이지 않는다.
