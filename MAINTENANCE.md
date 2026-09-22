# Maintenance — when to diagnose and how to update

A wiki that is not maintained is worse than a stale one. It says wrong things
confidently.

## A wiki updated by hand is a wiki that does not get updated

So `tool/sync.py` hangs on the `Stop` hook and runs itself whenever work ends.

| What it reconciles | When it runs |
| --- | --- |
| The document listing | When a document was added, deleted or changed |
| The decision record | When there is a PR or commit not in the record (checked at most once every six hours) |
| The diagnosis | Every time |

Expensive means it gets switched off, and an automatic update that is switched
off is the same as none.

And this is why history is not accumulated in comments. What changed in which
PR and when is held by `.wiki/decisions/`, and that record is mined from
commits automatically. Write the same story into the source comments as well
and there are two copies, and two copies soon disagree — which is exactly the
drift this lint hunts.

That is history, not a reason.

Time is what separates them. Why this structure is visible whenever the code
changes, so it lives next to the code. When what was fixed does not change
when the code does, so it ages alone. What stays and what moves is held by
[`craft/comments-carry-why`](craft/comments-carry-why.md).

## Two kinds of rot

| What | Who catches it | How |
| --- | --- | --- |
| The hub wiki's structure rots | `tool/lint.py` | A machine judges links, orphans, grounds and triggers |
| An attached repository's knowledge rots | `tool/repo_lint.py` | Listings and pointers, seen only inside that repository |
| The content rots | Re-running `tool/census.py` | Measures from real utterances whether the rule is still broken |

`lint` catches the wiki disagreeing with itself. It cannot catch the wiki
disagreeing with the world. That only appears by running a census again.

The two axes differ, so the tools differ. What runs when work ends in a target
repository is `repo_lint` alone. Scatter the hub's findings there and every
session shows lines nothing in that session can act on, and a warning that
appears every time is not read.

## When — on events, not on a calendar

Hung on a calendar it does not run. Attach it to something that already happens.

| Trigger | What | Why there |
| --- | --- | --- |
| Whenever work ends | `sync` (the `Stop` hook) | Automatic |
| Post-merge cleanup | `lint` | One step of the `after-merge` skill. It happens most often |
| Just before `apply` | `lint` | A rotten wiki is not written into someone else's repository |
| **Right after changing `enforce`** | **`lint --check`** | A declaration changing without the install following was the longest-lived fault |
| **Every hub gate run** | **`lint --check`** | It is in the gate. Wiring out of step exits 1 |
| Right after changing a page | `lint` + `graph` | Links and triggers break while being changed |
| End of a day's work | The `retrospect` skill | Catch today's drift today |
| Attaching a new project | `census` + `intersect` | A new intersection changes existing pages' severities |
| On receiving the same finding again | Re-run `census` | That page is not working |

The last row is the most important in this document. `retrospect` takes the
place a census cannot: a census needs dozens of sessions to say anything,
while an incident from today repeats until the next census unless it is caught
today.

## What follows by itself and what waits for `apply`

| Changed | How it takes effect | Re-run `apply` |
| --- | --- | --- |
| A page body · triggers · adapter slots | `inject` reads the hub files when it runs | Not needed |
| The Python implementation of an existing hook | The next process reads the file the settings' absolute path points at | Not needed |
| **`enforce.deny` · a new hook · an event · a command option** | A **copy** embedded in the target's settings | **Needed** |
| Codex's deny patterns | `codex_pretool` reads `apply.declared()` at run time | Not needed once it is wired |
| **A new Codex event · a new pretool link** | `.codex/hooks.json` | **Needed** |
| Project documents · decisions | `SessionStart` and `Stop`→`sync`→`harvest` | A separate path |

There is no automatic deployment. `sync` updates the corpus, the decisions and
`repo_lint`, and does not call `apply`. The `after-merge` skill calls `lint`
only. So the session that changed a declaration has to deploy it too, and
nobody says so if it does not — `lint --check` is what was built to say so.

The cycle is this.

1. A declaration changes in the hub → that session's gate reads the hub wiring
   with `lint --check`
