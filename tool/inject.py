"""UserPromptSubmit hook — read the utterance, put the matching page in context.

What this injects is agent input, so it goes out in English. The pages and
decision records it reads are Korean, and the translation happens on the way
out rather than in the files.
"""

from __future__ import annotations

# First import of the entry point: it keeps the stack from before whatever
# time limit kills this.
import hook_diagnostics  # noqa: F401
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import trajectory
import translate
from wikilib import WIKI, front_matter, rule_paragraph

INJECTABLE = {"landmine", "contract"}
SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")
HANGUL = re.compile(r"[가-힣]")

# The budget for the whole translation, kept under the hook's own 15 seconds.
# Going over does not cost the translation, it costs the entire injection.
# Whatever is not done by then goes out as the Korean original.
BUDGET = 8.0

# The length past which no English rendering of the utterance is attached.
# Unlike the rule budget, this block cannot be trimmed: a cut translation
# reads exactly like a whole one. So it is a threshold, not a ceiling.
MAX_RENDERED = 4000

# No budget by default. Every rule that matched is carried.
#
# Because nothing here may be dropped. What would be dropped is a rule the
# triggers selected — the one judged necessary for this utterance — and a rule
# broken because it was never carried is the failure this wiki exists to
# prevent. A ceiling must not manufacture that failure itself.
#
# Where a budget is set, it trims rather than cuts. The lowest severity goes
# from full text to its one rule line first, and past that to a title and a
# path. No page disappears.
#
# The project sets the budget through its adapter. It has nothing to do with
# the target repository's prompt limit: a hook's `additionalContext` does not
# travel that path, so borrowing that number here imposes someone else's
# ceiling.
#
# One budget per axis, deliberately. Sharing one means the thing that shrinks
# under pressure is always the rules, because `fit` trims rules and does not
# touch a decision record. The heaviest turn actually measured held
# 20,620 characters of rules against 2,173 of decisions: knowledge is 9% of
# it and carries 0% of the trimming. The side that grows must not push out
# the side that has to hold.
RULE_BUDGET = "rule_budget"
REPO_BUDGET = "repo_budget"

# Each host's ceiling on `additionalContext`, in UTF-8 bytes. Past it the host
# stores the injection in a file and hands the session a 2 KB preview, so a
# page carried on that turn was not read. Bytes, because a byte-level BPE
# never makes more tokens than bytes: under the ceiling in bytes is under it in
# tokens. Characters give no such bound — one Hangul syllable can be several
# tokens.
#
# Codex: the install sets `additionalContextLimit = 12000`, in tokens
# (`tool/apply.py` gives the default as "2,500 tokens"), so 12,000 bytes is on
# the safe side. Claude: no published unit, so it was read off the transcripts
# on 2026-09-25 — 3,784 injections, the largest kept whole 9,896 characters
# (19,466 bytes), the smallest sent to a file 10,015 characters. Claude counts
# characters, and characters never exceed bytes, so 9,800 bytes is under it.
# `trigger_audit replay` prints the same two numbers for the sessions it reads.
#
# A host missing here gets no deduplication. Set low, the error is sending
# full text more often, which is the right direction to be wrong in.
LIMIT = {"codex": 12000, "claude": 9800}

# What a compact leaves in each host's transcript. Unescaped quotes on purpose:
# the same words inside a message are JSON-escaped and do not match.
COMPACTED = (b'"subtype":"compact_boundary"', b'"type":"compacted"')

# How many decision records go in as full text in one turn. What is over that
# is not dropped; its name stays.
MAX_DECISIONS = 3

# The similarity supplement — `searchd`. It adds a line for a page the regex
# did not choose; it never removes or shortens one the regex did. `SUGGEST_MIN`
# is the floor on `SUGGEST_BY`, set from the recall labels (plan bundle 2,
# step 5); `None` means the supplement is off and the daemon is not asked.
#
# Off, measured on 2026-09-25: over 187 labelled turns no floor on either score
# reached 60% precision — the best was 7%. Most missed pages are behavioural
# rules (`do-the-whole-instruction` is 27 of 78) that a short utterance says
# nothing about. Rerun `trigger_audit.py suggest` before switching it on.
SUGGEST_BY = "cos"
SUGGEST_MIN: float | None = None
SUGGEST_K = 2
# Past this the turn goes without. The daemon answers in about 10 ms.
SEARCH_TIMEOUT = 0.15

