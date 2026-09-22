"""What has to stay true about `translate.py`, and what broke to put it here.

Nothing in this file touches the network. The one thing a live call proved —
that a silent failure reads exactly like a success — is why almost every test
below asserts on the *unchanged* input rather than on a translation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import translate as T  # noqa: E402

TOOL = HERE / "translate.py"

PAGE = (
    "---\n"
    "scope: operator\n"
    'triggers: ["한국어", "진행\\\\s*상황"]\n'
    "links: [hooks-fail-open]\n"
    "---\n"
    "\n"
    "# 사용자 화면에 뜨는 말은 한국어로\n"
    "\n"
    "규칙. `tool/korean_progress.py` 가 `Bash` 의 description 만 본다.\n"
    "자세한 것은 [[hooks-fail-open]] 과 [색인](index.md) 이 든다.\n"
    "나라장터 입찰공고 는 그대로 남는다. 슬롯 {review_dir} 도 마찬가지다.\n"
    "\n"
    '```python\nprint("이 안은 절대 안 바뀐다")\n```\n'
    "<!-- wiki:operator/korean-progress -->\n"
)

# Every substring that must come back byte-identical no matter what the model
# did to the prose around it.
FROZEN = (
    'triggers: ["한국어", "진행\\\\s*상황"]',
    "links: [hooks-fail-open]",
    "`tool/korean_progress.py`",
    "`Bash`",
    "[[hooks-fail-open]]",
    "(index.md)",
    "{review_dir}",
    'print("이 안은 절대 안 바뀐다")',
    "<!-- wiki:operator/korean-progress -->",
    "나라장터",
    "입찰공고",
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read or write the real cache, and never need a real key."""
    monkeypatch.setattr(T, "CACHE", tmp_path / "cache.sqlite3")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")


def _rewrites_all_prose(_system: str, batch: list[str], _seconds: float) -> list[str]:
    """A model that translates aggressively but honours the placeholders."""
    return [re.sub(r"[가-힣]+", "ENGLISH", item) for item in batch]


def test_protected_spans_survive_a_model_that_rewrites_everything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(T, "_ask", _rewrites_all_prose)
    out = T.translate([PAGE], T.KO_EN)[0]

    assert out != PAGE, "the fake model was supposed to change the prose"
    for frozen in FROZEN:
        assert frozen in out, frozen


def test_a_dropped_placeholder_keeps_the_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response missing one span reads fine and is wrong. That is the danger.

    The document would come back with a command or a wiki link silently deleted
    and every other line intact, so nothing downstream would look suspicious.
    """

    def loses_one(_system: str, batch: list[str], _seconds: float) -> list[str]:
        return [T.TOKEN.sub("", item, count=1) for item in batch]

    monkeypatch.setattr(T, "_ask", loses_one)
    assert T.translate([PAGE], T.KO_EN) == [PAGE]


def test_a_duplicated_or_renumbered_placeholder_keeps_the_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def duplicates(_system: str, batch: list[str], _seconds: float) -> list[str]:
        return [item + f"{T.OPEN}0{T.CLOSE}" for item in batch]

    def renumbers(_system: str, batch: list[str], _seconds: float) -> list[str]:
        return [item.replace(f"{T.OPEN}0{T.CLOSE}", f"{T.OPEN}99{T.CLOSE}", 1)
                for item in batch]

    for faulty in (duplicates, renumbers):
        monkeypatch.setattr(T, "_ask", faulty)
        assert T.translate([PAGE], T.KO_EN) == [PAGE], faulty.__name__


def test_a_missing_key_returns_the_input_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert T.ko_to_en("훅이 조용히 죽는다") == "훅이 조용히 죽는다"


def test_a_deadline_already_past_returns_the_input_unchanged() -> None:
    """The caller's budget wins. Its output still has to be assembled."""
    assert T.ko_to_en("훅이 조용히 죽는다", deadline=0.0) == "훅이 조용히 죽는다"


