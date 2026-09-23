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
import json
import re
import sys
import time
from pathlib import Path

import trajectory
import translate
from wikilib import WIKI, front_matter

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

# How many decision records go in as full text in one turn. What is over that
# is not dropped; its name stays.
MAX_DECISIONS = 3


def budget(adapter: str | None, slot: str, project: str | Path | None = None) -> int | None:
    """This project's budget for that axis. `None` when unset — no ceiling."""

    raw = slots_for(adapter, project).get(slot)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def shrink(body: str, path: Path, severity: str, hard: bool) -> str:
    """Shorten the full text. Never remove it.

    `hard` leaves a title and a path, otherwise the rule paragraph survives.
    Either way the fact that this page matched, and where to open it, are
    still there — which is the whole difference from dropping it.
    """

    title = next((x[2:].strip() for x in body.splitlines() if x.startswith("# ")), path.stem)
    head = f"<!-- wiki:{label(path)} ({severity}, shortened) -->\n# {title}"
    if hard:
        return head + f"\n\nFull page: `{label(path)}.md`"
    # Both spellings. Page bodies turn English in stage 2, and a shrink that
    # only knows `규칙.` would leave the title with no rule under it exactly
    # when the budget is tight -- the turn where the rule matters most.
    rule = next(
        (x for x in body.splitlines() if x.startswith(("규칙.", "Rule."))), ""
    )
    return head + (f"\n\n{rule}" if rule else "") + f"\n\nFull page: `{label(path)}.md`"


def fit(parts: list[str], rules: list, limit: int | None) -> tuple[list[str], int]:
    """Trim to the budget. Over it, still nothing is thrown away.

    Lowest severity first, down to the one rule line, then to the title alone.
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


def render_parts(matched: list, rule_limit: int | None, repo_limit: int | None) -> tuple:
    """The two axes as actually sent. The audit counts the same thing — slots
    filled, summaries, the name list — rather than a tidier version of it."""
    decisions = sorted(
        (m for m in matched if m[2].parent.name == "decisions"),
        key=lambda m: m[2].name, reverse=True,
    )
    rules = [m for m in matched if m[2].parent.name != "decisions"]
    rules.sort(key=lambda item: 0 if item[0] == "landmine" else 1)
    parts = [f"<!-- wiki:{label(p)} ({s}) -->\n{b}" for s, b, p in rules]
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
    return (
        "<!-- wiki:english-rendering -->\n"
        "English rendering of the user's message (Gemini). The Korean above is "
        "authoritative — go back to it wherever this reads oddly.\n\n" + english
    )


def main() -> int:
    # The utterance coming in and the injection going out are both Korean. The
    # encoding is not left to the environment.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="발화에 맞는 위키 페이지를 넣는다")
    parser.add_argument("--adapter", default=None, help="adapters/<이름>.toml")
    parser.add_argument("--project", default=None, help="대상 저장소. `.wiki/` 를 읽는다")
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
    matched = match_pages(prompt, pages(args.adapter, args.project))
    english = rendering(prompt, deadline)
    matched = localised(matched, deadline)
    rules, decisions, rule_parts, repo_parts, trimmed = render_parts(
        matched, budget(args.adapter, RULE_BUDGET, args.project),
        budget(args.adapter, REPO_BUDGET, args.project),
    )
    parts = rule_parts + repo_parts

    # Repository documents are not selected here. The whole listing goes in
    # once at session start and the choosing is done by whoever already holds
    # it — `tool/session_state.py`.

    loaded = [label(p) for _s, _b, p in rules + decisions]

    # A turn that matched nothing is recorded too. What was not carried is as
    # much evidence about routing as what was, and reading only the utterances
    # that matched nothing is the one way to find a miss.
    #
    # Unlike reading, writing has to work before `.wiki/` exists.
    # `project_wiki` returns `None` when it does not, which would leave a
    # freshly attached repository silently recording nothing at all.
    failed = trajectory.record(
        Path(args.project).expanduser() / ".wiki" if args.project else None,
        prompt,
        loaded,
        sum(len(part) for part in parts),
        str(payload.get("session_id") or ""),
    )
    if failed:
        # The name and nothing else. Non-ASCII in the message kills this very
        # stderr write under a cp949 console, which is how the report of a
        # failure became a second failure.
        print(f"trajectory skipped: {failed}", file=sys.stderr)

    if not parts and not english:
        return 0

    blocks = []
    # First, and not last. Carried even when no page matched — the utterance
    # is agent input on every turn, and tying it to a trigger would drop it on
    # exactly the turns no rule covers.
    #
    # Position is the other half of that. A host persists an injection past
    # about 12 KB and hands the session a 2 KB preview instead; the rules
    # alone reach 12,205 characters on an ordinary turn, so anything after
    # them is cut. Measured on 2026-09-22 in a web chat session: the rules
    # arrived, this block did not, and nothing said so. It is a few hundred
    # characters and it is what the person came to check, so it goes first.
    if english:
        blocks.append(english)
    if parts:
        blocks.append(
            "Below is what the wiki loaded for this utterance. A rule marks a "
            "place where something actually went wrong before; knowledge is "
            "something already decided.\n\n"
            + source_map(rules, args.project)
            + "\n\n"
            + "\n\n---\n\n".join(parts)
        )
    body = "\n\n---\n\n".join(blocks)
    # This one line lands on the person's screen as written. The rule inverted
    # and this stayed Korean, because the reader here is the person.
    # `operator/english-progress` holds that boundary.
    note = f"위키 주입: {', '.join(loaded[:6])}" if loaded else "위키: 걸린 규칙 없음"
    if trimmed:
        note += f" · 줄임 {trimmed}장"
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
