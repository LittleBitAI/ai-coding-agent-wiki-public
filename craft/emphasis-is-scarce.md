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

`tool/markdown_emphasis.py` looks at `Write` and `Edit` when the target is a
`.md` file, and at nothing else.

| What it refuses | Why a machine can be sure |
| --- | --- |
| A bolded paragraph label | A short bold run opening a block and ending in `.` or `:` |
| Two or more bolds on one line | Countable |
| A bold run spanning a line break | Unreadable in the source |
| Over 15% of prose lines | A ratio |

## What it does not refuse

- Whether a given phrase deserves emphasis. That is taste, and a hook that
  argues about taste gets switched off — and then nothing is enforced at all.
- Anything inside a fence, a table or front matter. A bolded table cell often
  works as a label.
- A fragment with fewer than four bolds or fewer than eight prose lines. An
  `Edit` carries part of a document, not a document, so a ratio over it says
  nothing.
- Files that are not `.md`. Emphasis in code comments belongs to
  [[comments-carry-why]].

## The procedure lives in the skill

What to reach for instead — headings, tables, backticks, a rewritten sentence —
is in `skills/write-markdown`. The hook refuses only what is certain; the skill
carries the rest.

The same shape appears on screen. Emphasise everything and the hierarchy is
gone, and a screen without hierarchy cannot say what to look at first —
[[screen-follows-the-purpose]].
