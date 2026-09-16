"""PreToolUse 훅 — 이미 있는 파일을 통째로 되쓰면 막는다."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# 파일에 쓰는 셸·파이썬 모양. 명령 모양은 무한하므로 전부 잡지 않는다 — 이 넷은
# 한 세션에서 실제로 45회를 만든 것들이고, 못 잡는 나머지는 페이지 산문이 든다.
WRITERS = (
    # `cat > path`, `cat >> path`, `tee path`
    re.compile(r"\b(?:cat|tee)\s+(?:-a\s+)?>>?\s*(?P<path>\"[^\"]+\"|'[^']+'|[\w./$~-]+)"),
    re.compile(r"\btee\s+(?:-a\s+)?(?P<path>\"[^\"]+\"|'[^']+'|[\w./$~-]+)"),
    # 리다이렉션. `2>&1` 과 `>/dev/null` 은 아래에서 걸러진다.
    re.compile(r"(?<![0-9&>])>>?\s*(?P<path>\"[^\"]+\"|'[^']+'|[\w./$~-]+\.[A-Za-z0-9]+)"),
    # 파이썬이 경로를 열어 쓰는 자리. heredoc 본문이 그대로 command 에 들어 있다.
    re.compile(r"Path\(\s*(?P<path>\"[^\"]+\"|'[^']+')\s*\)\s*\.\s*write_"),
    re.compile(r"open\(\s*(?P<path>\"[^\"]+\"|'[^']+')\s*,\s*[\"'][wa]"),
)

# 경로를 변수에 받아 두고 나중에 쓰는 모양. 위의 두 패턴은 `Path(...)` 와
# `.write_` 가 **붙어 있을 때만** 맞는데, 한 세션이 이것으로 다지점 치환을 열 번
# 넘게 했고 훅은 한 번도 안 걸렸다. 변수 하나를 따라가는 것이 그 구멍을 덮는다.
#
# 따라가는 것은 **대입 한 번**이다. 그 이상은 파서가 필요하고,
# 파서가 필요한 만큼 복잡한 스크립트는 이 규칙이 애초에 막으려는 것이다.
#
# 대입은 줄 처음이거나 `;` 뒤다. 줄 처음만 보던 첫 판은 이 규칙이 겨냥한 바로 그
# 모양을 놓쳤다 -- `python -c "import pathlib; p = pathlib.Path('README.md');
# p.write_text('x')"` 는 전부 한 줄이고, 힙독 안에 같은 것을 넣어도 마찬가지다.
#
# ponytail: 리터럴 대입 한 번까지다. `for n in [...]: p = Path(n)` 처럼 인자가
# 변수면 안 잡힌다. 그 경계를 넘는 것이 파서이고, 파서가 필요할 만큼 복잡한
# 스크립트를 손으로 짜는 것 자체가 이 규칙이 말리려는 일이다.
ASSIGNED_PATH = re.compile(
    r"(?:^|;)\s*(?P<name>\w+)\s*=\s*(?:[\w.]*\bPath|open)\(\s*"
    r"(?P<path>\"[^\"]+\"|'[^']+')",
    re.MULTILINE,
)
# 그 변수로 쓰는 자리. 읽기만 하는 것(`read_text`)은 여기 없다 — 읽기까지 막으면
# 오탐이고, 오탐이 작업을 멈추면 사용자가 훅을 통째로 끈다.
WRITES_THROUGH = (
    r"\.\s*write_\w*\s*\(",
    r"\.\s*open\(\s*[\"'][wa]",
    r"\.\s*writelines\s*\(",
    r"\.\s*write\s*\(",
)

# 저장소 밖이거나 diff 가 의미 없는 자리.
EXEMPT = re.compile(
    r"/dev/null|\$TMPDIR|\$\{TMPDIR|/tmp/|[Tt]emp[/\\]|scratchpad|\.git/|node_modules"
)

REASON = (
    "이미 있는 파일은 Edit 으로 고친다. 통째로 되쓰지 마라.\n"
    "되쓰려던 파일: {paths}\n"
    "\n"
    "왜 막는가. 한 줄을 고치려고 파일 전체를 다시 쓰면 무엇이 바뀌었는지가 diff 에\n"
    "안 남고, 인코딩과 줄끝이 조용히 뒤집힌다. 그리고 대상 텍스트가 안 맞을 때\n"
    "Edit 은 소리 내며 실패하지만 스크립트는 아무것도 안 바꾸고 조용히 성공한다.\n"
    "\n"
    "대신 이렇게. 바꿀 텍스트와 바꿀 내용을 짝지어 Edit 을 호출하라. 여러 자리면\n"
    "Edit 을 여러 번 호출한다. 새 파일이면 Write 를, 저장소 밖 스크래치면 그대로\n"
    "셸을 써도 된다 — 이 훅은 이미 있는 저장소 파일만 본다."
)


def _unquote(raw: str) -> str:
    return raw[1:-1] if raw[:1] in {'"', "'"} and raw[-1:] == raw[:1] else raw


# heredoc 본문을 *코드로* 받는 것들. 이 목록에 없는 수신자에게 가는 본문은
# 데이터이므로 스캔에서 뺀다.
INTERPRETERS = re.compile(r"\b(?:python[23]?|node|deno|bash|sh|zsh|perl|ruby)\b")
HEREDOC = re.compile(r"<<-?\s*(?P<quote>['\"]?)(?P<delim>\w+)(?P=quote)")


def strip_data_heredocs(command: str) -> str:
    """수신자가 인터프리터가 아닌 heredoc 의 본문을 지운다.

    **이 훅이 처음 쓰인 자리에서 자기 오탐으로 잡힌 것이 이것이다.** 커밋 메시지를
    `git commit -F - <<'MSG'` 로 넘기는데 그 메시지가 `cat > docs/README.md` 라는
    문장을 인용하고 있었고, 훅이 그 문자열을 보고 커밋을 막았다. 리뷰 지시문·PR
    본문·문서가 명령을 인용하는 것은 정상이고 흔하다.

    가르는 것은 본문이 무엇이 되느냐다. `python - <<'PY'` 의 본문은 *실행되는
    코드*라 봐야 하고, `git commit -F - <<'MSG'` 의 본문은 *데이터*라 안 봐야 한다.
    명령줄 자체의 리다이렉션은 본문 밖이므로 어느 쪽이든 그대로 남는다 --
    `cat > file <<'PY'` 는 계속 잡힌다.
    """
    out, cursor = [], 0
    for opener in HEREDOC.finditer(command):
        line_start = command.rfind("\n", 0, opener.start()) + 1
        receiver = command[line_start : opener.start()]
        out.append(command[cursor : opener.end()])
        cursor = opener.end()
        if INTERPRETERS.search(receiver):
            continue  # 코드다. 본문을 그대로 둔다
        delimiter = opener.group("delim")
        closing = re.search(
            rf"^\s*{re.escape(delimiter)}\s*$", command[cursor:], re.MULTILINE
        )
        if closing is None:
            continue  # 닫는 줄을 못 찾으면 판정하지 않는다
        cursor += closing.end()
    out.append(command[cursor:])
    return "".join(out)


def _through_variables(command: str) -> list[str]:
    """`p = Path("...")` 로 받아 두고 `p.write_text(...)` 로 쓰는 경로."""

    found: list[str] = []
    for match in ASSIGNED_PATH.finditer(command):
        name = match.group("name")
        path = _unquote(match.group("path"))
        if not path:
            continue
        written = any(
            re.search(rf"\b{re.escape(name)}\s*{tail}", command)
            for tail in WRITES_THROUGH
        )
        if written and path not in found:
            found.append(path)
    return found


def targets(command: str) -> list[str]:
    """명령이 쓰려는 경로 중 저장소 안의 것."""
    found: list[str] = []
    command = strip_data_heredocs(command)
    for pattern in WRITERS:
        for match in pattern.finditer(command):
            path = _unquote(match.group("path"))
            if EXEMPT.search(path) or not path:
                continue
            if path not in found:
                found.append(path)
    for path in _through_variables(command):
        if EXEMPT.search(path) or path in found:
            continue
        found.append(path)
    return found


def existing(paths: list[str], root: Path) -> list[str]:
    """그중 지금 실제로 있는 파일. 없는 것은 새 파일이므로 통과."""
    live = []
    for path in paths:
        candidate = Path(path) if os.path.isabs(path) else root / path
        try:
            if candidate.is_file():
                live.append(path)
        except OSError:
            continue  # 경로로 안 읽히면 판정하지 않는다
    return live


def verdict(payload: dict, root: Path) -> dict | None:
    """막아야 하면 훅 출력, 아니면 None."""

    tool = str(payload.get("tool_name"))
    given = payload.get("tool_input") or {}

    # Write 는 경로가 인자로 온다. 페이지가 정한 대로 새 파일에만 쓴다.
    if tool == "Write":
        path = str(given.get("file_path") or "")
        if not path or EXEMPT.search(path):
            return None
        hits = existing([path], root)
    elif tool == "Bash":
        command = str(given.get("command") or "")
        if not command:
            return None
        hits = existing(targets(command), root)
    else:
        return None

    if not hits:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON.format(paths=", ".join(hits)),
        },
        "systemMessage": f"이미 있는 파일을 되쓰려 해서 막았다: {', '.join(hits)}",
    }


def main() -> int:
    # 판정 대상도 차단 사유도 한글이다. 인코딩을 환경에 안 맡긴다.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        root = Path(str(payload.get("cwd") or Path.cwd()))
        answer = verdict(payload, root)
    except Exception:
        return 0  # 통과. 훅이 깨져서 작업이 멈추면 안 된다.
    if answer:
        json.dump(answer, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    # 첫머리의 규칙을 `main` 밖까지 덮는다. 무엇이든 잘못되면 통과시킨다.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
