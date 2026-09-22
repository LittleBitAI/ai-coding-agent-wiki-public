---
scope: craft
severity: landmine
triggers: ["마크다운", "markdown", "애스터리스크", "강조", "굵게", "\\*\\*", "문서를? (쓰|만들|생성)", "\\.md 문서"]
slots: []
enforce:
  pretooluse: markdown_emphasis.py
sources: []
sources_withheld: true
links: [comments-carry-why, screen-follows-the-purpose]
---

# Emphasis only works while it is scarce

Rule. One or two bolds per Markdown document, used only where the text reads
wrong without them. Never on a paragraph label, a command, a path, an
identifier or a status name — labels stay plain, the rest take backticks.

When it is broken. Emphasis turns into noise. Bold claims that a phrase
outranks the ones around it, and on every paragraph that claim is false
everywhere, so the reader stops seeing the marking at all. Then the one line
that really did matter goes past with the rest. That is worse than never having
emphasised anything.

## Why this page is on the second rung

It is the kind of rule that should have held as prose, and prose did not hold
it. One session put sixty bolds into four planning documents. Measuring the 21
pages already in the repository gave a median of 11.8% of prose lines and a
maximum of 40.9%, so the habit was learned from the corpus — which is exactly
why the corpus cannot set the threshold.

Two checks carry it, because one cannot. `tool/markdown_emphasis.py` runs
before a write and sees only what the call carries; `lint.loud_emphasis` runs
afterwards and reads the file.

The hook watches every editing tool on both hosts — `Write`, `Edit`,
`MultiEdit` from Claude, `apply_patch` from Codex, with or without a
`functions.` prefix — and only when the target path ends in `.md`. A patch is
judged at its `Move to:` destination, not at the file it came from.

| What it refuses | Whole document | Fragment |
| --- | --- | --- |
| Two or more bolds on one line | yes | yes |
| A bold run spanning a line break | yes | yes |
| A bolded paragraph label | yes | no |
| Over 15% of prose lines | yes | no |

`Write` and a patch's `Add File` carry a whole document. An `Edit`, a
`MultiEdit` and a patch hunk carry a fragment, and the last two checks need
surrounding text to be right — a ratio needs the whole document, a label needs
to know a block begins there. Guessing either from a fragment refuses correct
prose, and a hook that refuses correct prose gets switched off.

So what a fragment could push over the limit is caught afterwards.
`lint.loud_emphasis` reads every `.md` in the hub, and `repo_lint` runs the
same check in each target repository, which is where `sync` calls it on Stop.
A file it cannot read is itself a finding: skipping one quietly would make
"every `.md` passes" false while the gate stayed green.

## What the counter counts

Whatever CommonMark calls strong emphasis — `**bold**` and `__bold__` alike —
outside fences, tables, front matter and inline code. A parser decides that,
not a regex over the source.

Six rounds of review went into deciding it by hand, and every one of them said
the same thing in a different shape: a tilde fence, a four-backtick fence, an
info string, U+00A0, an escaped backtick, a code span crossing a line break,
`** not bold **`, `foo__bar__baz`. Each fix bought exactly one shape and the
next round found the next one. An inline lexer written a clause at a time
inside a style hook is not a job that ends, and each wrong clause either let
the rule be bypassed or refused correct prose.

`markdown-it-py` is in `requirements-dev.txt` and is not optional. When it is
missing the hook lets the write through and says so on screen, and `lint`
raises it as a finding. A check that cannot run and reports nothing reads
exactly like a check that ran and found nothing — that is how a gate stays
green with the rule switched off.

## What neither of them refuses

- Whether a given phrase deserves emphasis. That is taste, and a hook that
  argues about taste gets switched off — and then nothing is enforced at all.
- Anything inside a fence, a table or front matter. A bolded table cell often
  works as a label.
- A document with fewer than four bolds or fewer than eight prose lines. A
  ratio over that little says nothing either way.
- A bold inside a table cell — but the table has to be one. A block of
  pipe-shaped lines with no delimiter row is a paragraph, and CommonMark
  renders its pipes literally, so its emphasis counts like any other.
- Files that are not `.md`. Emphasis in code comments belongs to
  [[comments-carry-why]].

## The procedure lives in the skill

What to reach for instead — headings, tables, backticks, a rewritten sentence —
is in `skills/write-markdown`. The hook refuses only what is certain; the skill
carries the rest.

The same shape appears on screen. Emphasise everything and the hierarchy is
gone, and a screen without hierarchy cannot say what to look at first —
[[screen-follows-the-purpose]].
