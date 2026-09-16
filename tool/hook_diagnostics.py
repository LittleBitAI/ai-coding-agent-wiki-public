"""훅이 외부 제한으로 죽기 전에 로컬 스택을 남긴다. stdin은 읽지 않는다."""

import atexit
from datetime import datetime, timezone
import faulthandler
import json
import os
from pathlib import Path
import sys
import time


def arm(hook: str, after: float) -> None:
    """정상 실행은 지우고 느린 실행과 강제 종료의 기록은 보존한다."""
    stream = None
    armed = False
    try:
        directory = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "wiki-hook-diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        path = directory / f"wiki-{os.getpid()}-{time.time_ns()}.log"
        stream = path.open("x", encoding="utf-8", newline="\n")
        stream.write(json.dumps({
            "hook": Path(hook).name,
            "pid": os.getpid(), "parent_pid": os.getppid(),
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "stack_after_seconds": after,
        }) + "\n")
        stream.flush()
        # C watchdog은 stdin/GIL 대기 중에도 스택을 쓴다. 외부 kill의 finally에 의존하지 않는다.
        faulthandler.dump_traceback_later(after, file=stream)

        def finish():
            try:
                faulthandler.cancel_dump_traceback_later()
                elapsed = time.monotonic() - started
                stream.write(json.dumps({"completed_ms": round(elapsed * 1000)}) + "\n")
                stream.close()
                if elapsed < after:
                    path.unlink(missing_ok=True)
            except OSError:
                pass

        atexit.register(finish)
        armed = True
        # 실행 중 파일은 건드리지 않는다. 다음 훅에서 오래된 진단만 정리한다.
        now = time.time()
        old = sorted(
            (p for p in directory.glob("*.log") if now - p.stat().st_mtime > 60),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        for index, previous in enumerate(old):
            if index >= 100 or now - previous.stat().st_mtime > 7 * 86400:
                previous.unlink(missing_ok=True)
    except (OSError, RuntimeError, ValueError):
        # 진단 실패 때문에 기존 주입·차단 판정이 달라져서는 안 된다.
        if not armed and stream is not None:
            faulthandler.cancel_dump_traceback_later()
            stream.close()


# 진입점의 첫 import에서 시작한다. apply/pytest가 이 모듈을 가져오면 켜지지 않는다.
_thresholds = {
    "codex_pretool.py": 8, "inject.py": 8, "declared_continuation.py": 8,
    "session_state.py": 13, "sync.py": 28,
}
if Path(sys.argv[0]).name in _thresholds:
    arm(sys.argv[0], _thresholds[Path(sys.argv[0]).name])