RENDERING = (
    "<!-- wiki:english-rendering -->\n"
    "English rendering of the user's message (Gemini). The Korean above is "
    "authoritative — go back to it wherever this reads oddly.\n\n"
)


def budget(adapter: str | None, slot: str, project: str | Path | None = None) -> int | None:
    """This project's budget for that axis. `None` when unset — no ceiling."""

    raw = slots_for(adapter, project).get(slot)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def first_sentence(body: str) -> str:
    """The rule paragraph's opening sentence, without the `Rule.` word."""

    words = " ".join(rule_paragraph(body).split()[1:])
    return re.split(r"(?<=\.)\s", words, maxsplit=1)[0]


def title_of(body: str, path: Path) -> str:
    return next((x[2:].strip() for x in body.splitlines() if x.startswith("# ")), path.stem)


def shrink(body: str, path: Path, severity: str, hard: bool) -> str:
    """Shorten the full text. Never remove it.

    `hard` leaves a title and a path, otherwise the rule paragraph survives.
    Either way the fact that this page matched, and where to open it, are
    still there — which is the whole difference from dropping it.
    """

    head = f"<!-- wiki:{label(path)} ({severity}, shortened) -->\n# {title_of(body, path)}"
    rule = "" if hard else rule_paragraph(body)
    return head + (f"\n\n{rule}" if rule else "") + f"\n\nFull page: `{label(path)}.md`"


def repeated(body: str, path: Path, severity: str, seen: bool = True) -> str:
    """What a page declaring `repeat: rule` carries when not in full.

    The title, the rule paragraph whole, and the path. The declaration says
    every clause that must hold on every turn sits inside that paragraph. A
    one-sentence form was weighed and dropped in the plan's first review
    round — it lost exactly those clauses.

    Two occasions. The session has already seen the page in full, or this
    turn is too large for the host to show whole (`compose`). The tail says
    which, because "loaded earlier" would be false on the second.
    """

    tail = (f"Loaded in full earlier this session: `{label(path)}.md`" if seen else
            f"Full page, left out because this turn is over the host's ceiling: `{label(path)}.md`")
    return (
        f"<!-- wiki:{label(path)} ({severity}, {'repeated' if seen else 'rule only'}) -->\n"
        f"# {title_of(body, path)}\n\n{rule_paragraph(body)}\n\n{tail}"
    )


def whole(severity: str, body: str, path: Path) -> str:
    return f"<!-- wiki:{label(path)} ({severity}) -->\n{body}"


def sent_whole(rules: list, parts: list[str]) -> list[list[str]]:
    """`[name, tag]` of each page that went out in full — tagged after the
    slots were filled and the text translated, so it is what actually left."""

    return [[label(p), tag(b)] for (s, b, p), part in zip(rules, parts)
            if part == whole(s, b, p)]


