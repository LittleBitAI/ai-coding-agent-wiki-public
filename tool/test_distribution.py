"""Public copies must keep runtime data outside version control."""

from pathlib import Path
import json
import os
import subprocess
import sys

import pytest

from test_lint import build, kinds

ROOT = Path(__file__).resolve().parents[1]


def test_private_runtime_paths_are_ignored():
    paths = ["raw/chat/progress.jsonl", "raw/census-example.jsonl", "raw/corrections.jsonl",
             ".wiki/decisions/example.md", ".wiki/adapter.toml", ".claude/settings.json",
             ".codex/auth.json", ".chat-local.json", ".env", "graph.json",
             "adapters/local-project.toml", "artifacts/result.json"]
    result = subprocess.run(["git", "check-ignore", "--no-index", "--", *paths], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", check=True)
    assert set(result.stdout.splitlines()) == set(paths)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    placeholders = {"raw/.gitkeep", ".wiki/.gitignore", ".wiki/decisions/.gitkeep"}
    assert not any(p.startswith(("raw/", ".wiki/", ".claude/", ".codex/", "artifacts/"))
                   for p in tracked if p not in placeholders)
    assert "adapters/example.toml" in tracked


def test_withheld_evidence_preserves_severity_without_hiding_other_errors(tmp_path):
    for marker, exempt in [("", False), ("\nsources_withheld: true", True),
                           ("\nsources_withheld: false", False), ('\nsources_withheld: "true"', False)]:
        build(tmp_path, {"craft/example": {"severity": "landmine", "sources": "[]" + marker,
                                           "links": "[missing]"}})
        found = kinds(tmp_path)
        assert ("근거 없는 landmine" not in found) == exempt
        assert "끊어진 링크" in found


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher")
def test_slack_launcher_uses_explicit_local_configuration(tmp_path):
    project = tmp_path / "새 프로젝트"
    project.mkdir()
    fake = tmp_path / "fake_cli.py"
    fake.write_text('import json, os, sys\nfrom pathlib import Path\n'
                    'Path("captured.json").write_text(json.dumps({"wiki": os.environ["WIKI_ROOT"], '
                    '"channel": os.environ["SLACK_CHANNEL"], "prompt": sys.stdin.read()}), encoding="utf-8")\n',
                    encoding="utf-8", newline="\n")
    (tmp_path / "claude.cmd").write_text(f'@"{sys.executable}" "{fake}"\n', encoding="utf-8", newline="\n")
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    launcher = str(ROOT / "tool/slack_post.cmd")
    missing = subprocess.run([launcher, "standup", str(project)], env=env, capture_output=True)
    assert missing.returncode != 0
    assert not (project / "captured.json").exists()
    for kind in ("standup", "retro"):
        subprocess.run([launcher, kind, str(project), "test-channel"], env=env, check=True)
        captured = json.loads((project / "captured.json").read_text(encoding="utf-8"))
        assert Path(captured["wiki"]).resolve() == ROOT
        assert captured["channel"] == "test-channel"
        assert "<WIKI_ROOT>" in captured["prompt"] and "<SLACK_CHANNEL>" in captured["prompt"]
