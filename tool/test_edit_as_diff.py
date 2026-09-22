"""`edit_as_diff` 가 막는 자리와 안 막는 자리."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tool.edit_as_diff import verdict

HOOK = Path(__file__).with_name("edit_as_diff.py")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """이미 있는 파일 하나를 가진 저장소."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "existing.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# 제목\n", encoding="utf-8")
    return tmp_path


def bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


@pytest.mark.parametrize(
    "command",
    [
        'cat > src/existing.py <<PY\nx = 2\nPY',
        'cat >> README.md <<MD\n한 줄 더\nMD',
        'cd /repo && cat > "src/existing.py" <<PY\nPY',
        "python - <<'PY'\nfrom pathlib import Path\nPath('src/existing.py').write_text('x')\nPY",
        "python - <<'PY'\nopen('README.md', 'w').write('x')\nPY",
        "tee src/existing.py <<PY\nPY",
        "echo hi > README.md",
        # The shape that takes the path in a variable and writes through it
        # later. One session did more than ten multi-point replacements this
        # way without the hook firing once, because the two python patterns
        # above only match when `Path(...)` and `.write_` sit together.
        "python - <<'PY'\nimport pathlib\np = pathlib.Path('src/existing.py')\nt = p.read_text()\np.write_text(t.replace('a', 'b'))\nPY",
        # The interpreter called by absolute path. This session actually did
        # write it that way.
        "/c/py/python.exe - <<'PY'\nimport pathlib\np = pathlib.Path('README.md')\np.write_text('x')\nPY",
        # The shape that takes `open` into a variable.
        "python - <<'PY'\nf = open('README.md', 'w')\nf.write('x')\nPY",
        # `Path.open('w')`.
        "python - <<'PY'\nfrom pathlib import Path\np = Path('src/existing.py')\nwith p.open('w') as f:\n    f.write('x')\nPY",
        # The assignment not at the start of a line. A one-line `-c` is the
        # exact shape this rule aims at, and the first version — which looked
        # only at the start of a line — missed it entirely.
        "python -c \"import pathlib; p = pathlib.Path('README.md'); p.write_text('x')\"",
        # The same thing, arriving inside a heredoc.
        "python - <<'PY'\nimport pathlib; p = pathlib.Path('src/existing.py'); p.write_text('x')\nPY",
    ],
)
def test_rewriting_a_file_that_is_already_there_is_refused(
    repo: Path, command: str
) -> None:
    answer = verdict(bash(command), repo)

    assert answer is not None, command
    decision = answer["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Edit" in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # A new file. Nothing to erase, so it cannot become a diff — the
        # page's stated exception.
        "cat > src/brand_new.py <<PY\nPY",
        # Outside the repository. There is nowhere for a diff to live.
        'cat > "$TMPDIR/scratch.py" <<PY\nPY',
        "python - <<'PY'\nPath('/tmp/x.py').write_text('x')\nPY",
        # A read-only command. There is redirection, but not onto a file.
        "grep -rn foo src/ > /dev/null",
        "pytest -q 2>&1 | tail -3",
        "git diff --stat > /dev/null 2>&1",
        # Writes no file at all.
        "ls -la src/",
        "git log --oneline -5",
        # Only reads a repository file; the result goes to the screen. The
        # variable tracking catching this too would be a false positive, and a
        # false positive that stops the work gets the hook turned off.
        "python - <<'PY'\nimport pathlib\np = pathlib.Path('src/existing.py')\nprint(len(p.read_text()))\nPY",
        # Reads a repository file and writes into the scratch directory. What
        # is being written is not in the repository.
        "python - <<'PY'\nimport pathlib\nsrc = pathlib.Path('src/existing.py')\nout = pathlib.Path('/tmp/copy.py')\nout.write_text(src.read_text())\nPY",
    ],
)
def test_what_it_must_not_block(repo: Path, command: str) -> None:
    assert verdict(bash(command), repo) is None, command


def test_a_commit_message_that_quotes_a_command_is_not_a_command(repo: Path) -> None:
    """이 훅이 처음 쓰인 자리에서 자기 오탐으로 잡힌 것.

    커밋 메시지를 heredoc 으로 넘기는데 그 메시지가 막힌 명령을 인용하고 있었고,
    훅이 그 문자열을 보고 커밋을 막았다. 리뷰 지시문·PR 본문·문서가 명령을
    인용하는 것은 정상이고 흔하다 -- 그리고 이 규칙을 설명하는 글은 반드시
    그 명령을 인용한다.
    """
    command = (
        "git commit -F - <<'MSG'\n"
        "fix: 되쓰기를 막는다\n"
        "\n"
        "cat > docs/README.md 같은 모양이 45회 나왔다.\n"
        "MSG"
    )

    assert verdict(bash(command), repo) is None


def test_a_heredoc_into_an_interpreter_is_still_code(repo: Path) -> None:
    """데이터 본문을 뺀다고 코드 본문까지 빼면 잡던 것을 놓친다."""
    command = (
        "python - <<'PY'\n"
        "from pathlib import Path\n"
        "Path('README.md').write_text('x')\n"
        "PY"
    )

    assert verdict(bash(command), repo) is not None


def test_a_redirection_on_the_command_line_survives_a_data_heredoc(repo: Path) -> None:
    """본문은 데이터여도 명령줄의 리다이렉션은 본문 밖이다."""
    command = "cat > README.md <<'MD'\n한 줄\nMD"

    assert verdict(bash(command), repo) is not None


def test_write_onto_an_existing_file_is_refused(repo: Path) -> None:
    """`Write` 는 새 파일 전용이라고 페이지가 정했다."""
    answer = verdict(
        {"tool_name": "Write", "tool_input": {"file_path": "README.md"}}, repo
    )

    assert answer is not None
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_write_onto_a_new_file_passes(repo: Path) -> None:
    assert (
        verdict({"tool_name": "Write", "tool_input": {"file_path": "NEW.md"}}, repo)
        is None
    )


def test_the_edit_tool_is_never_looked_at(repo: Path) -> None:
    """고치라고 권하는 도구를 막으면 막다른 길이 된다."""
    assert (
        verdict({"tool_name": "Edit", "tool_input": {"file_path": "README.md"}}, repo)
        is None
    )


def test_a_broken_payload_passes_rather_than_stopping_the_session(repo: Path) -> None:
    """`craft/hooks-fail-open`. 훅이 깨져서 작업이 멈추면 안 된다."""
    for payload in [{}, {"tool_name": "Bash"}, {"tool_name": "Bash", "tool_input": {}}]:
        assert verdict(payload, repo) is None


def test_it_runs_as_a_process_and_answers_on_stdout(repo: Path) -> None:
    """훅은 프로세스로 불린다. 한글이 섞인 판정이 파이프에서 안 죽는지까지 본다."""
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "cat > README.md <<MD\n한 줄\nMD"},
            "cwd": str(repo),
        }
    )
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        # The encoding is not left to the locale. A child emitting Korean and
        # a parent reading cp949 dies quietly in the reader thread — the third
        # face of `craft/hooks-fail-open`.
        encoding="utf-8",
        errors="replace",
        # A non-zero exit code is part of what this test judges. Whatever
        # happens, the hook has to return 0, and that is asserted below.
        check=False,
    )

    assert done.returncode == 0
    answer = json.loads(done.stdout)
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "README.md" in answer["systemMessage"]
