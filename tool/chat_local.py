"""이 checkout의 설정과 현재 사용자의 실행 파일만 찾는다. 인증 파일은 다루지 않는다."""

import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".chat-local.json"


def settings():
    if not SETTINGS.exists():
        return {}
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) - {"workspace", "model"}
            or any(not isinstance(v, str) for v in data.values())):
        raise ValueError(".chat-local.json의 값은 문자열이어야 합니다. 설치 명령을 다시 실행하세요.")
    return data


def cli_command(name):
    """PATH의 CLI를 그대로 사용한다. Windows npm shim은 cmd를 거치지 않는다."""
    binary = shutil.which(name)
    if not binary:
        raise FileNotFoundError(f"{name}을 PATH에서 찾지 못했습니다. docs/chat-setup.md의 설치 절차를 확인하세요.")
    path = Path(binary)
    if path.suffix.lower() not in (".cmd", ".bat", ".ps1"):
        return [binary]
    # shim이 가리키는 실제 실행 파일을 읽는다. js든 네이티브 바이너리든 패키지 구조를 따라간다.
    # npm.cmd처럼 경로가 여럿이면 마지막 것이 실제로 실행되는 진입점이다.
    found = re.findall(r"""node_modules[\\/][^"'\s%]+\.(?:js|cjs|mjs|exe)""",
                       path.read_text(encoding="utf-8", errors="replace"))
    target = path.parent / found[-1].replace("\\", "/") if found else None
    if target and target.is_file():
        if target.suffix.lower() == ".exe":
            return [str(target)]
        node = path.parent / "node.exe"
        node_binary = str(node) if node.is_file() else shutil.which("node")
        if node_binary:
            return [node_binary, str(target)]
    raise ValueError(f"{name} 실행 파일을 확인할 수 없습니다. 공식 CLI 설치 후 다시 시도하세요: {binary}")
