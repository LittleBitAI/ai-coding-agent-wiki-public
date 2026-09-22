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

from markdown_emphasis import findings, verdict  # noqa: E402

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


def test_a_fragment_is_judged_only_on_what_needs_no_context() -> None:
    """When the result cannot be rebuilt, only the context-free checks run.

    Density needs a whole document and a label needs to know a block begins
    there. Guessing either from a fragment refuses correct prose — a bold
    opening a wrapped line is ordinary emphasis, and a review round found
    exactly that. What survives is what holds on any line by itself.
    """

    # `docs/nowhere.md` does not exist, so no result can be built.
    missing = "docs/nowhere.md"
    assert blocked("**규칙.** 한 줄이다.\n", path=missing, tool="Edit") is None

    why = blocked("여기 **이것**과 **저것**이 있다.\n", path=missing, tool="Edit")
    assert why and "한 줄에 굵게가 둘 이상" in why


def test_a_patch_is_judged_at_its_destination() -> None:
    """`*** Move to:` decides where the result lands, so it decides the check.

    Reading only the source header let a patch rename `notes.txt` into a `.md`
    and skip the extension test on the way. The check keyed on where the file
    came from rather than where it was going.
    """

    patch = (
        "*** Begin Patch\n*** Update File: notes.txt\n*** Move to: docs/x.md\n@@\n"
        "-old\n+여기 **이것**과 **저것**이 있다.\n*** End Patch"
    )
    assert verdict({"tool_name": "apply_patch", "tool_input": {"input": patch}})


def test_a_new_file_in_a_patch_is_a_whole_document() -> None:
    """`Add File` carries everything the file will hold, so it is judged whole."""

    patch = (
        "*** Begin Patch\n*** Add File: docs/n.md\n@@\n"
        "+# 제목\n+\n+**규칙.** 라벨을 굵게\n*** End Patch"
    )
    answer = verdict({"tool_name": "apply_patch", "tool_input": {"input": patch}})
    assert answer and "문단 라벨" in answer["hookSpecificOutput"]["permissionDecisionReason"]


def test_what_a_fragment_could_push_over_the_limit_is_left_to_lint(
    tmp_path: Path,
) -> None:
    """The hook stopped predicting what an edit would leave behind.

    Three rounds of review found faces of that prediction — a second hunk,
    `replace_all`, a four-backtick fence — each fix reimplementing more of
    `git apply` inside a style hook. `lint.loud_emphasis` reads the file
    afterwards instead, where there is nothing to guess about. The hook letting
    a fragment through is only defensible because that check exists, so this
    test holds both halves at once.
    """

    import lint

    noisy = "# 제목\n\n" + "\n\n".join(f"{n} 번째 **강조**." for n in range(9)) + "\n"
    assert blocked(noisy, tool="Edit") is None, "조각으로는 비율을 안 본다"

    (tmp_path / "loud.md").write_text(noisy, encoding="utf-8")
    (tmp_path / "quiet.md").write_text(CLEAN, encoding="utf-8")
    found = lint.loud_emphasis(tmp_path)

    assert [where for _kind, where in found if "loud.md" in where], "lint 가 못 잡았다"
    assert not [where for _kind, where in found if "quiet.md" in where]


def test_the_check_reaches_a_target_repository(tmp_path: Path) -> None:
    """허브에만 걸어 두면 설치된 저장소에서는 아무도 안 본다.

    훅이 조각을 통과시키는 것은 그 뒤에 파일을 읽는 검사가 있기 때문인데,
    그 검사가 허브에서만 돌면 대상 저장소에서는 강제가 통째로 비어 있다.
    `repo_lint` 가 `sync` 의 Stop 에서 도는 자리라 거기 있어야 한다.
    """

    import lint
    import repo_lint

    (tmp_path / ".wiki").mkdir()
    (tmp_path / "x.md").write_text(
        "# 제목\n\n" + "\n\n".join(f"{n} 번째 **강조**." for n in range(9)) + "\n",
        encoding="utf-8",
    )

    assert [k for k, _ in repo_lint.check(tmp_path) if k == "강조 과다"]
    assert [k for k, _ in lint.check(lint.WIKI, None, [tmp_path])[2] if k == "강조 과다"]