def tag(text: str) -> str:
    """A short fingerprint. Recorded in place of the text it stands for."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def rule_index(rules: list) -> str:
    """One sentence per loaded rule, meant to sit near the top of the injection.

    A host that receives more than about 12 KB stores the injection in a file
    and gives the session only the first 2 KB of it. With a repository's
    28,000-character `plan-active` in the mix, that happens on most turns.
    Measured on 2026-09-23 in ai-nara-shop: two turns sent 42 KB and 35 KB,
    and the session's preview ended partway through the first rule. Every
    rule after that one was never shown to the session. The full pages still
    go out below this index. The index only makes sure each rule's opening
    sentence is inside the part the host keeps.

    A page with no `Rule.` paragraph, which is repository knowledge, is left
    out of the index. With a known ceiling it rides only on a turn still over
    it — see `compose`.
    """

    lines = [f"- `{label(path)}` — {first_sentence(body)}"
             for _s, body, path in rules if rule_paragraph(body)]
    if not lines:
        return ""
    return (
        "<!-- wiki:rule-index -->\n"
        "Rules loaded this turn, one sentence each. The full pages follow below.\n"
        + "\n".join(lines)
    )


def fit(parts: list[str], rules: list, limit: int | None) -> tuple[list[str], int]:
    """Trim to the budget. Over it, still nothing is thrown away.

    Lowest severity first, down to the rule paragraph, then to the title
    alone — but only for a page that has no rule paragraph. The paragraph is
    the floor, the same one `repeated` stands on: below it the clauses that
    hold on every turn are gone. So the budget can be exceeded, and
    `trigger_audit` already calls it a target rather than a ceiling.
    With no budget this does nothing, which is the default.
    """

    if not limit or sum(len(p) for p in parts) <= limit:
        return parts, 0

    trimmed = 0
    for hard in (False, True):
        for i in range(len(rules) - 1, -1, -1):
            if sum(len(p) for p in parts) <= limit:
                return parts, trimmed
            severity, body, path = rules[i]
            if hard and rule_paragraph(body):
                continue
            small = shrink(body, path, severity, hard)
            if len(small) < len(parts[i]):
                parts[i] = small
                trimmed += 1
    return parts, trimmed


def digest(body: str, path: Path) -> str:
    """Reduce a decision record to two lines.

    The full text must not go in. One repository holds 88 of them at about
    700 characters each, so three matches alone push the rules out. Carrying
    them whole was measured: the heaviest turn reached 13,241 characters, over
    the ceiling, at a 67% hit rate — and this wiki's own standard is that past
    40% you are carrying everything, which reads the same as carrying nothing.

    What is needed at injection time is "this was already decided, and here is
    why", not the record. The record is at the end of the path.
    """

    title = next((x[2:].strip() for x in body.splitlines() if x.startswith("# ")), path.stem)
    # Both spellings, for the same reason `shrink` takes both. The body is
    # translated before this runs, so a parser that only knows `왜.` finds
    # nothing and the agent gets a decision title with no reason under it —
    # which reads as a decision made for no reason.
    why = next(
        (x.split(".", 1)[1].strip() for x in body.splitlines()
         if x.startswith(("왜.", "Why."))),
        "",
    )
    head = re.split(r"(?<=다\.)\s", why, maxsplit=1)[0][:180] if why else ""
    return f"- {title}\n  {head}\n  Full record: `.wiki/decisions/{path.stem}.md`"


def knowledge(decisions: list, limit: int | None) -> list[str]:
    """The decision-record block. A different budget from the rules, on purpose.

    Knowledge must not eat the rules' place. A rule broken because it was
    never carried is the failure this wiki exists to prevent, and knowledge
    must not be what creates it.

    Over the budget, full texts drop to names one at a time. Nothing vanishes
    here either: what matched stays, and so does where to open it.
    """

    if not decisions:
        return []

    keep = MAX_DECISIONS
    while True:
        briefs = [digest(b, p) for _s, b, p in decisions[:keep]]
        rest = [p.stem for _s, _b, p in decisions[keep:]]
        block = (
            "<!-- wiki:decisions -->\n"
            "This has been decided before. Read the reason before reversing it."
        )
        if briefs:
            block += "\n\n" + "\n".join(briefs)
        if rest:
            more = " more" if briefs else ""
            block += (
                f"\n\n{len(rest)}{more} decision(s) on this: "
                + ", ".join(f"`{n}`" for n in rest[:8])
                + (" …" if len(rest) > 8 else "")
            )
        if limit is None or len(block) <= limit or keep == 0:
            return [block]
        keep -= 1


def label(path: Path) -> str:
    """What a page is called: `scope/name` in the shared wiki, `.wiki/name` in a project."""

    if path.parent.name == "decisions":
        return f".wiki/decisions/{path.stem}"
    if path.parent.name == ".wiki":
        return f".wiki/{path.stem}"
    return f"{path.parent.name}/{path.stem}"


def source_map(matched: list, project: str | None) -> str:
    """Which repository the injected pages came from, written as absolute paths.

    Without this line a session read "record it in the wiki" as the current
    repository's `.wiki/`. Most of the injected pages had come from the hub,
    the header said "this repository's wiki", and the hub's path appeared
    nowhere. A name cannot decide it — both places are called "the wiki".

    Which scope holds what is stated alongside it. `operator` and `craft`
    name no repository, so they live in the hub; a repository's gates,
    launchers, ports and invariants live in that repository's `.wiki/`.
    """

    hub = Path(__file__).resolve().parents[1]
    from_hub = sorted(
        {label(p) for _s, _b, p in matched if not str(label(p)).startswith(".wiki/")}
    )
    from_repo = sorted(
        {label(p) for _s, _b, p in matched if str(label(p)).startswith(".wiki/")}
    )

    lines = ["**Where these came from.** Two places. Decide here which one to edit."]
    lines.append(f"- Hub wiki `{hub}` — `operator/` `craft/`. Rules that name no repo")
    if project:
        repo_wiki = Path(project).expanduser() / ".wiki"
        lines.append(f"- This repo `{repo_wiki}` — gates, launchers, ports, invariants")
    else:
        lines.append("- The target repo's `.wiki/` — gates, launchers, ports, invariants")
    if from_hub:
        lines.append(f"- From the hub this time: {', '.join(from_hub)}")
    if from_repo:
        lines.append(f"- From this repo this time: {', '.join(from_repo)}")
    return "\n".join(lines)


def adapter_path(adapter=None, project=None, *, wiki=None) -> Path | None:
    """The checkout's own file first. Only an older install with none falls back
    to looking the name up in the hub."""
    if project:
        local = Path(project).expanduser().resolve() / ".wiki/adapter.toml"
        if local.exists():
            return local
    return (wiki or WIKI) / "adapters" / f"{adapter}.toml" if adapter else None


def slots_for(adapter: str | None, project: str | Path | None = None) -> dict[str, str]:
    """The chosen checkout's slot values. No adapter means an empty table."""

    path = adapter_path(adapter, project)
    if path is None or not path.exists():
        return {}
    import tomllib

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {k: str(v) for k, v in (data.get("slots") or {}).items()}


