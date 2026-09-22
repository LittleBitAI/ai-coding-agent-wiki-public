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

# A fenced code block per CommonMark: up to three spaces of indent, then three
# or more backticks or tildes, then an info string.
FENCE = re.compile(r"^ {0,3}(?P<run>`{3,}|~{3,})(?P<info>.*)$")

# Both spellings Markdown renders as bold. Counting only `**` left `__` as a
# way out of the rule that nobody had to argue for.
BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)

# Inline code, lifted before counting. Asterisks inside it are characters, not
# emphasis, and counting them refused correct prose about Markdown itself.
CODE = re.compile(r"`+[^`\n]*`+")

# A paragraph label: the line opens with a short bolded run ending in a period
# or a colon. This repo's own pages write those plain -- `규칙.`, `어겼을 때.` --
# and bolding them puts emphasis on the scaffolding instead of the content.
LABEL = re.compile(r"^\s*\*\*[^*\n]{1,24}[.:]\*\*")

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


def prose(text: str) -> list[tuple[str, bool]]:
    """`(line, opens_a_block)` for what a reader reads as prose.

    Fences, tables and front matter are not prose. The flag matters because a
    bold run at the start of a *wrapped* line is ordinary mid-sentence emphasis,
    while the same run at the start of a block is a label. Without the
    distinction the check fires on correct prose, and a hook that fires on
    correct prose gets switched off — and then it enforces nothing.
    """

    out: list[tuple[str, bool]] = []
    # The run that opened the current block, or `""` outside one.
    fence = ""
    blank = True
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for n, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                start = n + 1
                break
    for line in lines[start:]:
        # Both fence spellings. Only backticks were recognised at first, so a
        # tilde-fenced code sample counted as prose and its asterisks pushed a
        # correct document over the limit.
        # The whole CommonMark fence rule at once, not one condition per
        # review round. Three rounds each added a single missing clause — the
        # marker character, then its length, then the info string — and each
        # time the next input shape was still wrong. What ends that is writing
        # the rule rather than the cases.
        mark = FENCE.match(line)
        if mark:
            run, info = mark.group("run"), mark.group("info")
            if fence:
                # A close is the same character, at least as long, and carries
                # no info string. Anything else on that line is content.
                # `strip()` here also ate U+00A0, which CommonMark counts as
                # content. Only ASCII space and tab are blank in a fence line.
                if (run[0] == fence[0] and len(run) >= len(fence)
                        and not info.strip(" \t")):
                    fence = ""
                    blank = True
                    continue
            # A backtick fence's info string may not contain a backtick, so
            # `` `a` and `b` `` on its own line opens nothing.
            elif not (run[0] == "`" and "`" in info):
                fence = run
                blank = True
                continue
        if fence:
            continue
        if not line.strip():
            blank = True
            continue
        if line.lstrip().startswith("|"):
            blank = True
            continue
        out.append((line, blank))
        blank = False
    return out


def findings(text: str, whole: bool = True) -> list[str]:
    """Everything certain that is wrong with this text's emphasis.

    `whole` is False when the result could not be reconstructed and only a
    fragment is in hand. Two of the checks need surrounding text to be right —
    a ratio needs the whole document, and a label needs to know a block starts
    there. On a fragment both are guesses, and a guess that refuses correct
    prose is how a hook gets switched off. Only the context-free two remain.
    """

    found = []
    rows = prose(text)
    # Inline code is blanked, not removed, so line numbers and the label check
    # still see the line they were written against.
    lines = [CODE.sub(lambda m: " " * len(m.group(0)), line) for line, _ in rows]
    body = "\n".join(lines)

    labels = [
        line.strip()[:40] for (line, opens), bare in zip(rows, lines)
        if whole and opens and LABEL.match(bare)
    ]
    if labels:
        found.append(f"- 문단 라벨을 굵게 했다 ({len(labels)}곳): {labels[0]} …")

    twice = sum(1 for line in lines if len(BOLD.findall(line)) > 1)
    if twice:
        found.append(f"- 한 줄에 굵게가 둘 이상인 줄이 {twice}개 있다")

    wrapped = sum(1 for m in BOLD.finditer(body) if "\n" in (m.group(1) or m.group(2)))
    if wrapped:
        found.append(f"- 줄바꿈을 건너뛰는 굵게가 {wrapped}곳 있다")

    bold = len(BOLD.findall(body))
    if whole and bold >= MIN_BOLD and len(lines) >= MIN_LINES:
        share = bold / len(lines)
        if share > LIMIT:
            found.append(
                f"- 산문 {len(lines)}줄에 굵게가 {bold}개다 "
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

    found = []
    for path, text, whole in written(payload.get("tool_input") or {}, tool):
        if path.lower().endswith(".md"):
            found += findings(text, whole)
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
