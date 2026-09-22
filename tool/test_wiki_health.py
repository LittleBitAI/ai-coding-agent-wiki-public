"""측정기·배선·검사의 사각지대를 임시 저장소에서 재현한다."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import apply
import inject
import lint
import repo_lint
import trigger_audit

TOOL = Path(__file__).resolve().parent


def run(script, *args, payload=None, env=None):
    return subprocess.run(
        [sys.executable, str(TOOL / script), *map(str, args)],
        input=payload, capture_output=True, timeout=30,
        env={**os.environ, **(env or {})},
    )


def test_wiring():
    assert "tree" not in apply.unfilled("example"), "git 리비전 문법은 슬롯이 아니다"
    assert "gate_cmd" in apply.unfilled("__health_missing_adapter__"), "선언된 실제 슬롯 누락은 잡아야 한다"
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        agents = ("claude", "codex")
        assert apply.wiring_drift(project, agents)
        for agent, name in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
            settings = {"hooks": {"SessionEnd": [{"hooks": [{"command": "keep"}]}]}}
            assert apply.configure(settings, project, "example", sys.executable, agent)
            assert not apply.configure(settings, project, "example", sys.executable, agent)
            path = project / name
            path.parent.mkdir()
            path.write_text(json.dumps(settings), encoding="utf-8")
        assert not apply.wiring_drift(project, agents)
        assert not repo_lint.check(project)
        path = project / ".claude/settings.json"
        original = path.read_text(encoding="utf-8")
        for change in ("deny", "pretool", "timeout", "matcher"):
            settings = json.loads(original)
            if change == "deny":
                settings["permissions"]["deny"].pop()
            elif change == "pretool":
                settings["hooks"]["PreToolUse"].pop()
            elif change == "timeout":
                settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"] = 1
            else:
                settings["hooks"]["UserPromptSubmit"][0]["matcher"] = "never"
            path.write_text(json.dumps(settings), encoding="utf-8")
            assert apply.wiring_drift(project, agents), change
            assert any(k == "훅 배선 드리프트" for k, _m in repo_lint.check(project))
            if change == "matcher":
                assert run("apply.py", "--project", project, "--adapter", "example", "--check").returncode == 1
        path.write_text(original, encoding="utf-8")
        assert run("apply.py", "--project", project, "--adapter", "example", "--check").returncode == 0

        # 남의 UserPromptSubmit 훅이 앞에 있어도 배선은 멀쩡하다. 드리프트가
        # 자기 훅을 이름으로 고르면 남의 명령이 `commands[0]` 이 되고, 그
        # 안의 첫 따옴표 토큰이 "설치된 인터프리터" 로 읽혀 정상 배선에
        # 드리프트가 뜬다. 게이트가 그것 때문에 떨어진다.
        settings = json.loads(original)
        settings["hooks"]["UserPromptSubmit"].insert(0, {"hooks": [{
            "type": "command",
            "command": '"C:/other/python.exe" "C:/other/inject.py"',
        }]})
        path.write_text(json.dumps(settings), encoding="utf-8")
        assert not apply.wiring_drift(project, agents), "남의 훅이 앞에 있다고 드리프트가 아니다"
        path.write_text(original, encoding="utf-8")
        path.unlink()
        assert run("apply.py", "--project", project, "--adapter", "example", "--check").returncode == 1
        assert not path.exists(), "검사가 설정을 썼다"
        (project / ".codex/hooks.json").unlink()
        (project / "adapters").mkdir()
        (project / "adapters" / f"{project.name}.toml").write_text('agents=["claude","codex"]', encoding="utf-8")
        previous = apply.WIKI
        try:
            apply.WIKI = project
            assert apply.wiring_drift(project), "설정 파일 전체가 사라져도 기대 에이전트는 남는다"
        finally:
            apply.WIKI = previous


def test_measurement():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "adapters").mkdir()
        (project / "adapters/x.toml").write_text(
            '[slots]\nrule_budget=200\nrepo_budget=250\nvalue="치환된 값"\n', encoding="utf-8",
        )
        (project / "craft").mkdir()
        (project / "craft/rule.md").write_text(
            '---\nseverity: contract\ntriggers: [시험]\n---\n# 규칙\n규칙. {value}\n' + "긴 본문" * 100,
            encoding="utf-8",
        )
        (project / ".wiki/decisions").mkdir(parents=True)
        for n in range(5):
            (project / f".wiki/decisions/2026-01-0{n+1}.md").write_text(
                f'---\nseverity: contract\ntriggers: [시험]\n---\n# 결정 {n}\n왜. 이유다. 자세한 이유.',
                encoding="utf-8",
            )
        original = inject.WIKI
        try:
            inject.WIKI = project
            available = inject.pages("x", project)
            measured = trigger_audit.measure("시험 🐋", available, 200, 250)
        finally:
            inject.WIKI = original
        assert measured["repo"] > 0 and len(measured["names"]) == 6
        response = run(
            "inject.py", "--adapter", "x", "--project", project,
            payload=json.dumps({"prompt": "시험 🐋", "session_id": "health-test"}, ensure_ascii=False).encode("utf-8"),
            # 번역을 꺼서 잰다. `trigger_audit.measure` 는 오프라인 재생이라
            # 번역을 못 하는데 훅은 하므로, 켜 두면 이 단언이 재는 것이
            # 둘의 단위가 같은가가 아니라 번역이 돌았는가가 된다.
            # 키만 빼는 것으로는 모자라다 — 캐시가 키보다 먼저 답한다.
            env={"WIKI_ROOT": str(project), "PYTHONIOENCODING": "cp949",
                 "LOCALAPPDATA": tmp, "GEMINI_API_KEY": "",
                 "TRANSLATE_CACHE": str(project / "translate-cache.sqlite3")},
        )
        assert response.returncode == 0 and not response.stderr, response.stderr
        output = json.loads(response.stdout)
        assert "치환된 값" in output["hookSpecificOutput"]["additionalContext"]
        row = json.loads((project / ".wiki/trajectory.jsonl").read_text(encoding="utf-8"))
        assert row["cost"] == measured["rule"] + measured["repo"]
        assert row["injected"] == measured["names"]
        census = project / "census-a.jsonl"
        census.write_text('{"text":"시험"}\n', encoding="utf-8")
        assert trigger_audit.census_paths([str(project / "census-*.jsonl")]) == [census]
        audit = run("trigger_audit.py", project / "census-*.jsonl", "--samples", "0")
        assert audit.returncode == 0 and "| repo | 미측정" in audit.stdout.decode("utf-8")


def test_lint_sees_itself_and_malformed_pages():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tool").mkdir()
        for name in ("lint.py", "repo_lint.py"):
            source = (TOOL / name).read_text(encoding="utf-8")
            (root / "tool" / name).write_text(source, encoding="utf-8")
            assert name not in lint.fragile_tools(root)
            (root / "tool" / name).write_text(
                source.replace('sys.stdout.reconfigure(encoding="utf-8")', 'sys.stderr.reconfigure(encoding="utf-8")'),
                encoding="utf-8",
            )
            assert name in lint.fragile_tools(root)
        source = (TOOL / "session_state.py").read_text(encoding="utf-8")
        path = root / "tool/session_state.py"
        path.write_text(source, encoding="utf-8")
        assert not lint.fragile_io(root)
        assert not lint.missing_hook_guards(root, {})
        path.write_text(source.replace('    sys.stdin.reconfigure(encoding="utf-8")', ''), encoding="utf-8")
        assert any("stdin" in m for _k, m in lint.fragile_io(root))
        path.write_text(source.replace('errors="replace"', 'errors="strict"'), encoding="utf-8")
        assert any("자식 출력" in m for _k, m in lint.fragile_io(root))
        path.write_text(source.replace("except Exception as _error:", "except ValueError as _error:"), encoding="utf-8")
        assert lint.missing_hook_guards(root, {})
        (root / "craft").mkdir()
        (root / ".wiki/decisions").mkdir(parents=True)
        for broken in ('---\nseverity: contract\ntriggers: ["\\s"]\n---\n# 깨짐',
                       '---\nseverity: contract\ntriggers: ["["]\n---\n# 정규식'):
            (root / "craft/broken.md").write_text(broken, encoding="utf-8")
            (root / ".wiki/decisions/broken.md").write_text(broken, encoding="utf-8")
            assert any(k == "페이지 형식 오류" for k, _m in lint.check(root)[2])
            assert any(k == "페이지 형식 오류" for k, _m in repo_lint.check(root))


def test_synthetic_trigger_cases():
    # These examples are authored fixtures, not collected user conversations.
    available = inject.pages()
    cases = [
        ("리뷰 루프를 실행해 주세요", "operator/codex-review-loop", True),
        ("오늘 날씨를 알려 주세요", "operator/codex-review-loop", False),
        ("결과 파일을 감시해 주세요", "craft/pick-up-async-results", True),
        ("화면 레이아웃을 검토해 주세요", "craft/screen-follows-the-purpose", True),
    ]
    for text, page, expected in cases:
        names = trigger_audit.measure(text, available)["names"]
        assert (page in names) == expected, (text, page)


def test_gate_ignores_only_slot_differences():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "adapters").mkdir()
        for name in ("a", "b"):
            (root / f"adapters/{name}.toml").write_text(f'[slots]\nvalue="{name}"', encoding="utf-8")
        assert run("lint.py", "--wiki", root).returncode == 1
        assert run("lint.py", "--wiki", root, "--check").returncode == 0
        (root / "craft").mkdir()
        (root / "craft/broken.md").write_text('---\ntriggers: ["\\s"]\n---', encoding="utf-8")
        assert run("lint.py", "--wiki", root, "--check").returncode == 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, test in sorted(list(globals().items())):
        if name.startswith("test_"):
            test()
            print(f"ok  {name}")