def fill(body: str, values: dict[str, str]) -> str:
    """Replace `{slot}` and nothing else.

    `str.format` would also reach a trigger's `{0,10}` and every brace in a
    code block. Only known names are swapped; an unknown one is left standing,
    and `apply` points at whatever is still unfilled.
    """

    return SLOT.sub(lambda m: values.get(m.group(1), m.group(0)), body)


def project_wiki(project: str | Path | None) -> Path | None:
    """The target repository's `.wiki/`, or `None`."""

    if not project:
        return None
    directory = Path(project).expanduser() / ".wiki"
    return directory if directory.is_dir() else None


def pages(
    adapter: str | None = None,
    project: str | Path | None = None,
) -> list[tuple[dict[str, object], str, Path]]:
    """The shared wiki's rules plus that project's knowledge.

    Project pages include `decisions/`. There are many of those — 90 in one
    repository — so carrying them all would blow the budget, and the selecting
    side keeps a few. This function only reads.
    """

    values = slots_for(adapter, project)
    found = []
    for scope in ("operator", "craft"):
        directory = WIKI / scope
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            meta, body = front_matter(path.read_text(encoding="utf-8"))
            found.append((meta, fill(body, values) if values else body, path))

    local = project_wiki(project)
    if local:
        for path in sorted(local.glob("*.md")) + sorted(local.glob("decisions/*.md")):
            meta, body = front_matter(path.read_text(encoding="utf-8"))
            found.append((meta, fill(body, values) if values else body, path))
    return found


def match_pages(prompt: str, available: list) -> list:
    """Injection and the audit share one severity and regex judgement."""
    matched = []
    for meta, body, path in available:
        severity = str(meta.get("severity") or "")
        triggers = meta.get("triggers")
        if severity not in INJECTABLE or not isinstance(triggers, list):
            continue
        for pattern in triggers:
            try:
                if re.search(str(pattern), prompt, re.IGNORECASE):
                    matched.append((severity, body, path))
                    break
            except re.error:
                continue
    return matched


