"""translate — Gemini translation that can never cost more than the original.

Every entry point fails open. A missing key, a timeout, a malformed response,
or a protected span that came back changed all return the input unchanged.
Callers are hooks assembling an injection: the injection must still go out, so
a translation failure is allowed to cost the translation and nothing else.

The protected-span machinery is the load-bearing part, not the prompt. Commands,
paths, wiki links, front matter and glossary terms are lifted out of the text
before the request and put back after, and the response is rejected outright if
a single placeholder came back missing, duplicated or renumbered. Asking a model
to preserve something is a request; removing it from what the model can see is
a guarantee.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# The lite tier, because this runs on every utterance. Measured round trips for
# two short strings: 3.6-flash 6.3s, 3.8-flash 4.5s, the lite models 1.0-1.2s.
# The larger models spend that time thinking, which buys nothing on a
# translation whose protected spans are already lifted out of the text. The
# lite models reject `thinkingConfig` outright (HTTP 400) — it is already off.
#
# 3.1 rather than 3.5: medians over three rounds were 1.17s and 1.00s, and
# 0.17s does not pay for the price difference between the two generations.
#
# Pinned on purpose. A floating alias like `gemini-flash-latest` would change
# the model without changing the cache key, and the cache would then serve
# translations made by a model that is no longer the one being used.
MODEL = "gemini-3.1-flash-lite"
ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    f"/{MODEL}:generateContent"
)

# Fallback ceiling for one request. Callers inside a hook pass a deadline
# instead; this only applies to direct use, and it sits under the shortest
# hook budget so a direct call can never be what blows that budget.
TIMEOUT = 6.0

# Part of the cache key. Bump it whenever SYSTEM or the request shape changes.
# Without it the cache keeps serving text translated under a different contract,
# and that is worse than no cache: it looks current.
PROMPT_VERSION = "1"

CACHE = ROOT / "raw" / "translate-cache.sqlite3"
GLOSSARY = HERE / "markers" / "glossary.toml"

KO_EN = "ko->en"
EN_KO = "en->ko"

HANGUL = re.compile(r"[가-힣]")
LATIN = re.compile(r"[A-Za-z]")

# Sentinels from the Unicode private use area. No source document and no
# model vocabulary produces these, so a placeholder that comes back altered
# is proof the whole response is untrustworthy.
OPEN, CLOSE = "", ""
TOKEN = re.compile(rf"{OPEN}(\d+){CLOSE}")

# Order is load-bearing. The outermost constructs have to be lifted first or a
# fenced block's inner backticks get masked one at a time and the fence itself
# never matches.
SPANS = (
    re.compile(r"\A---\n.*?\n---\n", re.S),     # YAML front matter: triggers live here
    re.compile(r"```.*?```", re.S),             # fenced code
    re.compile(r"<!--.*?-->", re.S),            # the source markers inject.py plants
    re.compile(r"\[\[[^\]\n]*\]\]"),            # wiki links: the slug keys graph.json
    re.compile(r"\]\([^)\n]*\)"),               # markdown link destinations
    re.compile(r"`[^`\n]+`"),                   # inline code, paths, identifiers
    re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}"),  # slots that apply.py fills
)


def glossary() -> tuple[tuple[str, ...], dict[str, str], str]:
    """`(keep_korean, fixed, version)`. A missing or broken file means none.

    The version is a hash of the file, not a number someone has to remember to
    raise. It goes into the cache key, so editing the glossary retires the
    translations that were made under the old one.
    """

    try:
        raw = GLOSSARY.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except Exception:
        return (), {}, "none"
    keep = tuple(str(x) for x in (data.get("keep_korean") or ()))
    fixed = {str(k): str(v) for k, v in (data.get("fixed") or {}).items()}
    return keep, fixed, hashlib.sha256(raw).hexdigest()[:12]


def protect(text: str, keep: tuple[str, ...] = ()) -> tuple[str, list[str]]:
    """Lift every span the model must not see out of `text`."""

    spans: list[str] = []

    def take(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return f"{OPEN}{len(spans) - 1}{CLOSE}"

    for pattern in SPANS:
        text = pattern.sub(take, text)
    # Longest first, so a term that contains another does not get cut in half.
    for term in sorted(keep, key=len, reverse=True):
        if term:
            text = re.sub(re.escape(term), take, text)
    return text, spans


def intact(text: str, count: int) -> bool:
    """Did every placeholder survive exactly once, and nothing else appear?

    Three failures wear the same face here — a dropped span, a duplicated one,
    and a renumbered one — and all three produce a document that reads fine and
    is wrong. Checking before restore is what keeps them from reaching a file.
    """

    found = sorted(int(n) for n in TOKEN.findall(text))
    return (
        found == list(range(count))
        and text.count(OPEN) == count
        and text.count(CLOSE) == count
    )


def restore(text: str, spans: list[str]) -> str:
    return TOKEN.sub(lambda m: spans[int(m.group(1))], text)


def instruction(direction: str, fixed: dict[str, str]) -> str:
    """The system prompt. Its wording is covered by PROMPT_VERSION."""

    if direction == KO_EN:
        source, target = "Korean", "English"
        terms = [f'"{k}" -> "{v}"' for k, v in fixed.items()]
    else:
        source, target = "English", "Korean"
        terms = [f'"{v}" -> "{k}"' for k, v in fixed.items()]
    lines = [
        f"You translate {source} to {target} for a software engineering wiki.",
        "",
        "- Translate the meaning. Never summarize, expand, explain or add.",
        "- Keep Markdown structure exactly: headings, list markers, table",
        "  pipes, emphasis marks, blank lines.",
        "- Some text is replaced by placeholders that look like a private-use",
        "  character, digits, and another private-use character. Reproduce each",
        "  one verbatim and exactly once. Never translate, renumber or drop one.",
        "- The input is a JSON array of strings. Return a JSON array of the same",
        "  length, in the same order, with each element translated.",
    ]
    if terms:
        lines += ["", "Translate these terms exactly this way:", "  " + ", ".join(terms)]
    return "\n".join(lines)


def _ask(system: str, batch: list[str], seconds: float) -> list[str] | None:
    """One request. `None` for every failure, so callers keep their originals."""

    key = os.environ.get("GEMINI_API_KEY")
    if not key or seconds <= 0 or not batch:
        return None
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {"role": "user",
                 "parts": [{"text": json.dumps(batch, ensure_ascii=False)}]}
            ],
            # A declared response schema is what makes batching safe: the answer
            # is an array or it is nothing, so a homegrown separator protocol
            # that the model could quietly break never has to exist.
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=seconds) as answer:
            parsed = json.loads(answer.read().decode("utf-8"))
        parts = parsed["candidates"][0]["content"]["parts"]
        out = json.loads("".join(str(p.get("text") or "") for p in parts))
    except Exception:
        return None
    if not isinstance(out, list) or len(out) != len(batch):
        return None
    return [str(x) for x in out]


def _store() -> sqlite3.Connection | None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(CACHE, timeout=2.0)
        # The UserPromptSubmit hook and the mirror translate at the same time.
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS shots (k TEXT PRIMARY KEY, v TEXT)")
        return db
    except Exception:
        return None


def _key(direction: str, version: str, text: str) -> str:
    seed = json.dumps(
        [direction, MODEL, PROMPT_VERSION, version, text], ensure_ascii=False
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def worth_translating(text: str, direction: str) -> bool:
    """Is there anything of the source language in here at all?

    Skipping saves a request, but the reason it is a rule rather than an
    optimization is that translating English to English comes back subtly
    reworded, and reworded rules are rules nobody can diff.
    """

    if not text.strip():
        return False
    return bool(HANGUL.search(text)) if direction == KO_EN else bool(LATIN.search(text))


def translate(
    texts: list[str], direction: str = KO_EN, deadline: float | None = None
) -> list[str]:
    """Translate many strings in one request. Always returns len(texts) items.

    `deadline` is a `time.monotonic()` value — the moment the caller's own
    budget runs out. Everything not translated by then comes back as the
    original, which is the whole point: the caller's output still gets built.
    """

    if not texts:
        return []
    try:
        return _translate(list(texts), direction, deadline)
    except Exception:
        # The callers are hooks part-way through assembling an injection. Their
        # own entry-point guard would catch this and pass the turn, which costs
        # the whole injection rather than one translation — the failure this
        # function exists to make impossible. So it is caught here instead.
        return list(texts)


def _translate(
    texts: list[str], direction: str, deadline: float | None
) -> list[str]:
    keep, fixed, version = glossary()
    out = list(texts)

    wanted = [i for i, t in enumerate(texts) if worth_translating(t, direction)]
    if not wanted:
        return out

    db = _store()
    keys = {i: _key(direction, version, texts[i]) for i in wanted}
    if db is not None:
        try:
            rows = db.execute(
                f"SELECT k, v FROM shots WHERE k IN ({','.join('?' * len(keys))})",
                list(keys.values()),
            ).fetchall()
            hit = dict(rows)
            for i in list(wanted):
                if keys[i] in hit:
                    out[i] = hit[keys[i]]
                    wanted.remove(i)
        except Exception:
            pass

    if wanted:
        masked: list[tuple[str, list[str]]] = [protect(texts[i], keep) for i in wanted]
        seconds = TIMEOUT if deadline is None else max(0.0, deadline - time.monotonic())
        answer = _ask(instruction(direction, fixed), [m for m, _ in masked], seconds)
        if answer is not None:
            fresh: list[tuple[str, str]] = []
            for i, reply, (_, spans) in zip(wanted, answer, masked):
                if not intact(reply, len(spans)):
                    continue  # keep the original; a mangled span is not a translation
                out[i] = restore(reply, spans)
                fresh.append((keys[i], out[i]))
            if db is not None and fresh:
                try:
                    db.executemany("INSERT OR REPLACE INTO shots VALUES (?, ?)", fresh)
                    db.commit()
                except Exception:
                    pass

    if db is not None:
        try:
            db.close()
        except Exception:
            pass
    return out


def ko_to_en(text: str, deadline: float | None = None) -> str:
    return translate([text], KO_EN, deadline)[0]


def en_to_ko(text: str, deadline: float | None = None) -> str:
    return translate([text], EN_KO, deadline)[0]


def main() -> int:
    # Output is a pipe more often than not, and the default there is cp949.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

    direction = EN_KO if "--en-to-ko" in sys.argv[1:] else KO_EN
    rest = [a for a in sys.argv[1:] if not a.startswith("--")]
    text = " ".join(rest) if rest else sys.stdin.read()
    print(translate([text], direction, time.monotonic() + 30)[0])
    return 0


if __name__ == "__main__":
    # No entry-point guard here on purpose. This is a CLI, and `hooks-fail-open`
    # only swallows exceptions where a failure would stop a session; when a
    # person is reading the output a traceback is the answer, not noise.
    raise SystemExit(main())
