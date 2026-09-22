# Enforcement — the five layers that make what is written govern behaviour

`SCHEMA.md` says "turn the rules that can be into checks". This document is
the how.

That rule is now layer 4 — `operator/edit-files-as-diffs`,
`tool/edit_as_diff.py`.

## The ladder — cheapest first, stop at the first rung that holds

| Layer | What | When | Cost |
| --- | --- | --- | --- |
| 1 | `permissions.deny` | The violation looks like a command | One line of `enforce.deny` on a page |
| 2 | `UserPromptSubmit` hook → `additionalContext` | Inject the page that fits this utterance | A few lines of regex |
| 3 | A skill | Set a repeated instruction into a procedure so the order cannot go wrong | One file |
| 4 | `PreToolUse` hook | The violation is only visible once computed | A script, and the risk of false positives |
| 5 | Prose | It needs judgement | It might not be followed |

There is one more beside layer 2. The `SessionStart` hook injects state rather
than a response to an utterance — the branch, the unfinished rows of open
plans, recent decisions. Two of the things that get forgotten catch on no
utterance at all: the user does not write down "what was I in the middle of",
and "why was it chosen that way" attaches to no particular word. What cannot
be caught by a trigger is not chased with one.

Stop at the first rung. Do not use layer 4 because layer 4 could block it — a
false positive that stops the work is not enforcement, it is obstruction.

## Layer 2 is the heart of this wiki

The `UserPromptSubmit` hook reads the user's utterance and puts the matching
page into the context.

```
User: "PR #91 리뷰 루프 돌려라"
   ↓  the UserPromptSubmit hook sees "리뷰 루프"
   ↓  hookSpecificOutput.additionalContext injects operator/codex-review-loop.md
Agent: starts with that page already read
```

This is what was wanted in the first place — the right thing gets read without
anyone saying "read X". It works differently from the original idea
(Karpathy's).

| | The original | Here |
| --- | --- | --- |
| Who chooses | The agent reads `index.md` and chooses | The hook reads the utterance and injects |
| If it is not read | It is not read | It cannot not be read |

So every page declares its `triggers`.

```yaml
---
scope: operator
severity: landmine
triggers: ["리뷰 루프", "review loop", "codex.*리뷰"]
---
```

Only `landmine` and `contract` are injected. `preference` stays in `index.md`
for the agent to read when it needs it. Otherwise the problem that created
this wiki — everything loaded into the context and therefore nothing read —
comes straight back.

The unit is the same as `trajectory.cost`: headers, source tables and the
separators between blocks are not counted. `rule` covers the shared rules and
a project's `.wiki/*.md` rules; `repo` covers decision blocks. The document
list, plans and recent decisions that `SessionStart` carries are in neither
number. The maxima of the two axes can fall on different turns, so adding them
and calling the result a per-turn maximum is wrong.

Run without `--project` and the auditor does not read the project pages at
all. "Did not read" and "read and found nothing" must not print as the same
thing.

A sum of the bodies means nothing, and calling that sum a "budget" makes it
read as a ceiling nobody ever set.

This is where the cost of adding pages becomes a number.

So the ceiling was removed. What would be cut is a rule a trigger matched —
the very thing judged necessary for this utterance — and a rule not arriving
is the failure this wiki exists to stop. A ceiling must not manufacture that
failure. A budget is set only by a project in `adapters/*.toml`, and even then
it trims rather than cuts: lower severities shrink to their one rule line, and
if it still does not fit, to a title and a path. No page disappears.

No value is not an unfinished setting, it is the default of *do not
abbreviate*. Picking a number from the current maximum size would revive the
groundless ceiling just removed under another name. A value is set after a
real injection limit or a drop in rule adherence has been observed, and cost
and adherence are measured together at that point.

A budget is a trimming target, not a hard ceiling. A rule's title and path and
a decision's name list have a minimum size, so a very small budget is simply
exceeded. Decisions summarise at most three and leave eight names and a total
for the rest — "every decision's name always survives" is the wrong reading too.

### The budget is per axis

There are two, `rule_budget` and `repo_budget`. With one, what shrinks when
space runs out is always the rules, because the trimming code trims rules and
does not touch a character of the decision record.

Leave a growing axis able to push out an axis that has to be held, and an
older project carries fewer rules.

`tool/test_inject.py` holds that ground. It also measures that the rules
actually do shrink when the two are not separated, so what this design
prevents is not erased by a single green.

### The warning moved from hit rate to size

A hit rate cannot measure harm — two summary lines riding on 47% of
utterances and seven full pages riding on 20% are entirely different things,
and the bad one is the second. The warning is now the median and how close it
comes to the ceiling.

What is needed at injection time is "this was already decided, and here is
why", not the full text.

Even within one rule, only the part a machine can judge goes down into a
check. Where a line broke can be counted; whether that sentence restates the
code has to be read. Make the second a check too and false positives stop the
work, and then the person turns the check off entirely.

Checking with a hook whether the watch was armed before sending would mean
guessing at state, and at layer 4 that produces false positives. A skill that
binds the two steps into one procedure removes the place the order can go
wrong instead.

**No layer without grounds, and no delay once there are grounds.**

## A census cannot see a rule that works

A census counts the instructions a user retyped, so a rule already enforced
produces no retyping and therefore reads as zero.

So there are two doors into a page.

| Door | Grounds | Example |
| --- | --- | --- |
| Repetition | It was retyped in two or more repositories | The review loop · post-merge cleanup |
| Enforcement | It already stands as a check or a block somewhere, and it travels | Blocking `git reset --hard` |

Without the second door, layer 1 never gains anything. What
`permissions.deny` blocks leaves not one line in a census.

## What is not done

- A `Stop` hook is not used to enforce "do not stop". When stopping is right
  is a judgement (only the user can decide · hard to reverse · the assumption
  is unsafe). Judged by a machine, it fails to stop where it should.
- `prompt` and `agent` type hooks are not used by default. They cost a model
  call on every tool call and their judgement wobbles. Only where `command`
  cannot do it.
- A check that produces false positives is not added. Enforcement that
  obstructs is enforcement the person turns off entirely.

The difference from layer 2 shows here. Layer 2 makes a rule read; layer 1
makes it impossible whether or not it was read. So anything that looks like a
command stops at layer 1 and never reaches layer 2.

What separates layer 4 from layer 1 is that the judgement takes computation.
That leaves room for false positives, and to narrow that room its target is
one thing: the `description` of `Bash`, `Agent` and `Task`. Not prompts, not
file contents. Anything goes wrong, it passes — enforcement that stops the
work is enforcement the person turns off entirely.

How to keep measuring whether the layers actually work is in "how to measure
whether a page works" in [`MAINTENANCE.md`](MAINTENANCE.md).