def render_parts(matched: list, rule_limit: int | None, repo_limit: int | None,
                 seen: set = frozenset(), repeatable: set = frozenset(),
                 squeeze: bool = False) -> tuple:
    """The two axes as actually sent. The audit counts the same thing — slots
    filled, summaries, the name list — rather than a tidier version of it.

    `seen` holds `(name, tag(body))` for pages this session already received
    in full; `repeatable` the names that declare `repeat: rule`. A page in
    both goes out as `repeated`. The key carries the body's tag, so a page
    edited mid-session is not seen and its new text goes out once in full.
    `squeeze` sends every declaring page as its rule paragraph — see `compose`.
    """
    decisions = sorted(
        (m for m in matched if m[2].parent.name == "decisions"),
        key=lambda m: m[2].name, reverse=True,
    )
    rules = [m for m in matched if m[2].parent.name != "decisions"]
    rules.sort(key=lambda item: 0 if item[0] == "landmine" else 1)
    parts = []
    for s, b, p in rules:
        known = (label(p), tag(b)) in seen
        if label(p) in repeatable and (known or squeeze) and rule_paragraph(b):
            parts.append(repeated(b, p, s, seen=known))
        else:
            parts.append(whole(s, b, p))
    parts, trimmed = fit(parts, rules, rule_limit)
    return rules, decisions, parts, knowledge(decisions, repo_limit), trimmed


def localised(matched: list, deadline: float) -> list:
    """Translate the repo's own pages before anything is measured.

    Only `.wiki/` pages. The hub's `operator/` and `craft/` prose is rewritten
    in English at the source in stage 2, so translating it here would pay for
    the same words twice and throw the second copy away.

    Runs before `render_parts`, which is the part that matters. Translating
    afterwards saved a few tokens on pages the budget would have shortened, and
    cost correctness everywhere else: `fit` had already trimmed to the Korean
    length, and English is usually longer, so a block could come back over the
    budget it was just fitted to — and `trajectory.cost` recorded the number
    from before, which `trigger_audit` reads as the size of what was injected.
    """

    mine = [i for i, (_s, _b, path) in enumerate(matched)
            if str(label(path)).startswith(".wiki/")]
    if not mine:
        return matched
    done = translate.translate(
        [matched[i][1] for i in mine], translate.KO_EN, deadline
    )
    out = list(matched)
    for body, i in zip(done, mine):
        severity, _was, path = out[i]
        out[i] = (severity, body, path)
    return out


def rendering(prompt: str, deadline: float | None = None) -> str:
    """The English rendering of the utterance, or `""` if there is none.

    **This must run after `match_pages`, never before.** Triggers are Korean
    regexes held against what the person actually typed. Hand `match_pages` a
    translation and nothing matches, and nothing matching is indistinguishable
    from nothing applying — the injection disappears without a word.

    `craft/hooks-fail-open` names that shape: not running is bad, believing it
    ran is worse.
    """

    if not HANGUL.search(prompt) or len(prompt) > MAX_RENDERED:
        # A long utterance is usually pasted material, and the rendering would
        # double it in a context that already holds the original. Skipping
        # beats truncating: half a translation reads as a whole one.
        return ""
    english = translate.ko_to_en(prompt, deadline)
    if english == prompt:
        # Unchanged means the translation failed. Labelling the Korean as an
        # English rendering would be a lie the reader cannot check.
        return ""
    return RENDERING + english


def repeatable(available: list) -> set[str]:
    """The pages that declared `repeat: rule`. Any other page goes out in full
    on every turn — the default is the safe side."""

    return {label(p) for meta, _b, p in available if meta.get("repeat") == "rule"}


def remembered(rows: list[dict], limit: int) -> set[tuple[str, str]]:
    """What this session has seen in full, read off its own rows.

    A page counts as seen when it went out in full, on a turn whose `sent`
    was within the host's ceiling, after the last compact. Past the ceiling
    the host put the injection in a file and showed a 2 KB preview, so the
    full text on that turn was never read. A row with no `sent` — written
    before this existed — counts for nothing.
    """

    seen: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("reset"):
            seen = set()
        sent = row.get("sent")
        if isinstance(sent, int) and sent <= limit:
            seen |= {tuple(x) for x in row.get("full") or [] if len(x) == 2}
    return seen


