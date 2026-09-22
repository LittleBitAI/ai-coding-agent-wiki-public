---
name: retrospect
description: >-
  Reflect on the session's work and turn what went wrong into wiki changes.
  Reads the day's commits and the session transcript, counts corrections and
  redos with evidence, and proposes page edits. Use when the user says "회고",
  "오늘 뭐 했", "돌아보자", "retrospective", "정리해줘" about a day's work, or at
  the end of a working session.
---

# Retrospective — what went wrong today, and what it becomes in the wiki

This skill exists because census cannot do this. Census says nothing until
dozens of sessions have piled up. Something that went wrong today has to be
caught today, or it repeats until the next census.

What a retrospective produces is candidates for the wiki, not impressions. Not
what you felt, but what has to become a page.

## Steps

### 1. What happened today — read it, do not invent it

```bash
git log --oneline --since=midnight
git diff --shortstat <first commit today>^..HEAD
```

Do not write from memory. The early part of a long session is already folded
into a summary, and a summary keeps what was done while erasing what went wrong.

### 2. Count where it went wrong — four kinds

| Kind | How to find it |
| --- | --- |
| Correction | Where the user said "아니", "틀렸다", "다시" |
| Re-entry | Where a rule already stated had to be typed again |
| Partial work | Where part of the instruction was done and the rest re-ordered |
| Reversal | Where a hypothesis was disproved and had to be undone |

Session records are at `~/.claude/projects/<flattened path>/<session>.jsonl`.
A block with `type=user` that is not a tool result is what a person typed.

Give the counts. "I think that happened a few times" is not a retrospective. It
has to be in a shape that can go into `raw/`.

### 3. Check whether each one is already a page

```bash
python tool/lint.py --repo <repo>
```

| Already a page | What it means | What to do |
| --- | --- | --- |
| Yes | That page is not working | Climb the ladder, do not rewrite the prose |
| No | A new candidate | Apply the thresholds below |

The first row matters most here. If it is written down and was broken anyway,
the problem is not that the sentence is weak. It is that it is a sentence.

### 4. Apply the thresholds — not everything becomes a page

| Where | When |
| --- | --- |
| That repo's `CLAUDE.md` | It only happens in one repository. Most things. |
| A wiki page | It happened in two or more, or it already stands as a check or a block and can be moved |
| Nowhere | It happened once and the cause is unknown. Wait until it happens again. |

Adding a page costs something by itself. It raises how much gets injected, and
that is the problem this wiki was built to solve in the first place.

### 5. Ask with options

What becomes a page is the user's judgement. Ask with arrow-key options, not
prose. Put the consequence in each option rather than a label: how many
characters this rule adds to the injection, and which utterances it catches.

### 6. Check after changing anything

```bash
python tool/lint.py --repo <repo>
python tool/trigger_audit.py raw/census-*.jsonl
```

Run the audit after writing a new trigger. One loose trigger loads its rule on
every turn, and then nothing gets read at all.

## What this does not do

- Does not list what went well. A retrospective's value is in what went wrong.
- Does not make one page per incident. Apply the step 4 thresholds first.
- Does not write "that happened a lot" without a count. Lint catches a
  `landmine` with no evidence.
