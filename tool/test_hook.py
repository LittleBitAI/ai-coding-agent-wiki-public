"""The user-level install: one wiring for every checkout, worktrees included."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import apply  # noqa: E402
import hook  # noqa: E402


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def attached_repo(root: Path) -> tuple[Path, Path]:
    """A clone carrying `.wiki/adapter.toml` only in its own checkout, plus a worktree of it."""

    main = root / "main clone"
    main.mkdir()
    git(main, "init", "-q")
    git(main, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "0")
    (main / ".wiki").mkdir()
    (main / ".wiki/adapter.toml").write_text('agents=["claude"]\n', encoding="utf-8")
    tree = root / "작업트리"
    git(main, "worktree", "add", "-q", str(tree))
    return main, tree


def test_worktree_resolves_to_the_attached_clone():
    with tempfile.TemporaryDirectory() as raw:
        main, tree = attached_repo(Path(raw))
        project, top = hook.project_for(tree / ".")
        assert project.resolve() == main.resolve(), "작업트리는 adapter를 가진 원래 clone의 위키를 쓴다"
        assert top.resolve() == tree.resolve(), "브랜치는 세션이 있는 작업트리에서 읽는다"
        assert hook.project_for(Path(raw)) is None, "저장소가 아니면 붙지 않는다"


def test_unattached_directory_passes_silently():
    with tempfile.TemporaryDirectory() as raw:
        done = subprocess.run(
            [sys.executable, str(HERE / "hook.py"), "claude", "inject.py"],
            input=json.dumps({"cwd": raw, "prompt": "안녕"}), capture_output=True,
            text=True, encoding="utf-8",
        )
        assert done.returncode == 0 and not done.stdout, "위키가 안 붙은 곳에서는 아무것도 내지 않는다"


def test_old_project_install_keeps_the_job():
    with tempfile.TemporaryDirectory() as raw:
        top = Path(raw)
        (top / ".claude").mkdir()
        settings = {}
        apply.configure(settings, top, None, "C:/py.exe", "claude")
        (top / ".claude/settings.json").write_text(json.dumps(settings), encoding="utf-8")
        assert hook.legacy(top, "claude", "inject.py"), "옛 설치가 있으면 두 번 돌지 않는다"
        assert not hook.legacy(top, "codex", "inject.py")


def test_user_level_wiring_round_trips():
    for agent in ("claude", "codex"):
        settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo 남의-훅"}]}]}}
        assert apply.configure(settings, None, None, "C:/py.exe", agent)
        assert not apply.configure(settings, None, None, "C:/py.exe", agent), "다시 걸어도 그대로다"
        commands = [h["command"] for gs in settings["hooks"].values() for g in gs for h in g["hooks"]]
        assert "echo 남의-훅" in commands
        ours = [c for c in commands if "hook.py" in c]
        assert ours and all("--project" not in c for c in ours), "전역 명령에는 프로젝트가 없다"
        assert all(f"hook.py\" {agent} " in c for c in ours)
        assert not apply.unwire(settings), "전역 배선은 옛 프로젝트 훅으로 치지 않는다"


def test_user_level_install_moves_the_drift_check():
    home = Path(os.environ["WIKI_USER_HOME"])
    user = home / ".claude/settings.json"
    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / ".wiki").mkdir()
        (project / ".wiki/adapter.toml").write_text('agents=["claude"]\n', encoding="utf-8")
        try:
            assert apply.wiring_drift(project), "아무 데도 안 걸렸으면 드리프트다"
            settings = {}
            apply.configure(settings, None, None, sys.executable, "claude")
            user.parent.mkdir(parents=True, exist_ok=True)
            user.write_text(json.dumps(settings), encoding="utf-8")
            assert not apply.wiring_drift(project), "전역에 걸렸으면 프로젝트 설정이 없어도 된다"
            old = {}
            apply.configure(old, project, None, sys.executable, "claude")
            (project / ".claude").mkdir()
            (project / ".claude/settings.json").write_text(json.dumps(old), encoding="utf-8")
            assert apply.wiring_drift(project), "전역과 겹친 옛 프로젝트 훅은 걷으라고 말한다"
            assert apply.unwire(old) and not apply.unwire(old)
        finally:
            user.unlink(missing_ok=True)