def compacted(previous: dict | None, transcript: Path, txp: str, size: int) -> bool:
    """Did the transcript compact since this session's previous turn?

    Only what was appended since then is read, so a transcript of tens of MB
    costs what one turn added. A different path, a transcript that shrank or
    a previous row with no offset all count as a compact: `/clear` and
    `--resume` land here, and so does anything this cannot explain.

    The previous row is this session's, not the file's last line. Two
    sessions write one trajectory in turns, and another session's larger
    offset would skip this one's compact — `trajectory.last_row` does not
    tell sessions apart, so it is not used here.
    """

    if previous is None:
        return False
    start = previous.get("tx")
    if previous.get("txp") != txp or not isinstance(start, int) or size < start:
        return True
    with transcript.open("rb") as handle:
        handle.seek(start)
        # Read once. Reading inside the loop handed every marker after the
        # first an exhausted stream, and Codex's compact was never seen.
        tail = handle.read()
    return any(marker in tail for marker in COMPACTED)


def recall(wiki: Path | None, session: str, transcript, host: str | None) -> tuple[set, dict]:
    """`(seen, fields)` — what this session already holds, and what to record.

    Anything missing or failing means nothing is seen and every page goes
    out in full, as it did before this existed. Wrong in that direction
    costs tokens. The other direction — counting as seen what was never read
    — is the failure this wiki exists to prevent, `craft/hooks-fail-open`.
    """

    limit = LIMIT.get(host or "")
    if wiki is None or not session or not transcript or limit is None:
        return set(), {}
    try:
        path = Path(str(transcript))
        size = path.stat().st_size
        # The path's tag, not the path: it holds a user name and a project.
        txp = tag(str(path))
        mine = trajectory.session_rows(trajectory.path_for(wiki), session)
        if compacted(mine[-1] if mine else None, path, txp, size):
            return set(), {"tx": size, "txp": txp, "reset": True}
        return remembered(mine, limit), {"tx": size, "txp": txp}
    except Exception:  # noqa: BLE001
        return set(), {}


def suggest(prompt: str, english: str, project: str | None, available: list,
            taken: set[str]) -> list[tuple[str, str]]:
    """`(name, first sentence)` for up to `SUGGEST_K` pages the regex missed.

    The query is the utterance and its English rendering: the hub's pages are
    English, a repository's are Korean. A page already chosen by the regex, or
    already seen in full this session, is not suggested again. Anything short
    of an answer — no daemon, a timeout, a stranger on the port — is no
    suggestion and nothing on screen (`craft/hooks-fail-open`).
    """

    if SUGGEST_MIN is None:
        return []
    import search

    found = search.ask(f"{prompt}\n{english[len(RENDERING):]}", project, "hook",
                       SEARCH_TIMEOUT, k=12)
    if not found:
        return []
    by_name = {label(p): (b, p) for _m, b, p in available}
    out = []
    for hit in sorted(found, key=lambda h: h.get(SUGGEST_BY) or 0, reverse=True):
        score = hit.get(SUGGEST_BY)
        name = label(Path(str(hit.get("path"))))
        if not isinstance(score, (int, float)) or score < SUGGEST_MIN:
            break
        if name in taken or name not in by_name:
            continue
        body, path = by_name[name]
        out.append((name, first_sentence(body) or title_of(body, path)))
        if len(out) == SUGGEST_K:
            break
    return out


def hint(found: list[tuple[str, str]]) -> str:
    """One line and a path per suggestion. Never the page itself."""

    if not found:
        return ""
    return (
        "<!-- wiki:suggested -->\n"
        "Possibly relevant, by similarity rather than a trigger. Open the page if it applies.\n"
        + "\n".join(f"- `{name}` — {line} (`{name}.md`)" for name, line in found)
    )