2. The target repository learns of its own missing wiring from the next
   `Stop`'s `repo_lint`
3. The actual update is done by the session that owns that target, with
   `apply --write`. Another repository's settings are never written
   automatically from here
4. A newly attached repository, or one installed through an aliased adapter,
   runs `--check` explicitly

## How to measure whether a page works

A census counts how many times each repeated instruction was retyped. If a
page was written because of some failure, a later count should have gone down.

    It did not go down  →  do not rewrite the page. Go up the ladder
    It went down        →  lower the severity or move it into a check, and cut the prose

`--since` cuts it to today, so a retrospective does not have to count by hand.

```bash
python tool/census.py --project <path> --since today
```

Severity is not chosen at the start, it is measured and corrected.

Going up one rung of the ladder in `ENFORCEMENT.md` is the answer.

## Updating — where something new goes

| What appeared | Where it goes | Threshold |
| --- | --- | --- |
| An incident seen once, in one repository | That repository's `CLAUDE.md` | None. It does not come into the wiki |
| Looks like it will repeat but there is one sample | Measurements only, in `raw/` | Write in that document what to count next time |
| The same incident in a second repository | A wiki page | `intersect` catches it in two or more |
| A rule already standing as a check or block somewhere | A wiki page | Does it still make sense moved |
| A page turns out to be wrong | Fix that page and update `sources` | Reproduction |
| A rule moves down to layer 1 | Fill `enforce.deny` and **`apply` to every target and every agent** | Is it actually blocked |
| A rule stops happening | Lower the severity or delete it | Zero in the next census |

The first row is the point of this table. An incident seen in one place
belongs to that repository, and bringing it here makes it someone else's
landmine.

The second row was added later. Before it, the only destinations were a page
or `CLAUDE.md`, and anything that was neither — seen once, and looking likely
to recur — had nowhere to go and disappeared inside the conversation. With the
number and what to count next written into `raw/`, counting costs almost
nothing when the second one arrives. Not creating a page is the point: writing
a rule from one sample makes that rule someone else's landmine, exactly as the
first row says.

The third row was added later too. A census counts what the user retyped, and
a rule already blocked produces no retyping. With only the first door open,
layer 1 never gains anything.

Applying a new `landmine` requires `sources` to say what it burned. Without
it, `lint` raises it.

## What to do with what `lint` finds

| Finding | What to do |
| --- | --- |
| A broken link | Write the page or remove the link. Check the threshold before writing |
| An orphan page | Link it from a related page. If nothing is related, reconsider why that page exists |
| A stale claim | Fix the grounds and the branch. If it is meant to be injected and has no trigger, write one |
| A `landmine` with no grounds | Name what it burned, or lower the severity |
| A missing connection | Link them, or narrow the triggers if they should not ride together |
| A contradiction (slots) | Below |

## A contradiction is not necessarily a fault

If two sources genuinely say different things, the wiki has to record that
fact. A machine cannot tell drift from an intended split, so `lint` raises
only what is undeclared and a person judges. The criteria and the
`conflicts_with` format are in "a contradiction is not necessarily a fault" in
`SCHEMA.md`.

Unifying before telling them apart erases information.

## What is not built

- There is no separate `log.md`. The original has one; here `git log` does
  that job. What changed and why is in the commit message, and the
  measurements from that moment are in a page's `sources`.
- Diagnosis results are not accumulated into files. `lint` reads a state, it
  is not a record. The same finding appearing over and over is a page to fix,
  not a file to keep.
- No calendar reminders. The trigger table above does that job.

## Grounds in the public copy

The original's rules, skills, applicability and severities are kept; only the
actual conversations, cases and measurements are withheld.
`sources_withheld: true` marks a rule whose grounds are private. `lint`
exempts the missing grounds only for existing rules carrying that mark, and it
does not substitute for a new rule's grounds. Installing and signing in with
your own CLI follows the [install guide](docs/chat-setup.md); managing the
public copy follows the [update guide](docs/publishing.md); what was verified
follows the [check record](docs/verification.md).
