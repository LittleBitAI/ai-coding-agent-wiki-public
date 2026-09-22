"""What the emphasis hook has to catch, and what it must never fire on.

The second half matters as much as the first. A hook that blocks correct prose
gets switched off, and a hook that is off enforces nothing — so every rule here
has a companion test proving the nearest correct shape still passes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from markdown_emphasis import verdict  # noqa: E402

HOOK = HERE / "markdown_emphasis.py"

CLEAN = """# 제목

규칙. 훅은 세션을 멈추지 않는다. `sys.stdout.reconfigure` 로 인코딩을 고정한다.

어겼을 때. 훅이 조용히 사라진다. 안 도는 것보다 나쁜 것은 안 도는데 도는 줄
아는 것이다.

## 표도 산문이 아니다

| 무엇 | 왜 |
| --- | --- |
| **굵게** | 표 셀의 굵게는 라벨 노릇을 한다 |

```python
print("**이 안은 안 센다**")
```

여기서 하나만 **정말 중요한 것**을 짚는다. 나머지는 문장으로 세운다.
"""


def blocked(text: str, path: str = "docs/x.md", tool: str = "Write") -> str | None:
    key = "content" if tool == "Write" else "new_string"
    answer = verdict({"tool_name": tool, "tool_input": {"file_path": path, key: text}})
    return None if answer is None else (
        answer["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_a_document_that_uses_emphasis_once_passes() -> None:
    assert blocked(CLEAN) is None


def test_a_bolded_paragraph_label_is_refused() -> None:
    """This repo writes `규칙.` and `어겼을 때.` plain. Bolding the label puts
    the emphasis on the scaffolding instead of the content."""

    why = blocked(CLEAN.replace("규칙. 훅은", "**규칙.** 훅은"))
    assert why and "문단 라벨" in why


def test_bold_opening_a_wrapped_line_is_not_a_label() -> None:
    """This fired a false positive once.

    A bold run at the head of a wrapped line is ordinary mid-sentence emphasis.
    Counting it as a label blocks correct prose, and a hook that blocks correct
    prose gets switched off.
    """

    text = (
        "# 제목\n\n"
        "`stdout` 만 고치면 절반이다. `stdin` 이 깨지면 발화가 트리거에 안 맞아\n"
        "**죽지도 않고 아무 일도 안 한다.** 트레이스백조차 안 남는다.\n"
    )
    assert blocked(text) is None


def test_two_bolds_on_one_line_are_refused() -> None:
    text = CLEAN.replace(
        "여기서 하나만 **정말 중요한 것**을 짚는다.",
        "여기서 **이것**과 **저것**을 짚는다.",
    )
    why = blocked(text)
    assert why and "한 줄에 굵게가 둘 이상" in why


def test_bold_across_a_line_break_is_refused() -> None:
    text = CLEAN.replace(
        "여기서 하나만 **정말 중요한 것**을 짚는다.",
        "여기서 하나만 **정말\n중요한 것**을 짚는다.",
    )
    why = blocked(text)
    assert why and "줄바꿈을 건너뛰는" in why


def test_density_over_the_limit_is_refused() -> None:
    body = "\n\n".join(f"{n} 번째 문단이고 여기 **강조**가 있다." for n in range(9))
    why = blocked(f"# 제목\n\n{body}\n")
    assert why and "상한" in why


def test_density_under_the_limit_passes() -> None:
    plain = "\n\n".join(f"{n} 번째 문단이고 강조가 없다." for n in range(30))
    why = blocked(f"# 제목\n\n{plain}\n\n여기 하나만 **정말 중요한 것**이 있다.\n")
    assert why is None


def test_fences_and_tables_are_not_counted() -> None:
    """Asterisks inside a fence and bold in a table cell do not move the ratio."""

    fence = "```\n" + "\n".join("**x**" for _ in range(40)) + "\n```"
    rows = "\n".join("| **a** | **b** |" for _ in range(40))
    plain = "\n\n".join(f"{n} 번째 문단." for n in range(12))
    assert blocked(f"# 제목\n\n{plain}\n\n{fence}\n\n{rows}\n") is None


def test_a_short_edit_fragment_is_not_judged_on_density() -> None:
    """`new_string` carries part of a document, not a document. A ratio over a
    fragment says nothing, so density never refuses one. A label or a doubled
    bold is still certain inside a fragment."""

    fragment = "한 줄이고 **강조**가 있다.\n\n또 한 줄에도 **강조**가 있다.\n"
    assert blocked(fragment, tool="Edit") is None

    labelled = "**규칙.** 한 줄이다.\n"
    why = blocked(labelled, tool="Edit")
    assert why and "문단 라벨" in why


def test_files_that_are_not_markdown_pass() -> None:
    noisy = CLEAN.replace("규칙. 훅은", "**규칙.** 훅은")
    assert blocked(noisy, path="tool/x.py") is None
    assert blocked(noisy, path="README") is None


def test_other_tools_pass() -> None:
    noisy = CLEAN.replace("규칙. 훅은", "**규칙.** 훅은")
    assert blocked(noisy, tool="Read") is None
    assert blocked(noisy, tool="Bash") is None


def test_a_broken_payload_passes_rather_than_stopping_the_session() -> None:
    """`craft/hooks-fail-open`. A broken hook must never stop the work."""

    for payload in [{}, {"tool_name": "Write"}, {"tool_name": "Write", "tool_input": {}}]:
        assert verdict(payload) is None


def test_it_runs_as_a_process_and_answers_on_stdout() -> None:
    """A hook is called as a process. This also checks that a Korean verdict
    survives the pipe."""

    payload = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "docs/x.md",
                "content": CLEAN.replace("규칙. 훅은", "**규칙.** 훅은"),
            },
        }
    )
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        # The child writes Korean; a cp949 default in the parent kills the
        # reader thread quietly -- craft/hooks-fail-open, third face.
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert done.returncode == 0
    answer = json.loads(done.stdout)
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "문단 라벨" in answer["hookSpecificOutput"]["permissionDecisionReason"]
