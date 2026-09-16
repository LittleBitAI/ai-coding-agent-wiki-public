---
name: after-merge
description: >-
  Clean up after a pull request is merged — return to the default branch, pull,
  delete the merged local and remote branches, stop any servers this session
  started, clear scratch directories, and run the wiki lint. Use when the user
  says "머지했다", "merge 완료", "브랜치 정리", or otherwise reports that a PR landed.
---

# 머지 후 정리

이 스킬이 드는 규칙은 `operator/after-merge-cleanup` 이다. 왜 그렇게 하는지는
그 페이지에 있고, 여기는 어떻게 하는지만 적는다.

전부 한다. 하나씩 시킬 때까지 기다리지 않는다.

## 걸음

### 1. 머지를 확인한다

```bash
git fetch origin --prune
gh pr view <N> --json state,mergedAt,mergeCommit
```

머지가 안 됐으면 멈추고 말한다. 안 된 것을 정리하면 작업을 잃는다.

### 2. 기본 브랜치로 복귀한다

```bash
git checkout main && git pull --ff-only
```

`--ff-only` 다. 병합 커밋을 조용히 만들지 않는다. 미커밋 변경이나 독립 리뷰 세션이
있는 작업 폴더는 전환하지 않는다. 머지 요청에는 정리까지 포함되며 재승인을 기다리지 않는다.

### 3. 로컬 브랜치를 지운다 — 지우기 전에 확인한다

`git branch -d` 는 squash 머지된 브랜치를 거절한다. tip 이 `main` 의 조상이
아니기 때문이다. `-D` 로 밀기 전에 내용이 실제로 들어갔는지 본다.

```bash
git rev-parse <branch>^{tree}    # 이 둘이
git rev-parse <해당-PR-머지-커밋>^{tree}
git diff --stat <branch> <해당-PR-머지-커밋>
```

같으면 `-D`. 다르면 충돌 해결이나 후속 커밋을 검토하고 bundle로 보존한 뒤 판단한다.
최신 main과 다르다는 사실만으로 미머지라고 단정하지 않는다. 작업 트리에 연결된 브랜치는
아래 자산 보존을 먼저 마친 뒤 작업 트리를 제거하고 지운다. Orca 작업 트리는 Orca로 제거한다.

### 4. 원격 브랜치

대개 머지가 이미 지웠다. `git fetch --prune` 뒤에 `git branch -r` 로 확인하고,
남아 있으면 지운다.

### 5. 서버를 끈다

이 세션이 띄운 것을 전부 끈다. 포트로 확인한다 — 프로세스 목록보다 확실하다.

### 6. 스크래치를 치운다

삭제 대상의 절대경로와 링크 대상을 먼저 확인한다. 음성 자산·런타임 데이터·라이브 및
리뷰 근거와 공유 의존성은 필요하면 작업 트리 밖으로 보존한다. junction은 링크만
제거하며 대상을 지우지 않는다. 사용자가 열어 둔 독립 리뷰 세션은 유지한다.

### 7. 위키를 검진한다

```bash
python tool/lint.py --repo <이 저장소>       # 허브 위키의 구조
python tool/repo_lint.py --repo <이 저장소>  # 이 저장소의 지식
```

발견을 어떻게
처리하는지는 위키의 `MAINTENANCE.md` 에 있다.

발견이 나와도 정리는 멈추지 않는다. 8번까지 하고 같이 보고한다.

### 8. 상태를 보고한다

브랜치 목록·서버 상태·워크트리 청결을 확인한 값으로 보고한다. "정리했다" 가
아니라 무엇이 남았는지를 적는다. lint 발견이 있으면 같이 적는다.

## 막히면

한 걸음이 막혀도 나머지를 다 하고, 막힌 것을 이름과 이유로 말한다.
범위를 조용히 줄이지 않는다.
