# 색인

에이전트가 이 파일을 먼저 읽고 어느 페이지가 필요한지 정한다. 임베딩도 벡터
DB 도 없다. `landmine` 과 `contract` 는 그마저도 안 기다린다 — `UserPromptSubmit`
훅이 발화를 보고 직접 넣는다([`ENFORCEMENT.md`](ENFORCEMENT.md)).

규약은 [`SCHEMA.md`](SCHEMA.md), 검진과 갱신은 [`MAINTENANCE.md`](MAINTENANCE.md).
페이지를 쓰거나 고치기 전에 읽는다.

```
python tool/census.py --project <경로> --out raw/census-<이름>.jsonl
python tool/intersect.py raw/census-*.jsonl
```

## operator — 사람을 따라다닌다

| 페이지 | 등급 |
| --- | --- |
| [Codex 리뷰 루프](operator/codex-review-loop.md) | `landmine` |
| [화면에 뜨는 말은 한국어로](operator/korean-progress.md) | `landmine` |
| [파일은 diff 로 고친다](operator/edit-files-as-diffs.md) | `contract` |
| [머지 후 정리](operator/after-merge-cleanup.md) | `contract` |
| [질문은 선택지로](operator/ask-with-arrow-key-options.md) | `contract` |
| [서브에이전트를 임의로 늘리지 않는다](operator/agent-delegation.md) | `contract` |

## craft — 기술을 따라다닌다

| 페이지 | 등급 |
| --- | --- |
| [비동기 결과는 곧바로 받는다](craft/pick-up-async-results.md) | `landmine` |
| [강조는 희소해야 강조다](craft/emphasis-is-scarce.md) | `landmine` |
| [시킨 것을 끝까지 한다](craft/do-the-whole-instruction.md) | `contract` |
| [되돌릴 수 없는 git 은 차단한다](craft/destructive-git-guards.md) | `contract` |
| [훅은 세션을 멈추지 않는다](craft/hooks-fail-open.md) | `landmine` |
| [주석은 이유를 들고 이력은 안 든다](craft/comments-carry-why.md) | `contract` |
| [오류 이름은 증상이 난 자리를 가리킨다](craft/error-names-the-symptom-site.md) | `landmine` |
| [화면은 목적을 따르고 손질은 순서를 따른다](craft/screen-follows-the-purpose.md) | `contract` |

census 는 작동하는 규칙을 못
본다 — 자세한 것은 `SCHEMA.md` 의 "페이지가 되는 문은 둘이다".

## skills — 반복 지시를 굳힌 절차

| 스킬 | 무엇 |
| --- | --- |
| [`review-loop`](skills/review-loop/SKILL.md) | 라운드 한 번. 감시를 걸고 보내는 것이 한 절차 |
| [`after-merge`](skills/after-merge/SKILL.md) | 머지 후 정리 일곱 걸음 + 검진 |
| [`retrospect`](skills/retrospect/SKILL.md) | 오늘 어긋난 자리를 세어 위키 갱신 후보로 |
| [`design-pass`](skills/design-pass/SKILL.md) | 디자인 다섯 걸음. 순서를 못 바꾸게 |

### 밖에서 들여온 스킬 — 고르는 것은 위키가 한다

`design-pass` 는 남의 스킬 둘을 부른다. 무엇을 언제 부르는지는 스킬이 아니라
페이지가 정한다 — 그래야 훅이 먼저 읽힌다.

```
npx skills add jakubkrehel/skills -g -s '*' -y   # 정지한 화면
npx skills add emilkowalski/skill  -g -s '*' -y  # 움직이는 것
```

경계와 표는 [화면은 목적을 따른다](craft/screen-follows-the-purpose.md) 에 있다.

## 지도

`web/` 의 위키 지도 이 이 색인을 그림으로 보여 준다. 노드 크기는 주입 비용, 색은 강제
층, 점선은 실제 발화에서 함께 실린 횟수다.

```
python tool/graph.py
```