def test_text_without_the_source_language_is_never_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-translating English to English comes back reworded, and a reworded
    rule is a rule nobody can diff."""

    asked: list[list[str]] = []
    monkeypatch.setattr(T, "_ask", lambda _s, batch, _t: asked.append(batch))

    assert T.translate(["pure ascii", "", "   "], T.KO_EN) == ["pure ascii", "", "   "]
    assert asked == [], "a request went out for text with no Korean in it"


def test_anything_that_raises_still_returns_the_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller is a hook mid-injection. Its own entry guard would catch this
    and pass the turn, costing the whole injection instead of one translation."""

    def broken() -> tuple[tuple[str, ...], dict[str, str], str]:
        raise RuntimeError("glossary is on fire")

    monkeypatch.setattr(T, "glossary", broken)
    assert T.translate(["훅이 조용히 죽는다"], T.KO_EN) == ["훅이 조용히 죽는다"]


def test_a_failed_translation_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caching a failure would freeze the original in place permanently."""
    monkeypatch.setattr(T, "_ask", lambda *_a: None)
    assert T.translate(["훅이 조용히 죽는다"], T.KO_EN) == ["훅이 조용히 죽는다"]

    monkeypatch.setattr(T, "_ask", _rewrites_all_prose)
    assert T.translate(["훅이 조용히 죽는다"], T.KO_EN) == ["ENGLISH ENGLISH ENGLISH"]


def test_the_cache_answers_without_a_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(T, "_ask", _rewrites_all_prose)
    first = T.translate(["훅이 조용히 죽는다"], T.KO_EN)

    asked: list[list[str]] = []
    monkeypatch.setattr(T, "_ask", lambda _s, batch, _t: asked.append(batch))
    assert T.translate(["훅이 조용히 죽는다"], T.KO_EN) == first
    assert asked == [], "a second request went out for text already cached"


def test_the_glossary_version_retires_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing the glossary has to retire what was translated under the old one.

    Without this the cache keeps serving a term the glossary no longer spells
    that way, and the wiki ends up naming one rule two ways.
    """

    monkeypatch.setattr(T, "_ask", _rewrites_all_prose)
    T.translate(["훅이 조용히 죽는다"], T.KO_EN)

    monkeypatch.setattr(T, "glossary", lambda: ((), {}, "a-different-version"))

    # Recorded rather than raised. `translate` swallows exceptions by contract,
    # so an assert thrown in here would be caught and the test would pass
    # whatever happened — a check that cannot fail is not a check.
    asked: list[list[str]] = []
    monkeypatch.setattr(T, "_ask", lambda _s, batch, _t: asked.append(batch))

    assert T.translate(["훅이 조용히 죽는다"], T.KO_EN) == ["훅이 조용히 죽는다"]
    assert asked == [["훅이 조용히 죽는다"]], "the retired entry was served anyway"


def test_keep_korean_terms_are_masked_not_merely_requested() -> None:
    """The prompt asks; the placeholder guarantees. Only the second one holds."""
    masked, spans = T.protect("나라장터 입찰공고 파서", ("나라장터", "입찰공고"))

    assert "나라장터" not in masked and "입찰공고" not in masked
    assert T.restore(masked, spans) == "나라장터 입찰공고 파서"


def test_it_runs_as_a_process_and_korean_survives_the_pipe(tmp_path: Path) -> None:
    """`craft/hooks-fail-open`, third face. The child writes Korean, the parent
    reads it, and a cp949 default in between kills the reader thread quietly."""

    done = subprocess.run(
        [sys.executable, str(TOOL), "훅이 조용히 죽는다"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        # No key, and a cache of its own. Dropping the key alone is not enough:
        # the cache answers before the key is read, so a real cache entry from
        # an earlier run would translate this and the assert below would flip.
        env={
            "PATH": "",
            "SYSTEMROOT": "C:\\Windows",
            "TRANSLATE_CACHE": str(tmp_path / "cache.sqlite3"),
        },
        check=False,
    )

    assert done.returncode == 0, done.stderr
    # No key in that environment, so it fails open and echoes the input back.
    assert done.stdout.strip() == "훅이 조용히 죽는다"
