---
name: design-pass
description: >-
  Design or rework a frontend screen in a fixed order — purpose and layout first,
  then measure padding/width/alignment and button wiring in a real browser, then
  typography hierarchy, then propose a color palette to the user, then fill the
  leftover whitespace. Use when asked to design, build, lay out or polish a UI,
  dashboard, landing page or detail page, or when the user says "디자인",
  "프런트엔드", "레이아웃", "타이포", "색 배합", "UI 다듬어". For motion and
  animation work use emil's `animate` / `review-animations` instead.
---

# One design pass — five steps

The rule behind this skill is `craft/screen-follows-the-purpose`. Why the order
is what it is lives on that page; only how to do it is written here.

Do all five. Do not reorder them. Hand step 4 to the user once.

## 0. One line on what is being built

Write this before opening a file.

```
Who:      <the person who arrives at this screen>
To do:    <one thing>
Success:  <what they see when it is done>
```

These three lines pick the screen list. If you cannot write them, ask the user.
A detail page and a dashboard are defaults, not answers. Do not build by default.

## 1. `DESIGN.md` and the sketch

Read `DESIGN.md` at the project root, or create it if it is not there.

- Borrow one — pick the closest purpose at <https://getdesign.md/>
- Format — the spec at <https://github.com/google-labs-code/design.md>
- Tokens in the front matter (`colors` `typography` `spacing` `rounded`
  `components`), and why they were chosen in the body

Leave a value empty when it is not decided yet and fill it in step 4. Empty and
undecided are different things: an empty slot becomes step 4's work.

Call `better-layout` for the sketch. Grouping, alignment, reading order and
progressive disclosure all belong to that skill. Use `prototype` or `variant`
when several options should be put side by side.

## 2. Measure it in a browser — do not eyeball it

Start it inside this cell (`operator/run-inside-this-session`). Open a new tab
with `claude-in-chrome` and pull two things out as numbers.

### 2-1. Does the same role use the same values

Run it with `javascript_tool` and read it with `read_console_messages`. It only
prints what disagrees, so `{}` means it passed.

```js
const seen = {};
for (const el of document.querySelectorAll('main *, [class*="card"], button')) {
  const s = getComputedStyle(el);
  const key = el.tagName + '.' + (el.className.baseVal ?? el.className).split(' ')[0];
  (seen[key] ??= new Set()).add(
    `pad=${s.padding} gap=${s.gap} w=${Math.round(el.getBoundingClientRect().width)}`
  );
}
console.log('[design-pass]', JSON.stringify(Object.fromEntries(
  Object.entries(seen).filter(([, v]) => v.size > 1).map(([k, v]) => [k, [...v]])
), null, 1));
```

Measure the width twice — a wide window, and 400px via `resize_window`. A
horizontal scrollbar appearing is itself a finding.

### 2-2. Do the buttons actually fire

Press every visible button one at a time and confirm on the console and the
network. A button with no handler attached looks perfectly fine, which is
exactly why this step exists.

Do not press a button that raises `alert` or `confirm`. It freezes the session.
For anything likely to carry a confirmation, such as a delete, read the code to
see whether a handler is bound instead.

Fix the findings and run step 2 again. Not measuring after a fix leaves it
indistinguishable from not having fixed it.

## 3. Typographic hierarchy

Call `better-typography`. Two things have to hold.

- The levels can be counted — you can answer how many size and weight
  combinations the screen uses
- Their uses do not overlap — one level never carries two meanings

Check it against `typography` in `DESIGN.md`. If there is nothing to check
against, decide it here and write it down.

## 4. Colour — you build the candidates, the user picks

Build two or three candidates for the project with `better-colors`. Check the
contrast of each and keep only what passes.

Then hand it over with `AskUserQuestion` (`operator/ask-with-arrow-key-options`).
Put the consequence in each option rather than a colour name: what gets
emphasised, what recedes, what impression it leaves.

Write what was picked into `colors` in `DESIGN.md`. Only that makes the next
session use the same blue.

## 5. Leftover whitespace

Sweep once at the end. Where it looks bare, first ask whether there is anything
worth putting there.

| The place | What goes in |
| --- | --- |
| There are numbers | Chart, sparkline, stat tile — the `dataviz` skill holds the rules |
| Something needs explaining | Large type, a pull quote, a section opener |
| A relationship has to be shown | A diagram |
| There is nothing worth putting | Leave it. A number invented to fill space is not an infographic. |

## When it is done

All five steps are done, step 2's output is empty, and the user has picked in
step 4. Check one last time that what was decided landed in `DESIGN.md`.

## What this skill does not do

- Motion. Movement belongs to emil's skills: `animate` to build one,
  `review-animations` to look at an existing one,
  `find-animation-opportunities` to find where one belongs.
- Wiring. Once the screen starts writing to a server, settle the account
  boundary and async ownership first
  (`craft/screen-ownership-before-wiring`). This skill stops before that.
