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

# `*** Add File: path` / `*** Update File: path` inside an apply_patch body.
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)

BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)

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
    fence = False
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
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
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

    `whole` is False when the text is part of a document rather than all of it
    — an `Edit` replacement or the added lines of a patch. A ratio over a
    fragment says nothing, so density is only judged on a whole document.
    """

    found = []
    rows = prose(text)
    lines = [line for line, _opens in rows]
    body = "\n".join(lines)

    labels = [line.strip()[:40] for line, opens in rows if opens and LABEL.match(line)]
    if labels:
        found.append(f"- 문단 라벨을 굵게 했다 ({len(labels)}곳): {labels[0]} …")

    twice = sum(1 for line in lines if len(BOLD.findall(line)) > 1)
    if twice:
        found.append(f"- 한 줄에 굵게가 둘 이상인 줄이 {twice}개 있다")

    wrapped = sum(1 for m in BOLD.finditer(body) if "\n" in m.group(1))
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


def targets(given: dict, tool: str) -> list[tuple[str, str, bool]]:
    """`(path, text, whole)` for every file this call would write.

    Three shapes reach here. `Write` carries a whole document, `Edit` and
    `MultiEdit` carry replacements, and `apply_patch` carries a patch body that
    can touch several files at once.
    """

    path = str(given.get("file_path") or "")
    if path:
        edits = given.get("edits")
        if isinstance(edits, list):
            text = "\n".join(
                str(e.get("new_string") or "") for e in edits if isinstance(e, dict)
            )
        else:
            text = str(given.get("content") or given.get("new_string") or "")
        return [(path, text, tool == "Write")] if text.strip() else []

    patch = str(given.get("input") or given.get("patch") or "")
    if not patch:
        return []
    out = []
    for match in PATCH_FILE.finditer(patch):
        after = PATCH_FILE.search(patch, match.end())
        chunk = patch[match.end():after.start() if after else len(patch)]
        # Only the added lines. The context and removals are what is already
        # there, and judging those would refuse an edit for someone else's bold.
        added = "\n".join(
            line[1:] for line in chunk.splitlines() if line.startswith("+")
        )
        if added.strip():
            out.append((match.group(1).strip(), added, False))
    return out


def verdict(payload: dict) -> dict | None:
    """The hook's answer, or `None` to let the write through."""

    # Codex prefixes some tool names with `functions.`.
    tool = str(payload.get("tool_name") or "").removeprefix("functions.")
    if tool not in WATCHED:
        return None

    found = []
    for path, text, whole in targets(payload.get("tool_input") or {}, tool):
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
