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

WATCHED = {"Write", "Edit"}

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
        if line.lstrip().startswith("```"):
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


def findings(text: str) -> list[str]:
    """Everything certain that is wrong with this text's emphasis."""

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
    if bold >= MIN_BOLD and len(lines) >= MIN_LINES:
        share = bold / len(lines)
        if share > LIMIT:
            found.append(
                f"- 산문 {len(lines)}줄에 굵게가 {bold}개다 "
                f"({share:.0%}, 상한 {LIMIT:.0%})"
            )
    return found


def verdict(payload: dict) -> dict | None:
    """The hook's answer, or `None` to let the write through."""

    if str(payload.get("tool_name")) not in WATCHED:
        return None
    given = payload.get("tool_input") or {}
    path = str(given.get("file_path") or "")
    if not path.lower().endswith(".md"):
        return None
    written = str(given.get("content") or given.get("new_string") or "")
    found = findings(written)
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