def compose(matched: list, limits: tuple, english: str, project: str | None,
            seen: set, repeat: set, limit: int | None, suggested: str = "") -> tuple:
    """`render_parts` and `assemble` together, fitted to the host's ceiling.

    Past the ceiling the host puts the whole injection in a file and shows the
    session a 2 KB preview, so a full page sent on that turn is not read — it
    only pushes everything behind it out of view. On such a turn every page
    that declared `repeat: rule` goes as its rule paragraph, seen or not: the
    declaration says the binding clauses are all there, and the rest was not
    going to be read. Pages that did not declare it still go in full.

    Chosen by the user on 2026-09-25 over the plan's "full text first". Claude's
    ceiling turned out to be about 10,000 characters and an ordinary turn in
    this repository was 10,292 bytes, so under "full first" no page was ever
    seen on Claude and deduplication saved 7% here, 0% in ai-nara-shop.

    The rule index rides only on a turn that is still over the ceiling. It
    exists for the 2 KB preview, and a turn under the ceiling has none — there
    it was a second copy of every paragraph's first sentence, about 1 KB a
    turn. Dropping it there took this repository's replay from 57% to 59%,
    and more turns now fit with their full pages. The user chose that on
    2026-09-25, over PR #20's "index on every turn".
    With no known ceiling the index stays, as before.

    Returns `render_parts`'s five, the body, and whether it was squeezed.
    """

    def fits(body: str) -> bool:
        return limit is not None and len(body.encode("utf-8")) <= limit

    out = render_parts(matched, *limits, seen, repeat)
    body = assemble(out[0], out[2] + out[3], english, project, index=False, suggested=suggested)
    if fits(body):
        return (*out, body, False)
    squeezed = limit is not None
    if squeezed:
        out = render_parts(matched, *limits, seen, repeat, squeeze=True)
        body = assemble(out[0], out[2] + out[3], english, project, index=False, suggested=suggested)
        if fits(body):
            return (*out, body, True)
    return (*out, assemble(out[0], out[2] + out[3], english, project, suggested=suggested), squeezed)


def assemble(rules: list, parts: list[str], english: str, project: str | None,
             index: bool = True, suggested: str = "") -> str:
    """The whole `additionalContext`, or `""` when there is nothing to send."""

    if not parts and not english and not suggested:
        return ""
    # The rule index goes first. It is a few hundred characters, and the
    # rendering in front of it could reach 4,000 (`MAX_RENDERED`) and push
    # every rule sentence out of the 2 KB preview. See `rule_index`.
    blocks = []
    listing = rule_index(rules) if index else ""
    if listing:
        blocks.append(listing)
    # Before the pages, not after them. The rendering is carried even when no
    # page matched: the utterance is agent input on every turn, and tying it
    # to a trigger would drop it on exactly the turns no rule covers.
    #
    # Position is the other half of that. A host persists an injection past
    # about 12 KB and hands the session a 2 KB preview instead; the rules
    # alone reach 12,205 characters on an ordinary turn, so anything after
    # them is cut. Measured on 2026-09-22 in a web chat session: the rules
    # arrived, this block did not, and nothing said so. Behind the short
    # index it still starts inside the preview.
    if english:
        blocks.append(english)
    # Two lines at most, so it goes where the 2 KB preview still reaches.
    if suggested:
        blocks.append(suggested)
    # The header and the source map stay on a turn where every rule was
    # already seen. They are a few hundred characters, and a branch that
    # drops them is a branch that can drop the repeated forms with them.
    if parts:
        blocks.append(
            "Below is what the wiki loaded for this utterance. A rule marks a "
            "place where something actually went wrong before; knowledge is "
            "something already decided.\n\n"
            + source_map(rules, project)
            + "\n\n"
            + "\n\n---\n\n".join(parts)
        )
    return "\n\n---\n\n".join(blocks)


