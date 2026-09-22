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
# implementation, declared in requirements-dev.txt. It is not optional: a
# missing parser is reported, never quietly skipped, because "every `.md`
# passes" must not be able to mean "no `.md` was read".
MISSING = (
    "markdown-it-py 가 없어 강조 검사를 돌리지 못했다 — "
    "`python -m pip install -r requirements-dev.txt`"
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
    "- Two on a line, or one spanning a line break, is unreadable in the source\n"
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


def scan(text: str) -> tuple[dict[int, int], int, list[str], int]:
    """`(bolds per line, bolds crossing a line break, labels, prose lines)`.

    Only what a reader reads as prose gets here. A fence, a table and inline
    code carry no emphasis tokens of their own, so nothing inside them is
    counted without a single rule about any of them being written here.
    """

    md = parser()
    per_line: dict[int, int] = {}
    wrapped = 0
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
        # Inline children carry no line numbers, so count them off the block's
        # first line: a soft or hard break is exactly one line down, and a code
        # span's own newlines are already spaces by the time it is a token.
        line = token.map[0]
        opens: list[list] = []
        # True until something printable has been seen on this block, which is
        # what makes a bold run a label rather than mid-sentence emphasis.
        first = True
        for child in token.children or []:
            if child.type in ("softbreak", "hardbreak"):
                line += 1
                first = False
            elif child.type == "strong_open":
                opens.append([line, [], first])
                first = False
            elif child.type == "strong_close" and opens:
                start, parts, opened = opens.pop()
                if start == line:
                    per_line[start] = per_line.get(start, 0) + 1
                else:
                    wrapped += 1
                inner = "".join(parts)
                if opened and LABEL.match(inner):
                    labels.append(inner)
                if opens:
                    opens[-1][1].append(inner)
            elif child.content:
                for frame in opens:
                    frame[1].append(child.content)
                if child.content.strip():
                    first = False
    return per_line, wrapped, labels, len(rows)


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

    per_line, wrapped, labels, rows = scan(text)

    found = []
    if whole and labels:
        found.append(f"- 문단 라벨을 굵게 했다 ({len(labels)}곳): {labels[0]} …")

    twice = sum(1 for count in per_line.values() if count > 1)
    if twice:
        found.append(f"- 한 줄에 굵게가 둘 이상인 줄이 {twice}개 있다")

    if wrapped:
        found.append(f"- 줄바꿈을 건너뛰는 굵게가 {wrapped}곳 있다")

    bold = sum(per_line.values()) + wrapped
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
    that hold on any line by itself. What a fragment could push over the limit
    is caught by `lint.loud_emphasis`, which reads the real file afterwards and
    has nothing to guess about.
    """

    path = str(given.get("file_path") or "")
    if path:
        edits = given.get("edits")
        pairs = (
            [e for e in edits if isinstance(e, dict)] if isinstance(edits, list)
            else [given]
        )
        text = "\n".join(str(e.get("new_string") or "") for e in pairs)
        if tool == "Write":
            text = str(given.get("content") or "")
        return [(path, text, tool == "Write")] if text.strip() else []

    patch = str(given.get("input") or given.get("patch") or "")
    out = []
    for match in PATCH_FILE.finditer(patch):
        after = PATCH_FILE.search(patch, match.end())
        body = patch[match.end():after.start() if after else len(patch)]
        # The destination, not the source. A patch may rename as it edits, and
        # reading only the source header lets `notes.txt -> docs/x.md` past a
        # check that keys on the extension.
        moved = MOVE_TO.search(body)
        added = "\n".join(
            line[1:] for line in body.splitlines() if line.startswith("+")
        )
        if added.strip():
            whole = match.group(0).startswith("*** Add File:")
            out.append(((moved.group(1) if moved else match.group(1)).strip(),
                        added, whole))
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
