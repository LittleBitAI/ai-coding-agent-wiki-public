"""채널 정의와 고를 수 있는 것들 — 프로젝트 · 모델 · effort."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

from chat_local import cli_command, settings

WIKI = Path(__file__).resolve().parent.parent
LOCAL = settings()
WORKSPACE = (WIKI / Path(LOCAL.get("workspace", "..")).expanduser()).resolve()

# CLI 가 `--model` 에서 이름으로 받는 것들. 빈 값은 플래그를 안 붙인다는 뜻이고,
# 그러면 CLI 의 기본 모델이 쓰인다.
MODELS = [
    {"id": "", "label": "Claude 기본", "note": "Claude CLI 가 정한 것"},
    {"id": "opus", "label": "Opus", "note": "제일 세다. 제일 느리다"},
    {"id": "sonnet", "label": "Sonnet", "note": "보통 이거면 된다"},
    {"id": "haiku", "label": "Haiku", "note": "짧은 확인용"},
    {"id": "fable", "label": "Fable", "note": ""},
]

# `--effort` 가 받는 다섯. 위로 갈수록 더 오래 생각하고 더 많이 쓴다.
EFFORTS = [
    {"id": "", "label": "기본", "note": "CLI 가 정한 것"},
    {"id": "low", "label": "low", "note": "빠른 사실 확인"},
    {"id": "medium", "label": "medium", "note": ""},
    {"id": "high", "label": "high", "note": "원인을 캐야 할 때"},
    {"id": "xhigh", "label": "xhigh", "note": ""},
    {"id": "max", "label": "max", "note": "제일 비싸다"},
]

ANSWER_PROMPT = (WIKI / "tool/prompts/chat-answer.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def codex_models() -> list[dict]:
    """설치된 Codex의 공개 모델 목록. 서버 수명 동안 캐시하며 실패는 캐시하지 않는다."""
    proc = subprocess.Popen(
        [*cli_command("codex"), "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
    )
    replies: queue.Queue = queue.Queue()

    def read():
        for line in proc.stdout:
            try:
                replies.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        replies.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + 25

    def request(rid, method, params):
        proc.stdin.write(json.dumps({"id": rid, "method": method, "params": params}) + "\n")
        proc.stdin.flush()
        while True:
            try:
                message = replies.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise RuntimeError("Codex 모델 목록 응답 시간 초과") from exc
            if message is None:
                raise RuntimeError("Codex 모델 목록 연결 종료")
            if message.get("id") == rid:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message["result"]

    try:
        request(1, "initialize", {"clientInfo": {"name": "wiki-chat", "version": "0.1.0"}})
        proc.stdin.write('{"method":"initialized"}\n')
        proc.stdin.flush()
        models, cursor, rid = [], None, 2
        while True:
            result = request(rid, "model/list", {"limit": 100, "includeHidden": False, "cursor": cursor})
            for model in result["data"]:
                default = model["defaultReasoningEffort"]
                models.append({
                    "id": "codex:" + model["model"], "label": model["displayName"], "note": "Codex",
                    "default_effort": default,
                    "is_default": model.get("isDefault", False),
                    "efforts": [{"id": "", "label": f"기본 ({default})", "note": ""}] + [
                        {"id": e["reasoningEffort"], "label": e["reasoningEffort"], "note": ""}
                        for e in model["supportedReasoningEfforts"]
                    ],
                })
            cursor = result.get("nextCursor")
            if not cursor:
                break
            rid += 1
        if not models:
            raise RuntimeError("Codex가 사용 가능한 모델을 반환하지 않았습니다")
        return models
    finally:
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        reader.join(timeout=1)
        proc.stdout.close()


def projects() -> list[dict]:
    """고를 수 있는 저장소. 워크스페이스에서 `.git` 이 있는 것만.

    목록을 손으로 안 든다 — 저장소가 늘 때마다 여기를 고치는 것은
    곧 안 고치는 것이다. 어댑터가 있는 것은 표시해 준다. 그 저장소는 위키가 이미 붙어 있어
    훅과 주입이 도는 자리다.
    """

    known = {p.stem for p in (WIKI / "adapters").glob("*.toml")}
    found = [{"id": WIKI.name, "path": str(WIKI), "wired": True}]
    for path in sorted(WORKSPACE.iterdir()) if WORKSPACE.is_dir() else []:
        if path.name == WIKI.name or not (path / ".git").exists() or repo_for(path.name) is None:
            continue
        found.append({
            "id": path.name,
            "path": str(path),
            "wired": path.name in known or (path / ".wiki/adapter.toml").is_file(),
        })
    return found


def repo_for(name: str) -> Path | None:
    """이름으로 저장소 경로. 워크스페이스 밖은 안 준다 — 화면에서 온 값이다."""

    if not name:
        return None
    if name == WIKI.name:
        return WIKI
    path = (WORKSPACE / name).resolve()
    if name != path.name or path.parent != WORKSPACE.resolve() or not (path / ".git").exists():
        return None
    return path


@dataclass(frozen=True)
class Channel:
    id: str
    label: str
    blurb: str
    preamble: str
    model: str = ""     # 기본 모델
    effort: str = ""    # 기본 effort


CHANNELS: list[Channel] = [
    Channel(
        id="progress",
        label="진척도",
        blurb="무엇이 닫혔고 다음이 무엇인가",
        effort="low",   # 읽고 옮기는 일이라 깊이 생각할 게 없다
        preamble=(
            "Focus: repository progress and plans. Read `.wiki/plan-active.md` first "
            "and follow the progress skill's document order. Use commits to verify "
            "claims, not to replace the plan. Cite each status claim. Read existing "
            "metrics instead of recalculating them. Keep the answer concise."
        ),
    ),
    Channel(
        id="diagnose",
        label="진단",
        blurb="왜 안 되나 — 기록부터 본다",
        effort="high",  # 원인을 캐는 자리다
        preamble=(
            "Focus: diagnosis. Follow `.wiki/telemetry.md`. Before interpreting code, "
            "inspect available `.omm/`, `data/latency_logs/`, Langfuse, and "
            "`artifacts/live/*.jsonl` evidence. Code shows what could happen; logs "
            "show what ran. Label hypotheses and state the observation needed to "
            "confirm them. Report unavailable sources explicitly."
        ),
    ),
    Channel(
        id="retro",
        label="회고",
        blurb="오늘 어긋난 자리를 센다",
        effort="high",
        preamble=(
            "Focus: retrospective. Follow the retrospect skill. Read today's commits "
            "and count corrections, repeated input, partial completion, and reversals "
            "in session logs. Use the wiki's `tool/transcript.py --project <repository>` "
            "to extract user turns and tool counts instead of loading entire logs. "
            "Do not list accomplishments or edit files. End with a fenced block "
            "labeled `retro-candidates`, one candidate per line (empty if none). "
            "Each line: Korean category, count with the Korean occurrence unit, "
            "middle dot, imperative rule, middle dot, existing page ID or a Korean "
            "label meaning new candidate. A repeated violation of an existing page "
            "calls for stronger enforcement, not duplicated prose."
        ),
    ),
    Channel(
        id="review",
        label="리뷰",
        blurb="PR 번호를 주면 리뷰 라운드를 낸다",
        effort="high",
        preamble=(
            "Focus: read-only code review. For a PR, read `gh pr view <n>` and "
            "`gh pr diff <n>`; for a local branch inspect its actual diff. Follow "
            "`operator/codex-review-loop`. Findings use `[P0|P1|P2] path:line`, "
            "trigger, defect, impact, and reproducible evidence. Do not invent "
            "findings. If none, state that there are no new findings in Korean. "
            "Check the disposition of prior findings first. End with a justified "
            "merge recommendation in Korean. Do not edit or merge."
        ),
    ),
    Channel(
        id="wiki",
        label="위키",
        blurb="위키와 도구 자체를 본다",
        preamble=(
            "Focus: the wiki and its tools. Read the contracts in `SCHEMA.md` and "
            "the five enforcement levels in `ENFORCEMENT.md`. Before proposing a "
            "new page, establish that the documented admission threshold is met; "
            "additional pages have a context cost."
        ),
    ),
]

BY_ID = {c.id: c for c in CHANNELS}


def get(cid: str) -> Channel:
    if cid not in BY_ID:
        raise KeyError(cid)
    return BY_ID[cid]
