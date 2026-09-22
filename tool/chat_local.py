"""Find this checkout's settings and the current user's executables, nothing else.

Credential files are never touched.
"""

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
    """Use the CLI on PATH as it is. A Windows npm shim does not go through cmd."""
    binary = shutil.which(name)
    if not binary:
        raise FileNotFoundError(f"{name}을 PATH에서 찾지 못했습니다. docs/chat-setup.md의 설치 절차를 확인하세요.")
    path = Path(binary)
    if path.suffix.lower() not in (".cmd", ".bat", ".ps1"):
        return [binary]
    # Read the real executable the shim points at, following the package
    # layout whether that ends at a js file or a native binary. When there are
    # several paths, as in `npm.cmd`, the last one is the entry point that
    # actually runs.
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
