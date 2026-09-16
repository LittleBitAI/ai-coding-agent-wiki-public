"""Claude의 살아 있는 프로세스와 Codex의 명시적 resume을 대화 하나로 감싼다."""

from __future__ import annotations

import json
import subprocess
import threading
import queue
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from chat_local import cli_command

# 브라우저에서 열리는 것이 파일을 고치면 그건 채팅이 아니라 원격 셸이다.
# 그래서 Edit·Write 는 목록에 없다.
#
# ponytail: Bash 는 있다. `git log` 와 `tool/*.py` 를 부르려면 필요하고, 그것
# 없이는 채널 넷이 다 반쪽이 된다. 셸이므로 이론상 쓰기가 가능하지만 대상
# 저장소의 `permissions.deny`(git reset --hard · sed -i · secrets)가 그대로
# 걸린다. 더 조이려면 Bash 대신 도구별 엔드포인트를 파라.
READ_TOOLS = "Bash,Read,Glob,Grep"

BOOT_TIMEOUT = 120.0   # 첫 턴은 훅과 적재가 있어 느리다
TURN_TIMEOUT = 600.0


@dataclass
class Event:
    """화면이 알아야 하는 것만. 나머지 이벤트 종류는 여기서 버린다."""

    kind: str          # "delta" | "tool" | "done" | "error"
    text: str = ""
    meta: dict = field(default_factory=dict)


def _blocks(message: dict) -> list[dict]:
    content = (message or {}).get("content")
    return content if isinstance(content, list) else []


