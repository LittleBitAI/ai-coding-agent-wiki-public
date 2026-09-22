---
scope: operator
severity: landmine
triggers: ["리뷰\\s*루프", "review\\s*loop", "codex.{0,12}(리뷰|보내|돌려)", "라운드\\s*\\d+\\s*(를|을)?\\s*(보내|전송)"]
slots: [review_dir, gate_cmd, live_cmd]
sources: []
sources_withheld: true
links: [pick-up-async-results, ask-with-arrow-key-options, agent-delegation]
---

# The Codex review loop — files carry it, the terminal is a doorbell

The reviewer is the session already assigned. A request for an independent
review does not widen into spawning another implementation agent. What may be
created is held by [[agent-delegation]].

Rule. Reviews pass through files. The instruction goes in
`{review_dir}/<topic>-round-<n>.md`, and the terminal receives one sentence:
`'read that file and review it'`. The reviewer writes the result to
`<topic>-round-<n>-result.md`. Do not scrape the result off the terminal.

What goes wrong. The round disappears quietly. Worse is
**a review that looks like it happened and did not** — a session that never
read the instruction asks "which file?", or reviews whatever it had open and
hands that back.

## What the instruction must contain

- The result file's path, in the first section. "Write to this file, say
  nothing on the terminal, and if that file is not written this round did not
  happen."
- Worktree protection as an *allow* list. Written as prohibitions first, a
  prohibition swallows the exception and the review ends up on screen only.
  - Allowed: reading · `git log`/`show`/`diff` · `gh pr view`/`diff` ·
    running tests · writing that one result file
  - Forbidden: `checkout`, `switch`, `stash`, `merge`, `rebase`, `reset`,
    `cherry-pick`, `commit`, `push` · installing packages · every edit other
    than that result file
- What changed since the last round. The commit range and the size confirmed
  with `git diff --shortstat`.
- What has already been run. Do not make them derive it again.
- What became of each earlier finding, including what was rejected and why.
- The report format and the grades.

  ```
  [P0|P1|P2] file:line — what / when / why
  ```

  | Grade | Criterion |
  | --- | --- |
  | P0 | Data corruption or loss, security, crash, contract violation |
  | P1 | A correctness defect, a regression, wrong behaviour this PR introduced |
  | P2 | A suggestion, style, a follow-up candidate |

- An instruction not to invent findings without grounds. With nothing wrong,
  one line: `새 발견 없음`.
- A last line of `머지 허용` or `머지 불가 — <reason>`.

## What the receiving side holds

- Arm the watch *before* sending. And do not end the turn between the send and
  the watch → [[pick-up-async-results]]
- Watch the directory, not one path. If the reviewer writes under a
  neighbouring name, polling one path never finishes. A session that answered
  an earlier round sometimes reuses the previous path — and then the new
  result overwrites the old one.
- Check that the result file's first line names that round.
- Do not take a finding as fact. Reproduce before fixing. Fix where the
  finding points, and count separately the places that rule applies to.
- P2 is not fixed by default. Record it under `Deferred P2` at the bottom of
  the round file, and instruct that a P2 already recorded is not reported
  again next round without new grounds or a severity change.
- A finding that is not agreed with goes back as a question, with grounds.

## Every round

1. Run the offline gate: `{gate_cmd}`
2. If there is a live run, run it and carry the result in the instruction:
   `{live_cmd}`
3. Commit and push. Twenty rounds piled up locally leave the PR looking
   exactly as it did before the review started, and from outside that is
   indistinguishable from abandoned work.

## When the rounds stop shrinking — sort by family first

A similar number of findings each round is not a relentless reviewer; it is a
signal that the repairs are not reaching the cause. Before sending the next
round, pair up the findings so far into a table. One row is
`finding → the repair made → what came back next round`.

A raw list does not show it. The families only appear once they are paired.

| Family | How to recognise it | What to do |
| --- | --- | --- |
| The wrong model | Findings cluster in one file and every one is "it does not look at this input either" | Re-decide what that code models — [[gate-the-exit-not-the-callers]] |
| Where it measures | Two findings arrive about the same value (time, length, cost) | Follow the value's life and find where it changes last — [[measure-after-the-last-change]] |
| The claim is wrong | The code is right and the commit message, comment or test is written too broadly | Fix the sentence and the test, not the code |
| Knew and skipped | Something written under "what I suspect" in the instruction comes back as a finding | Having written the suspicion, reproduce it in that round |

The first two are what stops convergence. The other two close in one go.

In one real PR, eleven findings had four causes. Five were faces of one model,
three were where it measured, and the last two were the other two families.
Only two were genuinely new defects the repairs had created — the rest were
patches on symptom sites.

"Fix where the finding points", above, is a rule about scope, not about depth.
Not fixing broadly and fixing shallowly are different things, and applying
that sentence to depth is what turned that PR into three more rounds.

## When it ends

It ends when P0 and serious P1 have no new findings and every test passes. It
can end with P2 outstanding. Once it does, go through `Deferred P2` once and
leave only what is worth doing, as a single PR comment. Minor style and taste
are discarded.
