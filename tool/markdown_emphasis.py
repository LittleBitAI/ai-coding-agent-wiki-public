"""PreToolUse hook — refuse a Markdown write whose emphasis has stopped working.

Bold is a claim that this phrase matters more than the ones around it. Put it on
every paragraph and the claim is false everywhere, so the reader stops seeing it
and the one line that really did matter goes past with the rest.

This only judges what a machine can be sure of. Whether a particular phrase
deserves emphasis is taste, and a hook that argues about taste gets switched
off — then nothing is enforced at all.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

# Both hosts' editing tools. Claude sends `Write`/`Edit`/`MultiEdit`; Codex
# sends `apply_patch`, sometimes as `functions.apply_patch`. Listing only
# Claude's names is how this hook came to be installed on Codex and let every
# Codex edit through -- wired, reported as enforced, never once firing.
WATCHED = {"Write", "Edit", "MultiEdit", "apply_patch"}

# `*** Add File: path` / `*** Update File: path` inside an apply_patch body,
# and the rename header that decides where the result actually lands.
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)
MOVE_TO = re.compile(r"^\*\*\* Move to: (.+)$", re.M)

# Emphasis is read off a CommonMark parse, not off regexes over the source.
#
# Six review rounds went into a hand-written scanner and every one of them
# found the same thing: the scanner and CommonMark disagreed about some input
# shape. A tilde fence, a four-backtick fence, an info string, U+00A0, an
# escaped backtick, a code span crossing a line break, `** not bold **`,
# `foo__bar__baz` — each needed one more clause of the spec, and the next
# round found the next shape. Reimplementing an inline lexer inside a style
# hook is not a job that ends, and every wrong clause either let the rule be
# bypassed or refused correct prose.
#
# So the parser answers. `markdown-it-py` is a strict CommonMark
# implementation, declared in requirements-hooks.txt -- the one file that
# says what a hooks install needs. It is not optional: a
# missing parser is reported, never quietly skipped, because "every `.md`
# passes" must not be able to mean "no `.md` was read".
# 화면의 복구 명령은 그대로 붙여 넣어 돌아야 한다. 그러려면 셋이 다 맞아야 한다.
# 경로는 절대경로여야 하고 — 훅의 작업 디렉터리는 대상 저장소이고 이 파일은 허브에
# 있다 — 따옴표로 감싸야 하며 — 이 저장소는 공백 경로를 지원한다고 적어 두었다 —
# 인터프리터는 `python` 이 아니라 훅이 실제로 돌고 있는 이것이어야 한다.
MISSING = (
    "markdown-it-py 가 없어 강조 검사를 돌리지 못했다 — "
    f'`"{sys.executable}" -m pip install -r '
    f'"{Path(__file__).resolve().parents[1] / "requirements-hooks.txt"}"`'
)

_PARSER: object | None = None


def parser():
    """The shared parser: CommonMark plus tables, or `None` when unavailable.

    Tables, because a bolded table cell often reads as a column label and this
    check has always exempted them. The bare commonmark preset has no table
    rule and would read a table as a paragraph and count its cells.

    Tables and nothing else. The `gfm-like` preset also turns on linkify, and
    linkify needs `linkify-it-py`, which is an *extra* of markdown-it-py that
    a plain `markdown-it-py` requirement does not install. Where it is absent
    `MarkdownIt("gfm-like")` constructs fine and then raises inside `parse` —
    past the `None` check, into the blanket except in `main`, and the write
    goes through with nothing said. That is the exact failure this check
    exists to prevent, so the preset that can reach it is not used.
    """

    global _PARSER
    if _PARSER is None:
        try:
            from markdown_it import MarkdownIt
        except Exception:
            return None
        _PARSER = MarkdownIt("commonmark").enable("table")
    return _PARSER


# A paragraph label: a short bolded run opening a block and ending in a period
# or a colon. This repo's own pages write those plain -- `규칙.`, `어겼을 때.` --
# and bolding them puts emphasis on the scaffolding instead of the content.
# This matches the text the parser resolved, so the delimiters are already
# gone and `**Rule.**` and `__Rule.__` arrive here identical.
LABEL = re.compile(r"^[^\n]{1,24}[.:]$")

# HTML's void elements, the whole list from the spec at once rather than a
# clause per review round. An inline tag is normally scaffolding around text
# and puts nothing on the page itself, so a bold behind `<span>` still opens
# its block. These are the exceptions: they render something by themselves,
# so a bold behind one is no longer the first thing the reader sees.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
TAG = re.compile(r"^<\s*([a-zA-Z][-a-zA-Z0-9]*)")


def standalone(raw: str) -> bool:
    """Does this inline tag put something on the page by itself?"""

    name = TAG.match(raw)
    return bool(name) and (
        name.group(1).lower() in VOID or raw.rstrip().endswith("/>"))

# Above this share of prose lines, emphasis is no longer marking exceptions.
# Not taken from the pages in this repo: several of them are already past it,
# which is how the habit spread in the first place.
LIMIT = 0.15
MIN_BOLD = 4      # below this, density says nothing
MIN_LINES = 8     # an Edit fragment shorter than this is not a document

REASON = (
    "Review this document's emphasis before writing it. Bold claims that a\n"
    "phrase outranks the ones around it; put it on every paragraph and the\n"
    "claim is false everywhere, so the reader stops seeing it.\n"
    "\n"
    "{findings}\n"
    "Check before writing.\n"
    "- Paragraph labels stay plain (`규칙.` `어겼을 때.` `목표.`). House style.\n"
    "- One or two bolds per document, only where the text reads wrong without\n"
    "- Commands, paths, identifiers and status names take backticks, not bold\n"
    "- Two in a paragraph, or one holding a line break, is unreadable in source\n"
    "- For the rest, fix the sentence instead of propping it up with emphasis\n"
    "\n"
    "`skills/write-markdown` holds the procedure."
)


def blanked(text: str) -> str:
    """`text` with YAML front matter replaced by empty lines.

    Blanked rather than cut, so every remaining line keeps its number. Front
    matter is not prose, and this repo's `triggers` hold regexes with asterisks
    in them.
    """

    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for n, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                lines[:n + 1] = [""] * (n + 1)
                break
    return "\n".join(lines)


def scan(text: str) -> tuple[int, int, list[str], int, int]:
    """`(crowded blocks, bolds holding a line break, labels, prose lines, bolds)`.

    Only what a reader reads as prose gets here. A fence, a table and inline
    code carry no emphasis tokens of their own, so nothing inside them is
    counted without a single rule about any of them being written here.

    Counted per block, never per line. Inline children carry no source
    positions, and the obvious reconstruction — start at the block's first line
    and step on every soft break — is wrong: a code span's newlines are already
    spaces by the time it is a token, so every line it swallowed is lost and
    every count after it is off. A review round found both faces of that, a
    missed line-spanning bold and two bolds from different lines reported as
    one crowded line. What ends it is not counting lines. A block is a unit the
    parser hands over exactly.
    """

    md = parser()
    crowded = bolds = wrapped = 0
    labels: list[str] = []
    rows: set[int] = set()
    table = 0
    for token in md.parse(blanked(text)):
        if token.type == "table_open":
            table += 1
        elif token.type == "table_close":
            table -= 1
        if token.type != "inline" or token.map is None or table:
            continue
        rows.update(range(token.map[0], token.map[1]))
        children = token.children or []
        # Lines the block covers that no break accounts for. Those went into a
        # code span, which is the one place a newline disappears from the token
        # stream — it is how `**`+"`a\nb`"+`**` looks like a single-line bold.
        breaks = sum(1 for c in children if c.type in ("softbreak", "hardbreak"))
        # A newline the block covers is in exactly one of three places: a break
        # token, a token that still carries it (an inline tag written across
        # lines keeps its own), or a code span, which replaced it with a space
        # and is the only one that cannot be counted directly.
        kept = sum(c.content.count("\n") for c in children if c.content)
        folded = max(0, token.map[1] - token.map[0] - 1 - breaks - kept)
        # So which code span ate the rest is still unrecorded, and a bold owns
        # that residue only when every code span in the block is inside it.
        # Charging it to any bold that merely holds one refused correct prose
        # twice: beside an unrelated span that wrapped, and beside a tag that
        # did -- the second only because tags were counted as folding at all.
        spans = sum(1 for c in children if c.type == "code_inline")

        here = 0
        opens: list[dict] = []
        # True until something printable has been seen in this block, which is
        # what makes a bold run a label rather than mid-sentence emphasis.
        first = True
        for child in children:
            if child.type in ("softbreak", "hardbreak"):
                for frame in opens:
                    frame["broken"] = True
                first = False
            elif child.type == "strong_open":
                opens.append({"parts": [], "opened": first, "broken": False,
                              "spans": 0})
                first = False
            elif child.type == "strong_close" and opens:
                frame = opens.pop()
                here += 1
                if frame["broken"] or (
                        folded and frame["spans"] and frame["spans"] == spans):
                    wrapped += 1
                inner = "".join(frame["parts"])
                if frame["opened"] and LABEL.match(inner):
                    labels.append(inner)
                if opens:
                    opens[-1]["parts"].append(inner)
            elif child.type == "html_inline":
                # A tag written across lines carries the newline itself, and
                # the bold holding it holds a line break as surely as one
                # holding a soft break.
                if "\n" in child.content:
                    for frame in opens:
                        frame["broken"] = True
                # Its source is never label text. Whether it ends the run of
                # nothing-seen-yet is a separate question, and both blanket
                # answers were review findings: counting every tag as visible
                # let `<span>**Rule.**</span>` through, counting none as
                # visible refused `<img src=x> **Rule.**`.
                if standalone(child.content):
                    first = False
            elif child.content:
                for frame in opens:
                    frame["parts"].append(child.content)
                    if child.type == "code_inline":
                        frame["spans"] += 1
                if child.content.strip():
                    first = False
        bolds += here
        if here > 1:
            crowded += 1
    return crowded, wrapped, labels, len(rows), bolds


def findings(text: str, whole: bool = True) -> list[str]:
    """Everything certain that is wrong with this text's emphasis.

    `whole` is False when the result could not be reconstructed and only a
    fragment is in hand. Two of the checks need surrounding text to be right —
    a ratio needs the whole document, and a label needs to know a block starts
    there. On a fragment both are guesses, and a guess that refuses correct
    prose is how a hook gets switched off. Only the context-free two remain.

    A missing parser is not a finding here. This runs in two places that must
    say so differently: the hook tells the session and lets the write through,
    `lint` fails the gate. Returning `[]` would tell both of them "clean".
    """

    if parser() is None:
        return []

    crowded, wrapped, labels, rows, bold = scan(text)

    found = []
    if whole and labels:
        found.append(f"- 문단 라벨을 굵게 했다 ({len(labels)}곳): {labels[0]} …")

    if crowded:
        found.append(f"- 한 문단에 굵게가 둘 이상인 문단이 {crowded}개 있다")

    if wrapped:
        found.append(f"- 줄바꿈을 품은 굵게가 {wrapped}곳 있다")

    if whole and bold >= MIN_BOLD and rows >= MIN_LINES:
        share = bold / rows
        if share > LIMIT:
            found.append(
                f"- 산문 {rows}줄에 굵게가 {bold}개다 "
                f"({share:.0%}, 상한 {LIMIT:.0%})"
            )
    return found


def written(given: dict, tool: str) -> list[tuple[str, str, bool]]:
    """`(path, text, whole)` for what this call puts on the page.

    It does not predict the resulting document, and that is the point. Three
    review rounds found faces of trying to: a tool name, a rename header, a
    dropped context line, a second hunk, `replace_all`, a four-backtick fence.
    Each fix reimplemented a little more of `git apply` and a Markdown lexer
    inside a style hook, and the next round found the next input shape.

    So this claims only what it can see. `Write` carries a whole document and
    is judged as one. Everything else is a fragment and gets the two checks
    that hold on any text by itself. What a fragment could push over the limit
    is caught by `lint.loud_emphasis`, which reads the real file afterwards and
    has nothing to guess about.

    One entry per fragment, never one joined entry. Joining a `MultiEdit`'s
    edits with a newline built a paragraph that exists in no file: two edits
    landing in two different paragraphs read as one paragraph with two bolds,
    and correct prose was refused. The same for a patch's hunks. Whatever
    separates two fragments in the real file is not in this call, so they are
    not put next to each other here.
    """

    path = str(given.get("file_path") or "")
    if path:
        if tool == "Write":
            text = str(given.get("content") or "")
            return [(path, text, True)] if text.strip() else []
        edits = given.get("edits")
        pairs = (
            [e for e in edits if isinstance(e, dict)] if isinstance(edits, list)
            else [given]
        )
        return [(path, str(e.get("new_string") or ""), False) for e in pairs
                if str(e.get("new_string") or "").strip()]

    patch = str(given.get("input") or given.get("patch") or "")
    out = []
    for match in PATCH_FILE.finditer(patch):
        after = PATCH_FILE.search(patch, match.end())
        body = patch[match.end():after.start() if after else len(patch)]
        # The destination, not the source. A patch may rename as it edits, and
        # reading only the source header lets `notes.txt -> docs/x.md` past a
        # check that keys on the extension.
        moved = MOVE_TO.search(body)
        where = (moved.group(1) if moved else match.group(1)).strip()
        whole = match.group(0).startswith("*** Add File:")
        # One entry per run of consecutive added lines. Only such a run is
        # contiguous in the result; joining runs that a context line or a
        # second hunk separates invents a paragraph no file contains. An
        # `Add File` body is one run, so it arrives whole either way.
        run: list[str] = []
        for line in body.splitlines() + [""]:
            if line.startswith("+"):
                run.append(line[1:])
                continue
            if "".join(run).strip():
                out.append((where, "\n".join(run), whole))
            run = []
    return out


def verdict(payload: dict) -> dict | None:
    """The hook's answer, or `None` to let the write through."""

    # Codex prefixes some tool names with `functions.`.
    tool = str(payload.get("tool_name") or "").removeprefix("functions.")
    if tool not in WATCHED:
        return None

    targets = [
        (text, whole)
        for path, text, whole in written(payload.get("tool_input") or {}, tool)
        if path.lower().endswith(".md")
    ]
    if not targets:
        return None
    if parser() is None:
        # Let the write through — a style hook must never stop the work — but
        # say so on screen. A check that cannot run and reports nothing is
        # indistinguishable from a check that ran and found nothing, and that
        # is the shape this repo calls a silent gate.
        return {"systemMessage": MISSING}

    found = []
    try:
        for text, whole in targets:
            found += findings(text, whole)
    except Exception as error:  # noqa: BLE001
        # `main` catches this too and passes silently, which is the fail-open
        # contract and is right -- but silent is what makes a broken check
        # indistinguishable from a clean document. One preset already reached
        # here: `gfm-like` constructs without `linkify-it-py` and then raises
        # inside `parse`. Say it on screen and still let the write through.
        return {"systemMessage": f"강조 검사가 실패했다: {type(error).__name__}"}
    if not found:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON.format(findings="\n".join(found)),
        },
        "systemMessage": f"마크다운 강조 검토: {len(found)}건",
    }


def main() -> int:
    # Both the text being judged and the message going back carry Korean.
    # The encoding is not left to whatever the environment happens to give.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        payload = json.load(sys.stdin)
        answer = verdict(payload if isinstance(payload, dict) else {})
    except Exception:
        return 0  # Pass. A broken hook must never stop the work.
    if answer:
        json.dump(answer, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    # Covers the rule above outside `main` too. Anything wrong means pass.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