class ChatSession:
    """한 채널의 살아 있는 대화. 한 번에 한 턴만 돈다."""

    def __init__(self, repo: Path, tools: str = READ_TOOLS,
                 system: str = "", model: str | None = None,
                 effort: str | None = None, resume: str | None = None,
                 isolated: bool = False) -> None:
        self.repo = Path(repo)
        self.tools = tools
        # 채널의 성격은 시스템 프롬프트로 붙인다. 처음엔 이것을 첫 턴으로
        # 태웠는데 그 한 턴이 2분을 먹었다 — 모델이 소개를 읽고 파일을 뒤진다.
        # 시스템 프롬프트는 턴을 안 쓰고 첫 발화부터 걸린다.
        self.system = system.strip()
        # 모델과 effort 는 띄울 때 정해진다. 바꾸려면 `reconfigure` 가 프로세스를
        # 다시 띄우는데, 그때 `--resume` 으로 이어 붙여 대화를 안 잃는다.
        self.model = model or None
        self.effort = effort or None
        self.isolated = isolated
        self.session_id: str | None = resume
        self.model_name = ""
        self._resume: str | None = resume
        self._proc: subprocess.Popen | None = None
        self._events: queue.Queue[dict] = queue.Queue()
        self._turn = threading.Lock()
        self._start = threading.Lock()
        self._stderr: deque[str] = deque(maxlen=20)

    @property
    def is_codex(self) -> bool:
        return bool(self.model and self.model.startswith("codex:"))

    # -- 수명 --------------------------------------------------------------

    def _spawn(self) -> None:
        cmd = [
            "claude", "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--tools", self.tools,
            "--allowedTools", self.tools,
        ]
        if self.isolated:
            # --bare는 구독 로그인도 생략한다. 인증은 유지하고 설정·훅·도구만 격리한다.
            cmd += ["--setting-sources", "", "--settings", '{"disableAllHooks":true}',
                    "--strict-mcp-config", "--no-session-persistence"]
        if self.system:
            cmd += ["--system-prompt" if self.isolated else "--append-system-prompt", self.system]
        if self.model:
            cmd += ["--model", self.model]
        if self.effort:
            cmd += ["--effort", self.effort]
        if self._resume:
            cmd += ["--resume", self._resume]
        if self.is_codex:
            cmd = ["codex", "exec", "--model", self.model.removeprefix("codex:"),
                   "--json", "--sandbox", "read-only",
                   "-c", 'approval_policy="never"', "--disable", "multi_agent",
                   "-c", "developer_instructions=" + json.dumps(self.system, ensure_ascii=False)]
            if self.effort:
                cmd += ["-c", "model_reasoning_effort=" + json.dumps(self.effort)]
            if self.isolated:
                cmd += ["--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                        "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"',
                        "--disable", "shell_tool", "--disable", "apps", "--disable", "plugins",
                        "--disable", "memories"]
            elif self._resume:
                cmd += ["resume", self._resume]
            cmd.append("-")
            self.model_name = self.model.removeprefix("codex:")
        self._stderr = deque(maxlen=20)
        cmd = [*cli_command(cmd[0]), *cmd[1:]]
        self._proc = subprocess.Popen(
            cmd, cwd=str(self.repo),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1,
        )
        threading.Thread(target=self._pump, args=(self._proc, self._events), daemon=True).start()
        threading.Thread(target=self._pump_stderr, args=(self._proc, self._stderr), daemon=True).start()

    def _pump(self, proc, events) -> None:
        # 이전 프로세스의 종료 알림을 다음 프로세스의 큐에 섞지 않는다.
        assert proc.stdout
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                events.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        # 프로세스가 죽으면 기다리는 쪽이 영영 안 깨어난다. 문을 닫아 준다.
        events.put({"type": "__closed__"})

    @staticmethod
    def _pump_stderr(proc, errors) -> None:
        if proc.stderr:
            for line in proc.stderr:
                errors.append(line)

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure(self) -> None:
        with self._start:
            if not self.alive:
                # 이어 붙일 세션이 있으면 그 id 를 들고 다시 뜬다. 없으면
                # 새 대화다.
                self._resume = self.session_id
                self._events = queue.Queue()
                self._spawn()

    def reconfigure(self, model: str | None, effort: str | None) -> None:
        """모델·effort 를 바꾼다. 대화는 안 잃는다.

        둘 다 띄울 때 정해지는 값이라 프로세스를 다시 띄워야 한다. 그런데
        그냥 다시 띄우면 앞의 대화가 사라지므로, 지금 세션 id 를 들고
        `--resume` 으로 붙는다. 다음 발화 때 실제로 뜬다 — 안 물어볼 채널을
        미리 띄워 둘 이유가 없다.
        """

        if (model or None) == self.model and (effort or None) == self.effort:
            return
        self.model = model or None
        self.effort = effort or None
        self.close()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)

    # -- 한 턴 -------------------------------------------------------------

    def say(self, text: str):
        """발화 하나를 보내고 이벤트를 흘린다. 한 번에 한 턴만 돈다."""

        if not self._turn.acquire(blocking=False):
            yield Event("error", "앞 턴이 아직 안 끝났다.")
            return
        completed = False
        try:
            self.ensure()
            assert self._proc and self._proc.stdin
            # 버려진 턴은 finally에서 닫는다. 시작 이벤트가 있는 큐는 비우지 않는다.
            payload = {"type": "user", "message": {
                "role": "user", "content": [{"type": "text", "text": text}]}}
            try:
                self._proc.stdin.write(text if self.is_codex else json.dumps(payload, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
                if self.is_codex:
                    self._proc.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                self.close()
                yield Event("error", "프로세스가 죽었다. 다시 보내면 새로 띄운다.")
                return
            for event in self._drain():
                completed = event.kind == "done"
                yield event
        finally:
            if self.is_codex or not completed:
                self.close()
            self._turn.release()

    def _drain(self):
        deadline = BOOT_TIMEOUT if self.session_id is None else TURN_TIMEOUT
        started = time.monotonic()
        final = ""
        while True:
            try:
                ev = self._events.get(timeout=deadline)
            except queue.Empty:
                self.close()
                yield Event("error", f"{deadline:.0f}초 안에 답이 없다.")
                return
            deadline = TURN_TIMEOUT

            kind = ev.get("type")
            if kind == "__closed__":
                err = "".join(self._stderr)[-800:]
                self.close()
                yield Event("error", f"프로세스가 닫혔다. {err}".strip())
                return

            if self.is_codex:
                if kind == "thread.started":
                    self.session_id = ev.get("thread_id") or self.session_id
                elif kind == "item.completed" and ev.get("item", {}).get("type") == "agent_message":
                    final = str(ev["item"].get("text") or "")
                elif kind == "item.started" and ev.get("item", {}).get("type") in (
                    "command_execution", "mcp_tool_call", "web_search",
                ):
                    item = ev["item"]
                    yield Event("tool", str(item.get("command") or item.get("tool") or item["type"])[:120])
                elif kind == "turn.completed":
                    usage = ev.get("usage") or {}
                    yield Event("done", final, {
                        "ms": round((time.monotonic() - started) * 1000),
                        "session_id": self.session_id, "model": self.model_name,
                        "error": not bool(final.strip()),
                        "tokens": {"in": usage.get("input_tokens"), "out": usage.get("output_tokens"),
                                   "cache_read": usage.get("cached_input_tokens")},
                    })
                    return
                elif kind in ("turn.failed", "error"):
                    error = ev.get("error") or {}
                    yield Event("error", str(error.get("message") if isinstance(error, dict) else error)
                                or str(ev.get("message") or "Codex 요청 실패"))
                    return
                continue

            if kind == "system" and ev.get("subtype") == "init":
                self.session_id = ev.get("session_id") or self.session_id
                # "기본" 을 골랐을 때 실제로 무엇이 붙었는지는 여기서만 안다.
                self.model_name = str(ev.get("model") or "")

            elif kind == "stream_event":
                inner = ev.get("event") or {}
                if inner.get("type") == "content_block_delta":
                    delta = inner.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield Event("delta", delta["text"])

            elif kind == "assistant":
                for block in _blocks(ev.get("message") or {}):
                    if block.get("type") == "tool_use":
                        yield Event("tool", _tool_brief(block))

            elif kind == "result":
                usage = ev.get("usage") or {}
                yield Event(
                    "done",
                    str(ev.get("result") or ""),
                    {"ms": ev.get("duration_ms"),
                     "error": bool(ev.get("is_error")),
                     "session_id": ev.get("session_id"),
                     "model": self.model_name,
                     # 이 위키는 주입 글자수를 노드 크기로 그릴 만큼 비용에
                     # 민감하다. effort 가 무엇을 치르는지는 여기서 보여야 한다.
                     "cost_usd": ev.get("total_cost_usd"),
                     "tokens": {
                         "in": usage.get("input_tokens"),
                         "out": usage.get("output_tokens"),
                         "cache_read": usage.get("cache_read_input_tokens"),
                         "cache_write": usage.get("cache_creation_input_tokens"),
                     }},
                )
                return


def _tool_brief(block: dict) -> str:
    """도구 한 줄. 무엇을 하고 있는지만 보이면 된다."""

    name = str(block.get("name") or "?")
    args = block.get("input") or {}
    for key in ("description", "file_path", "pattern", "path", "command"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return f"{name} · {' '.join(value.split())[:90]}"
    return name


def explain(answer: str, model: str = "", effort: str = ""):
    """원문만 새 세션에 전달한다. 검색 프롬프트·채널·대화 이력은 전달하지 않는다."""
    prompt = (Path(__file__).parent / "prompts/chat-explain.md").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="wiki-explain-") as folder:
        chat = ChatSession(Path(folder), tools="", system=prompt, model=model,
                           effort=effort, isolated=True)
        try:
            yield from chat.say(json.dumps({"source_answer": answer}, ensure_ascii=False))
        finally:
            chat.close()


def demo() -> None:
    """두 턴이 한 프로세스에서 이어지는가. 이것이 이 파일의 전제다."""

    import sys
    import time

    sys.stdout.reconfigure(encoding="utf-8")
    here = Path(__file__).resolve().parent.parent
    chat = ChatSession(here)

    # 답의 문구를 재면 표현 하나에 빨개진다. 재야 하는 것은 둘째 턴이 첫째
    # 턴을 기억하느냐이므로, 기억할 표를 하나 주고 그것만 대조한다.
    token = "MARMOT-77"

    said = []
    t0 = time.time()
    for ev in chat.say(f"이 표를 기억해라: {token}. '알겠다' 한 마디만 답해라."):
        if ev.kind == "done":
            said.append(ev.text)
    first = time.time() - t0

    t1 = time.time()
    for ev in chat.say("방금 기억하라고 한 표를 그대로 적어라. 그것만."):
        if ev.kind == "done":
            said.append(ev.text)
    second = time.time() - t1

    chat.close()
    assert len(said) == 2, said
    assert token in said[1], said[1]  # 한 프로세스가 앞 턴을 들고 있다
    print(f"ok  두 턴이 이어진다 — {first:.1f}s → {second:.1f}s")
    print(f"    1: {said[0][:60]}")
    print(f"    2: {said[1][:60]}")


if __name__ == "__main__":
    demo()
