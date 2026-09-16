"""강제 종료되어도 원문 없이 멈춘 위치가 남고 정상 출력은 보존된다."""

import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

# 이 파일이 스스로 찍지는 않는다. 그래도 고정한다 — `tool/*.py` 를 예외 없이
# 보는 것이 `lint.py` 의 이 검사이고, 좁힌 자리가 다음 사고라고 그 검사 자신이
# 적어 두었다.
#
# 좁혔으면 여기서 놓쳤다. 진짜 노출은 찍는 쪽이 아니라 **자식을 읽는 쪽**에
# 있었다 — 아래 `text=True` 넷이 로케일로 디코딩해서, 한글을 내보내는
# `codex_pretool.py` 를 읽다가 cp949 로 죽었다. 그래서 넷 다 인코딩을 적는다.
sys.stdout.reconfigure(encoding="utf-8")

TOOL = Path(__file__).resolve().parent


def test_timeout_evidence_survives_process_kill(tmp_path):
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path), "PYTHONPATH": str(TOOL)}
    code = (
        "from hook_diagnostics import arm; import time; "
        "arm('probe.py', 0.2); print('ready', flush=True); time.sleep(30)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=env, text=True, encoding="utf-8",
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        deadline = time.monotonic() + 5
        logs = []
        while time.monotonic() < deadline:
            logs = list(tmp_path.rglob("*.log"))
            if logs and "Timeout" in logs[0].read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        assert logs and "Timeout" in logs[0].read_text(encoding="utf-8")
    finally:
        process.kill()
        process.communicate(timeout=5)
    evidence = logs[0].read_text(encoding="utf-8")
    assert '"hook": "probe.py"' in evidence
    assert '"pid":' in evidence and '"started_utc":' in evidence
    assert 'File "<string>"' in evidence
    assert '"completed_ms"' not in evidence
    logs[0].unlink()

    normal = subprocess.run(
        [sys.executable, "-c", "from hook_diagnostics import arm; "
         "arm('probe.py', 8); print('unchanged')"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=10,
    )
    assert (normal.returncode, normal.stdout, normal.stderr) == (0, "unchanged\n", "")
    assert not list(tmp_path.rglob("*.log"))


@pytest.mark.skipif(os.name != "nt", reason="설치된 Windows Orca 훅 통합 검사")
def test_orca_stalled_endpoint_leaves_process_evidence_without_payload(tmp_path):
    hook = Path.home() / ".orca" / "agent-hooks" / "codex-hook.cmd"
    if not hook.exists():
        pytest.skip("Orca 훅 미설치")
    endpoint = tmp_path / "endpoint.cmd"
    endpoint.write_text(
        f'@"{sys.executable}" -c "import time; time.sleep(30)"\n', encoding="utf-8",
    )
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path),
           "ORCA_AGENT_HOOK_ENDPOINT": str(endpoint), "ORCA_AGENT_HOOK_PORT": ""}
    process = subprocess.Popen(
        ["cmd.exe", "/d", "/c", str(hook)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    observer = subprocess.Popen([
        "pwsh", "-NoProfile", "-File", str(TOOL / "watch_hook_timeouts.ps1"),
        "-ThresholdSeconds", "0.2", "-DurationSeconds", "3", "-LogDirectory", str(tmp_path),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.stdin.write(b'{"prompt":"PRIVATE_SENTINEL"}')
        process.stdin.flush()
        deadline = time.monotonic() + 6
        evidence = ""
        while time.monotonic() < deadline:
            logs = list(tmp_path.glob("process-*.log"))
            evidence = "\n".join(p.read_text(encoding="utf-8") for p in logs)
            if '"hook":"codex-hook.cmd"' in evidence:
                break
            time.sleep(0.05)
        assert '"hook":"codex-hook.cmd"' in evidence
        assert "PRIVATE_SENTINEL" not in evidence
    finally:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=10)
        process.communicate(timeout=5)
        stdout, stderr = observer.communicate(timeout=10)
        assert (observer.returncode, stdout, stderr) == (0, b"", b"")
    assert logs[0].exists()
    logs[0].unlink()
    env["ORCA_AGENT_HOOK_ENDPOINT"] = ""
    normal = subprocess.run(
        ["cmd.exe", "/d", "/c", str(hook)], input=b"private input",
        capture_output=True, env=env, timeout=5,
    )
    assert (normal.returncode, normal.stdout, normal.stderr) == (0, b"", b"")


def test_installed_pretool_records_blocked_stdin_without_content(tmp_path):
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    process = subprocess.Popen(
        [sys.executable, str(TOOL / "codex_pretool.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    try:
        process.stdin.write(b'{"prompt":"PRIVATE_SENTINEL"')
        process.stdin.flush()
        deadline = time.monotonic() + 12
        evidence = ""
        while time.monotonic() < deadline:
            logs = list(tmp_path.rglob("*.log"))
            evidence = logs[0].read_text(encoding="utf-8") if logs else ""
            if "Timeout" in evidence:
                break
            time.sleep(0.1)
        assert "Timeout" in evidence and "codex_pretool.py" in evidence
        assert "PRIVATE_SENTINEL" not in evidence
        assert process.poll() is None
    finally:
        process.kill()
        process.communicate(timeout=5)


def test_slow_completion_retention_and_unwritable_directory(tmp_path):
    directory = tmp_path / "wiki-hook-diagnostics"
    directory.mkdir()
    expired = directory / "wiki-old.log"
    expired.write_text("old", encoding="utf-8")
    os.utime(expired, (0, 0))
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path), "PYTHONPATH": str(TOOL)}
    slow = subprocess.run(
        [sys.executable, "-c", "from hook_diagnostics import arm; import time; "
         "arm('probe.py', 0.1); time.sleep(0.3); print('unchanged')"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=5,
    )
    assert (slow.returncode, slow.stdout, slow.stderr) == (0, "unchanged\n", "")
    assert not expired.exists()
    logs = list(directory.glob("*.log"))
    assert len(logs) == 1
    assert '"completed_ms"' in logs[0].read_text(encoding="utf-8")
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("keep", encoding="utf-8")
    env["LOCALAPPDATA"] = str(blocked)
    normal = subprocess.run(
        [sys.executable, str(TOOL / "codex_pretool.py")],
        input='{"tool_name":"request_user_input_async"}',
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=5,
    )
    assert normal.returncode == 0 and normal.stderr == ""
    assert '"permissionDecision": "deny"' in normal.stdout
