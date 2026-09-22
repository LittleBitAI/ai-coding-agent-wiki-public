"""What has to stay true about `sessions.py`.

Finding a log used to live in `census.py`, and the mirror — a live screen —
imported the diagnostic to do it. These are the cases that made the split
worth doing: several worktrees of one repository, and worktrees that are gone.

Nothing here touches a real session directory or a network.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sessions as S  # noqa: E402


def claude_log(folder: Path, name: str, cwd: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(json.dumps({"type": "user", "cwd": str(cwd)}) + "\n", encoding="utf-8")
    return path


def rollout(day: Path, name: str, cwd: Path) -> Path:
    day.mkdir(parents=True, exist_ok=True)
    path = day / name
    path.write_text(
        json.dumps({"type": "session_meta", "payload": {"cwd": str(cwd)}}) + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# Which log belongs to which checkout
# --------------------------------------------------------------------------


def test_codex_finds_its_rollout_by_cwd(tmp_path, monkeypatch):
    day = tmp_path / "2026" / "09" / "22"
    rollout(day, "rollout-a.jsonl", tmp_path / "elsewhere")
    mine = rollout(day, "rollout-b.jsonl", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setattr(S, "codex_homes", lambda: [tmp_path])

    assert S.codex_session((tmp_path / "repo").resolve()) == mine
    assert S.codex_session((tmp_path / "nowhere").resolve()) is None


def test_codex_sessions_are_not_only_under_the_default_home(tmp_path, monkeypatch):
    """Orca gives every Codex cell its own `CODEX_HOME`, per account.

    Reading only `~/.codex/sessions` found none of the sessions the person
    actually runs, and the mirror said "no session" while one was running in
    front of them. Measured, with a live cell open.
    """

    default = tmp_path / "home" / ".codex"
    account = tmp_path / "roaming" / "orca" / "codex-accounts" / "acc-1" / "home"
    moved = tmp_path / "moved"
    for root in (default, account, moved):
        (root / "sessions").mkdir(parents=True)

    monkeypatch.setattr(S.Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("CODEX_HOME", str(moved))

    found = S.codex_homes()

    assert moved / "sessions" in found          # CODEX_HOME wins, and comes first
    assert default / "sessions" in found        # the default is still read
    assert account / "sessions" in found        # and so is every Orca account
    assert found[0] == moved / "sessions"
    assert len(found) == len(set(found))        # a home named twice is read once


def test_a_cell_opened_in_a_subfolder_still_belongs_to_the_repo(tmp_path):
    """Cells get opened in `web/` all the time. `==` reports no session at all."""

    repo = (tmp_path / "repo").resolve()

    assert S.under(repo, repo)
    assert S.under(repo / "web" / "src", repo)
    assert not S.under(repo.parent, repo)
    assert not S.under((tmp_path / "other").resolve(), repo)
    assert not S.under(None, repo)


def test_two_worktrees_sharing_a_leaf_name_do_not_share_a_log(tmp_path):
    """`folder`'s fallback used to take the first name that matched the tail.

    Two repositories each had a worktree called `pollock`. Handing the first
    one found to whichever asked is how one repository's session shows up in
    another's mirror, and nothing on the screen says it happened.
    """

    root = tmp_path / "projects"
    for flat in ("C--a-pollock", "C--b-pollock"):
        (root / flat).mkdir(parents=True)
    wanted = tmp_path / "somewhere" / "pollock"
    wanted.mkdir(parents=True)

    found = S.folder(wanted, root)

    assert not found.is_dir()               # better nothing than the wrong one
    assert found.name.endswith("-pollock")  # it is still the name it would have


def test_the_tail_fallback_still_answers_when_only_one_matches(tmp_path):
    """The fallback exists for an environment where the flattening differs."""

    root = tmp_path / "projects"
    only = root / "flattened-some-other-way-demo"
    only.mkdir(parents=True)
    project = tmp_path / "elsewhere" / "demo"
    project.mkdir(parents=True)

    assert S.folder(project, root) == only


# --------------------------------------------------------------------------
# Which repository a checkout is of
# --------------------------------------------------------------------------


def git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_a_worktree_says_which_repository_it_is_of(tmp_path):
    """The one question the directory name cannot answer.

    `--git-common-dir` is the main clone's `.git` seen from any worktree of
    it, so two checkouts of one repository come back with the same answer
    however their directories are named.
    """

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit",
        "--allow-empty", "-m", "one")
    git(repo, "worktree", "add", "-b", "side", str(tmp_path / "barb"))

    root, branch = S.checkout(repo)
    assert Path(root) == repo.resolve()
    assert branch == "main"

    root, branch = S.checkout(tmp_path / "barb")
    assert Path(root) == repo.resolve()   # the same repository, not another one
    assert branch == "side"


def test_a_clone_with_no_commit_is_still_a_repository(tmp_path):
    """`rev-parse` answers one of the two questions and exits non-zero anyway.

    Demanding exit 0 threw away the answer git had already printed, and a
    freshly initialised repo came out looking like it was not a repo at all.
    """

    repo = tmp_path / "fresh"
    repo.mkdir()
    git(repo, "init", "-b", "main")

    root, branch = S.checkout(repo)

    assert Path(root) == repo.resolve()
    assert branch == ""  # nothing is checked out yet, and `HEAD` is not a name


def test_a_directory_that_is_not_a_checkout_says_so(tmp_path):
    assert S.checkout(tmp_path) == ("", "")


# --------------------------------------------------------------------------
# The listing
# --------------------------------------------------------------------------


def test_every_checkout_with_a_session_is_offered(tmp_path, monkeypatch):
    """The picker's whole list. A checkout appears once, under its latest session."""

    day = tmp_path / "2026" / "09" / "22"
    for name, cwd in (
        ("rollout-a.jsonl", tmp_path / "work"),
        ("rollout-b.jsonl", tmp_path / "work" / "web"),  # a subfolder of the same repo
        ("rollout-c.jsonl", tmp_path / "other"),
    ):
        rollout(day, name, cwd)
        cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(S, "codex_homes", lambda: [tmp_path])

    rows = S.checkouts("codex")

    assert {row["path"] for row in rows} == {
        str(tmp_path / "work"),
        str(tmp_path / "work" / "web"),
        str(tmp_path / "other"),
    }
    assert all(row["name"] for row in rows)


