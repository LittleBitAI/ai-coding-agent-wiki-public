---
name: write-markdown
description: >-
  Write or revise a Markdown document so its formatting carries meaning instead
  of decorating it — emphasis used sparingly, structure doing the work, code
  spans for anything literal. Use before creating or rewriting any `.md` file,
  and when the user says "마크다운", "강조", "애스터리스크", "굵게", "문서 다듬어",
  or says a document reads strangely.
---

# Writing a Markdown document

The rule behind this skill is `craft/emphasis-is-scarce`. Why it matters is on
that page; only how to do it is written here.

`tool/markdown_emphasis.py` refuses a `.md` write that breaks the mechanical
parts. This skill covers the rest, which is most of it.

## The one idea

Formatting is a claim about the text under it. Bold claims this phrase outranks
its neighbours. A heading claims a new subject starts here. A list claims these
items are parallel. Make a claim that is not true and the reader learns to stop
believing the others.

That is why emphasis gets scarce rather than tidy. Two bolds in a document are
two claims a reader will check. Twenty are wallpaper.

## Before writing

Decide what the document is, because it sets everything else.

| Kind | What carries the structure |
| --- | --- |
| A rule or a decision | The rule sentence first, then why, then what breaks |
| A procedure | Numbered steps, one action each |
| A reference | Tables and lists; prose only where a table would lie |
| An explanation | Paragraphs. Resist the urge to bullet an argument |

## While writing

Reach for structure before emphasis. They compete, and structure wins.

- A heading beats a bolded lead-in. It shows up in the outline; the bold does not.
- A table beats a paragraph full of bolded field names.
- A code span beats bold for anything literal: a command, a path, an identifier,
  a filename, a status value, a flag. `--ff-only`, not **--ff-only**.
- A rewritten sentence beats emphasis inside a weak one. If a clause needs bold
  to land, the sentence is usually the problem.

Paragraph labels stay plain. This repo writes `규칙.`, `어겼을 때.`, `목표.` with
no bold, and the hook enforces that. The label is scaffolding; bolding it puts
the emphasis on the frame instead of the picture.

Keep bold to phrases, never whole sentences and never across a line break. A
bold run that wraps is unreadable in the source, which is where it gets edited.

Italics are for a term being introduced or a word used as a word. They are not
a weaker bold; reaching for them because bold felt like too much is a sign the
sentence needs work instead.

## Before saving

Read the document once looking only at what is marked up.

1. Count the bolds. More than two or three in a page, and cut until the ones
   left are the ones you would defend.
2. For each survivor, ask what goes wrong if it is plain. No answer means cut it.
3. Check every literal — command, path, identifier, filename — is in backticks
   rather than bold.
4. Check the headings alone read as an outline of the document.

## What this skill does not do

- It does not police prose style, only what the formatting claims.
- It does not apply to generated output, logs, or data files that happen to end
  in `.md`.
