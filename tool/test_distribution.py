"""Public copies must keep runtime data outside version control."""

from pathlib import Path
import subprocess

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
    assert not any(p.startswith(("raw/", ".wiki/", ".claude/", ".codex/", "artifacts/")) for p in tracked)
    assert "adapters/example.toml" in tracked
