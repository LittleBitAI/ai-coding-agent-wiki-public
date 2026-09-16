---
scope: operator
severity: contract
triggers: ["edit\\s*(만|diff)", "diff\\s*(로|형태|방식)", "ran\\s*(형식|으로)\\s*(수정|하지|작성)", "스크립트로\\s*(수정|고쳐|바꾸)", "sed\\s+-i", "here-?string"]
slots: []
enforce:
  deny:
    - "Bash(sed -i*)"
    - "Bash(perl -pi*)"
    - "Bash(perl -i*)"
    - "Bash(perl -0pi*)"
    - "Bash(dos2unix*)"
    - "Bash(unix2dos*)"
  pretooluse: edit_as_diff.py
sources: []
sources_withheld: true
links: [destructive-git-guards]
---

# 파일은 diff 로 고친다 — 스크립트로 다시 쓰지 마라

규칙. 기존 파일은 바꿀 텍스트와 바꿀 내용을 짝지어 고친다.
전체를 통째로 쓰는 것은 새 파일일 때만이다.
셸 리다이렉션·here-string·`sed -i`·파일을 읽어 치환하고 되쓰는
한 줄짜리 스크립트는 쓰지 않는다.

스크립트로 되쓰면 세 가지가 한꺼번에 나빠진다. 한 줄을 고치려고 파일
전체를 다시 쓰고, 무엇이 바뀌었는지가 diff 에 안 남고, 인코딩과 줄끝이 조용히
바뀐다.

어겼을 때. 바뀐 자리를 아무도 못 읽는다. diff 는 대상 텍스트가 안 맞으면
소리 내며 실패하지만, 스크립트는 아무것도 안 바꾸고도 조용히 성공한다.

## 강제 — 이 페이지는 1층과 4층을 다 쓴다

`sed -i` 계열은 명령 모양으로 보이므로 `permissions.deny` 가 막는다. `apply`
가 이 페이지의 `enforce.deny` 를 대상 저장소의 `.claude/settings.json` 에
합친다.

`Bash(perl -i*)` 는 `perl -0pi` 를 안 맞는다. 앞이 `-0pi` 라서다.

그러니 이 자리의 deny 는 실측한 모양만
literal 로 적는다. `perl -0777pi` 처럼 안 세어진 조합은 여전히 빠져나간다 —
그것이 나오면 그때 한 줄을 더한다.

`tool/edit_as_diff.py` 가 4층이다. **이미 있는 파일** 하나만 본다.

- `Bash`: `cat >`·`cat >>`·`tee`·리다이렉션·`Path(...).write_*`·`open(..., "w")`
  가 가리키는 경로 중 지금 실제로 있는 파일
- `Write`: 대상 경로가 이미 있으면 — 통째로 쓰는 것은 새 파일일 때만이므로

통과시키는 것이 절반이다. 새 파일, 저장소 밖 스크래치, `/dev/null`, `2>&1`,
`Edit` 자체. **오탐이 작업을 멈추면 사용자가 훅을 통째로 끄고 강제는 0이 된다.**
`tool/test_edit_as_diff.py` 가 막는 자리 여덟과 안 막는 자리 아홉을 다 든다.

명령 모양이 무한하다는 것은 여전히 맞다. 못 잡는 나머지는 아래 산문이 든다.

가르는 것은 본문이 무엇이 되느냐다. `python - <<'PY'` 의 본문은 실행되는 코드라
봐야 하고, `git commit -F - <<'MSG'` 의 본문은 데이터라 안 봐야 한다. 그래서
`strip_data_heredocs` 가 수신자를 보고 인터프리터가 아니면 본문을 스캔에서 뺀다.
명령줄 자체의 리다이렉션은 본문 밖이므로 `cat > file <<'PY'` 는 계속 잡힌다.

## 새 파일은 예외다

없던 파일을 만드는 것은 통째로 쓴다. 지울 것이 없으므로 diff 가 될 수 없다.

되돌릴 수 없는 쪽을 막는 규칙은 [[destructive-git-guards]] 에 있다. 둘이 같은
자리를 지킨다 — 무엇이 바뀌었는지 아무도 못 읽게 되는 것을 막는다.