def test_a_deleted_worktree_leaves_the_listing_when_it_leaves_the_disk(
    tmp_path, monkeypatch
):
    """Deleting a worktree does not delete what the host wrote about it.

    Twelve of twenty-nine rows in the picker were checkouts that no longer
    existed, each still offering to mirror a session that could never say
    another word.
    """

    day = tmp_path / "2026" / "09" / "22"
    here, gone = tmp_path / "here", tmp_path / "gone"
    rollout(day, "rollout-a.jsonl", here)
    rollout(day, "rollout-b.jsonl", gone)
    here.mkdir()  # `gone` is never created — that is the point
    monkeypatch.setattr(S, "codex_homes", lambda: [tmp_path])

    assert {row["path"] for row in S.checkouts("codex")} == {str(here)}


def test_the_listing_carries_the_repository_each_checkout_is_of(tmp_path, monkeypatch):
    """Several worktrees of one repository, told apart by branch, not by name."""

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit",
        "--allow-empty", "-m", "one")
    git(repo, "worktree", "add", "-b", "side", str(tmp_path / "barb"))

    day = tmp_path / "logs" / "2026" / "09" / "22"
    rollout(day, "rollout-a.jsonl", repo)
    rollout(day, "rollout-b.jsonl", tmp_path / "barb")
    monkeypatch.setattr(S, "codex_homes", lambda: [tmp_path / "logs"])

    rows = {row["path"]: row for row in S.checkouts("codex")}

    assert len(rows) == 2
    assert {row["repo"] for row in rows.values()} == {str(repo.resolve())}
    assert rows[str(repo)]["branch"] == "main"
    assert rows[str(tmp_path / "barb")]["branch"] == "side"
    assert rows[str(tmp_path / "barb")]["repoName"] == "repo"