def main() -> int:
    # The utterance coming in and the injection going out are both Korean. The
    # encoding is not left to the environment.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="발화에 맞는 위키 페이지를 넣는다")
    parser.add_argument("--adapter", default=None, help="adapters/<이름>.toml")
    parser.add_argument("--project", default=None, help="대상 저장소. `.wiki/` 를 읽는다")
    parser.add_argument("--host", default=None, help="claude|codex. 없으면 세션 내 중복 제거를 안 한다")
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
    if not prompt:
        return 0

    # Triggers are matched on the Korean the person typed, then the bodies are
    # translated, then everything downstream measures the English that will
    # actually go out. One deadline covers this and the utterance rendering,
    # so the hook's budget bounds the pair rather than each separately.
    #
    # The utterance is translated before the pages. It is a few hundred
    # characters; a repository page can be 28,000 — ai-nara-shop's
    # `plan-active` on 2026-09-23 held the request past the whole deadline,
    # and the rendering behind it got zero seconds and was dropped. The block
    # the person checks goes first; the pages take what is left.
    deadline = time.monotonic() + BUDGET
    available = pages(args.adapter, args.project)
    matched = match_pages(prompt, available)
    english = rendering(prompt, deadline)
    matched = localised(matched, deadline)
    # Unlike reading, writing has to work before `.wiki/` exists.
    # `project_wiki` returns `None` when it does not, which would leave a
    # freshly attached repository silently recording nothing at all.
    wiki = Path(args.project).expanduser() / ".wiki" if args.project else None
    session = str(payload.get("session_id") or "")
    seen, where = recall(wiki, session, payload.get("transcript_path"), args.host)
    limits = (budget(args.adapter, RULE_BUDGET, args.project),
              budget(args.adapter, REPO_BUDGET, args.project))
    # After the regex and the rendering, never in their place: the names the
    # regex chose are the same with or without the daemon.
    suggested = suggest(prompt, english, args.project, available,
                        {label(p) for _s, _b, p in matched} | {name for name, _t in seen})
    # Without a host the ceiling is unknown, so nothing is squeezed either.
    rules, decisions, rule_parts, repo_parts, trimmed, body, _squeezed = compose(
        matched, limits, english, args.project, seen, repeatable(available),
        LIMIT.get(args.host or ""), hint(suggested),
    )
    parts = rule_parts + repo_parts

    # Repository documents are not selected here. The whole listing goes in
    # once at session start and the choosing is done by whoever already holds
    # it — `tool/session_state.py`.

    loaded = [label(p) for _s, _b, p in rules + decisions]
    if body:
        # This one line lands on the person's screen as written. The rule
        # inverted and this stayed Korean, because the reader here is the
        # person. `operator/english-progress` holds that boundary.
        note = f"위키 주입: {', '.join(loaded[:6])}" if loaded else "위키: 걸린 규칙 없음"
        heads = [part.split("\n", 1)[0] for part in rule_parts]
        again = sum(", repeated) -->" in head for head in heads)
        squeezed = sum(", rule only) -->" in head for head in heads)
        if again:
            note += f" · 이미 실림 {again}장"
        if squeezed:
            note += f" · 한도로 규칙 문단만 {squeezed}장"
        if trimmed:
            note += f" · 줄임 {trimmed}장"
        if suggested:
            note += f" · 유사도 제안 {len(suggested)}장"
        if english:
            note += " · 영어본 첨부"
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": body,
                },
                "systemMessage": note,
            },
            sys.stdout,
            ensure_ascii=False,
        )
        sys.stdout.flush()

    # Recorded last, after the output is out. Recorded first, a turn that
    # died building the body or writing stdout still left `full` behind, and
    # the next turn counted pages that never arrived as seen. A record that
    # fails leaves no `full`, so the next turn sends the pages in full again.
    #
    # A turn that matched nothing is recorded too. What was not carried is as
    # much evidence about routing as what was, and reading only the utterances
    # that matched nothing is the one way to find a miss.
    failed = trajectory.record(
        wiki,
        prompt,
        loaded,
        sum(len(part) for part in parts),
        session,
        # The whole `additionalContext` in UTF-8 bytes — index, rendering,
        # source map and separators included. `cost` counts only the rule and
        # decision blocks; this is the number a host ceiling is compared with.
        sent=len(body.encode("utf-8")),
        full=sent_whole(rules, rule_parts),
        # Apart from `injected` and `full`: a suggestion is a line, not a page.
        suggested=[name for name, _line in suggested],
        **where,
    )
    if failed:
        # The name and nothing else. Non-ASCII in the message kills this very
        # stderr write under a cp949 console, which is how the report of a
        # failure became a second failure.
        print(f"trajectory skipped: {failed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # Whatever happens, a hook does not stop the session. Leave the name of
    # what went wrong and pass.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
