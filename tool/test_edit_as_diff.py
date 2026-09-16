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
        # 경로를 변수에 받아 두고 나중에 쓰는 모양. 한 세션이 이것으로 다지점
        # 치환을 열 번 넘게 했고 훅은 한 번도 안 걸렸다 — 위의 두 파이썬 패턴이
        # `Path(...)` 와 `.write_` 가 **붙어 있을 때만** 맞기 때문이다.
        "python - <<'PY'\nimport pathlib\np = pathlib.Path('src/existing.py')\nt = p.read_text()\np.write_text(t.replace('a', 'b'))\nPY",
        # 인터프리터가 절대 경로로 불린 모양. 이 세션이 실제로 쓴 것이다.
        "/c/py/python.exe - <<'PY'\nimport pathlib\np = pathlib.Path('README.md')\np.write_text('x')\nPY",
        # `open` 을 변수로 받는 모양.
        "python - <<'PY'\nf = open('README.md', 'w')\nf.write('x')\nPY",
        # `Path.open('w')`.
        "python - <<'PY'\nfrom pathlib import Path\np = Path('src/existing.py')\nwith p.open('w') as f:\n    f.write('x')\nPY",
        # 대입이 줄 처음에 없는 모양. `-c` 한 줄은 이 규칙이 겨냥한 바로 그
        # 모양인데, 줄 처음만 보던 첫 판이 통째로 놓쳤다.
        "python -c \"import pathlib; p = pathlib.Path('README.md'); p.write_text('x')\"",
        # 같은 것이 힙독 안에 들어온 모양.
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
        # 새 파일. 지울 것이 없으므로 diff 가 될 수 없다 -- 페이지의 명시된 예외.
        "cat > src/brand_new.py <<PY\nPY",
        # 저장소 밖. diff 가 남을 자리가 없다.
        'cat > "$TMPDIR/scratch.py" <<PY\nPY',
        "python - <<'PY'\nPath('/tmp/x.py').write_text('x')\nPY",
        # 읽기만 하는 명령. 리다이렉션이 있어도 대상이 파일이 아니다.
        "grep -rn foo src/ > /dev/null",
        "pytest -q 2>&1 | tail -3",
        "git diff --stat > /dev/null 2>&1",
        # 파일을 아예 안 쓰는 것.
        "ls -la src/",
        "git log --oneline -5",
        # 저장소 파일을 **읽기만** 하고 결과는 화면으로. 변수 추적이 이것까지
        # 잡으면 오탐이고, 오탐이 작업을 멈추면 사용자가 훅을 끈다.
        "python - <<'PY'\nimport pathlib\np = pathlib.Path('src/existing.py')\nprint(len(p.read_text()))\nPY",
        # 저장소 파일을 읽어 **스크래치에** 쓴다. 쓰는 대상이 저장소가 아니다.
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
        # 인코딩을 로케일에 안 맡긴다. 자식이 한글을 내고 부모가 cp949 로 읽으면
        # 리더 스레드에서 조용히 죽는다 -- craft/hooks-fail-open 의 셋째 얼굴.
        encoding="utf-8",
        errors="replace",
        # 0 이 아닌 코드도 이 테스트의 판정 대상이다. 훅은 무슨 일이 있어도 0 을
        # 돌려야 하고, 그것을 아래에서 단언한다.
        check=False,
    )

    assert done.returncode == 0
    answer = json.loads(done.stdout)
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "README.md" in answer["systemMessage"]
