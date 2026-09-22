---
name: review-loop
description: >-
  Run one round of the external code-review loop against an already-open reviewer
  terminal. Use when the user says "리뷰 루프", "review loop", "라운드 N 보내",
  "codex 리뷰", or asks to send/receive a review round. Writes the round
  instruction to a file, arms the result watch BEFORE sending, sends one sentence
  to the terminal, and reads the result from the file — never from the terminal.
---

# One round of the review loop

This skill exists for the ordering. When arming the watch and sending are two
separate steps, the order gets it wrong. Here they are one procedure, so there
is nowhere to get it wrong.

## Steps

### 1. Pick the round number and topic

```
artifacts/review/<topic>-round-<n>.md
```

Scan `artifacts/review/` and take the number after the most recent instruction
that has no `-result.md` yet. Do not reuse a previous round's path — a new
result would overwrite the old one.

### 2. Write the instruction

The first clause is the result file path. Next is worktree protection, and the
allow list goes first: put the prohibitions first and they swallow the
exceptions, leaving the review on screen and nowhere else.

Everything that has to be in it is on the `operator/codex-review-loop` page.
That page is injected alongside this skill, so it is not repeated here.

Check before sending.

- Did you measure the size with `git diff --shortstat` and write the real number
- Did you write what became of each finding from the last round, refusals and
  reasons included
- Did you write what has already been run, so it is not derived again

### 3. Arm the watch first — never move this step after step 4

```
Monitor: a *-result.md under artifacts/review/ newer than the send
```

- Watch the directory, not one path. If the reviewer writes under a neighbouring
  name, polling a single path never finishes.
- Poll at one second. These are local files.
- Do not end the turn after arming it. Do the next step in the same response.

### 4. Send one sentence

```
orca terminal send --terminal <handle> --text '그 파일을 읽고 리뷰하라' --enter
```

Look the handle up again on every send — it goes stale when the reviewer
restarts. Never open a new window.

### 5. Read the result when it lands

Read it from the file. Do not scrape the terminal. Check that the first line
names that round; if it does not, that session reviewed whatever it had been
looking at instead of reading the instruction.

### 6. Reproduce a finding before treating it as fact

- P0 and serious P1: reproduce first. Fix what reproduces, and write down what
  does not.
- When fixing, check three things:
  1. Remove each judgement one at a time and see which test goes red
  2. Whether this is a false green measured before the response arrived
  3. Whether you counted every place that rule has to apply
- Fix only where the finding points. Fixing broadly breaks something else.
- If you disagree, write the evidence and ask back.
- Do not fix P2. Record it under `Deferred P2` at the bottom of the round file.

When there are several ways to repair it, hand the choice to the user — with
arrow-key options, not prose (`operator/ask-with-arrow-key-options`). Put the
consequence in each option, not a label: what it costs and what it rules out.

### 7. Gate, then live, then commit, then push

Push without asking. Left local, the PR stays as it was before the review began,
and from outside that is indistinguishable from abandoned work.

### 8. Next round

Write what changed, the mutation results, new `Deferred P2` entries, and whether
any existing P2 was promoted, into the next instruction. Then go back to step 1.

## When to stop

Stop when there are no new findings at P0 or serious P1 and every test passes.
Leftover P2 entries do not prevent stopping.

When it ends, go through `Deferred P2` once and leave only what is worth doing,
as a single PR comment. Discard minor style and taste. `artifacts/` is scratch
space, not a permanent record.