def test_the_scan_follows_git_rather_than_a_hand_written_exclusion_list(
    tmp_path: Path,
) -> None:
    """손으로 쓴 제외 목록은 허브의 사정이지 남의 저장소의 사정이 아니다.

    `web/`·`artifacts/`·`raw/` 를 이름으로 거르니 대상 저장소에서는 진짜 문서가
    통째로 빠졌고, 앞자리만 같은 `node_modules-guide.md` 도 같이 빠졌다.
    "이 파일이 우리 것인가" 는 git 이 이미 답을 안다.
    """

    import lint

    for args in (["init", "-q"], ["config", "user.email", "t@e.com"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                       capture_output=True)
    (tmp_path / ".gitignore").write_text("vendor/\n", encoding="utf-8")

    noisy = "# 제목\n\n" + "\n\n".join(f"{n} 번째 **강조**." for n in range(9)) + "\n"
    for rel in ("web/docs/x.md", "artifacts/x.md", "raw/x.md",
                "node_modules-guide.md", "vendor/skip.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(noisy, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True,
                   capture_output=True)

    seen = {where.split("`")[1] for _kind, where in lint.loud_emphasis(tmp_path)}
    assert "web/docs/x.md" in seen and "node_modules-guide.md" in seen
    assert "vendor/skip.md" not in seen, "무시 대상까지 봤다"


def test_both_bold_spellings_count_and_inline_code_does_not() -> None:
    """`__` 만 쓰면 규칙을 통째로 빠져나갈 수 있었다. 반대로 인라인 코드 안의
    별표는 문자인데 강조로 세어 마크다운을 설명하는 산문을 거부했다."""

    under = "# t\n\n" + "\n\n".join(f"{n} 번째 __강조__." for n in range(9)) + "\n"
    assert findings(under), "`__bold__` 가 안 세어졌다"

    assert findings("`**a**` and `**b**`", whole=False) == []


def test_a_markdown_file_that_cannot_be_read_is_a_finding(tmp_path: Path) -> None:
    """건너뛰면 "전부 봤다" 가 거짓인 채로 게이트가 초록이 된다."""

    import lint

    (tmp_path / "bad.md").write_bytes(b"\xff\xfe**x**")
    found = lint.loud_emphasis(tmp_path)

    assert [where for _kind, where in found if "읽지 못했다" in where]


def test_only_a_real_closing_fence_closes_a_fence() -> None:
    """Three rounds each added one missing clause and each time the next input
    shape was still wrong: the marker character, then its length, then the info
    string. These are the whole CommonMark rule, held at once.
    """

    tick = chr(96)
    inside = "\n".join(["**code**"] * 4 + ["plain"] * 4)
    for name, text in {
        "info string on the closing line": (
            f"# t\n{tick * 3}text\n{tick * 3}python\n{inside}\n{tick * 3}\n"
        ),
        "a tilde run inside a backtick block": (
            f"# t\n\n{tick * 3}text\n~~~\n{inside}\n{tick * 3}\n"
        ),
        "a shorter run inside a longer one": (
            f"# t\n\n{tick * 4}\n{tick * 3}\n{inside}\n{tick * 4}\n"
        ),
        "a tilde fence": f"# t\n\n~~~\n{inside}\n~~~\n",
        "a fence indented three spaces": (
            f"# t\n\n   {tick * 3}\n{inside}\n   {tick * 3}\n"
        ),
    }.items():
        assert findings(text) == [], name


def test_prose_outside_a_fence_is_still_counted() -> None:
    """The fence rule must not become a way to stop counting anything."""

    loud = "# t\n\n" + "\n\n".join(f"{n} 번째 **강조**." for n in range(9)) + "\n"
    assert findings(loud), "펜스 밖이 안 세어졌다"


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
