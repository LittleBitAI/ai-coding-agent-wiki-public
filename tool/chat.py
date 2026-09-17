"""chat — Claude/Codex로 근거를 찾고, 독립 호출로 쉬운 설명을 만든다."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 윈도우에서 `mimetypes` 는 레지스트리를 읽고, 거기서 `.js` 가 흔히
# `text/plain` 이다. 그러면 `<script type="module">` 을 브라우저가 조용히
# 거부한다 — 콘솔에 아무것도 안 남고 화면만 빈다. 실제로 그렇게 한 번 비었다.
# 타입은 요청 때 조회하므로 임포트 뒤에 등록해도 늦지 않다.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chat_channels  # noqa: E402
from chat_session import ChatSession, explain  # noqa: E402
from session_state import active_page, branch_line, decisions, run  # noqa: E402
from slack_brief import repo_url  # noqa: E402

ROOT = HERE.parent
LOGS = ROOT / "raw" / "chat"
DIST = ROOT / "web" / "dist"
CORRECTIONS = ROOT / "raw" / "corrections.jsonl"
DROPPED = ROOT / "raw" / "retro-dropped.jsonl"
PY = sys.executable

MAX_REPLAY = 200  # 화면에 되살릴 지난 발화 수

_sessions: dict[tuple[str, str], ChatSession] = {}
_lock = threading.Lock()
_busy: set[str] = set()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """서버가 내려가면 자식도 내린다. 안 그러면 `claude.exe` 가 쌓인다.

    Ctrl+C 나 정상 종료에서만 돈다. 강제 종료(작업 관리자·킬)에는 못 걸리므로
    그때는 자식이 남는다 — 어떤 언어로도 못 잡는 자리다.
    """

    yield
    with _lock:
        alive = list(_sessions.values())
        _sessions.clear()
    for chat in alive:
        chat.close()


app = FastAPI(title="wiki chat", lifespan=lifespan)


# 프로젝트 선택은 모든 채널이 공유한다. 문맥과 모델 설정은 프로젝트·채널별이다.
_config: dict[tuple[str, str], dict] = {}
_project: str | None = None


def project() -> str:
    global _project
    if _project is None:
        path = LOGS / "project.json"
        name = json.loads(path.read_text(encoding="utf-8")) if path.exists() else chat_channels.WIKI.name
        if not isinstance(name, str):
            raise HTTPException(409, "저장된 프로젝트 설정을 읽을 수 없습니다")
        _project = name
    return _project


def session_key(cid: str) -> tuple[str, str]:
    return (str(repo_of(cid)), cid)


def config(cid: str) -> dict:
    key = (project(), cid)
    if key not in _config:
        channel = chat_channels.get(cid)
        model = chat_channels.LOCAL.get("model", channel.model)
        effort = channel.effort
        if model.startswith("codex:"):
            try:
                selected = next(m for m in chat_channels.codex_models() if m["id"] == model)
                if effort not in {e["id"] for e in selected["efforts"]}:
                    effort = selected["default_effort"]
            except Exception as exc:
                raise HTTPException(503, "기본 Codex 모델을 확인할 수 없습니다. 설치 명령을 다시 실행하세요.") from exc
        _config[key] = {"repo": project(),
                        "model": model,
                        "effort": effort}
    return _config[key]


def session(cid: str) -> ChatSession:
    """채널의 살아 있는 대화. 없으면 띄운다.

    채널 소개는 시스템 프롬프트로 간다. 첫 턴으로 태웠더니 그 한 턴이 2분을
    먹었고(모델이 소개를 읽고 파일을 뒤진다) 실제 물음의 답은 6초였다.

    죽은 프로세스는 **새 객체로 갈지 않는다.** 갈면 그 객체가 들고 있던
    `session_id` 가 같이 버려지고, 그러면 `--resume` 이 걸릴 자리가 없어서
    모델·effort 를 바꿀 때마다 대화가 조용히 사라진다. 실제로 그랬다 —
    응답은 `kept: True` 인데 세션 id 가 갈렸다. 되살리는 것은 `ensure` 가 한다.

    다른 프로젝트로 갔다 돌아와도 같은 프로젝트·채널의 객체를 다시 쓴다.
    """

    with _lock:
        key = session_key(cid)
        chat = _sessions.get(key)
        if chat is None:
            channel = chat_channels.get(cid)
            cfg = config(cid)
            repo = repo_of(cid)
            chat = ChatSession(repo, system=chat_channels.ANSWER_PROMPT + "\n\n" + channel.preamble,
                               model=cfg["model"], effort=cfg["effort"])
            # 서버 재시작도 문맥 지우기가 아니다. 명시적 초기화 뒤의 같은 CLI만 재개한다.
            for row in reversed(recall(cid, include_context=True)):
                if row.get("role") == "context":
                    break
                if row.get("session_id"):
                    provider = row.get("provider") or ("claude" if str(row.get("model", "")).startswith("claude-") else "codex")
                    if provider == ("codex" if chat.is_codex else "claude"):
                        chat.session_id = row["session_id"]
                    break
            _sessions[key] = chat
        return chat


# -- 기록 -----------------------------------------------------------------
# DB 를 안 쓴다. 혼자 쓰는 localhost 에서 jsonl 한 줄이 못 하는 것이 없다.

def remember(cid: str, role: str, text: str, error: str = "", **extra) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.time(), "role": role, "text": text, "repo": str(repo_of(cid)), **extra}
    if error:
        row["error"] = error
    with (LOGS / f"{cid}.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def recall(cid: str, legacy: bool = False, include_context: bool = False) -> list[dict]:
    path = LOGS / f"{cid}.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            belongs = not row.get("repo") if legacy else row.get("repo") == str(repo_of(cid))
            if belongs and (include_context or row.get("role") in ("user", "assistant")):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows[-MAX_REPLAY:]


# -- API ------------------------------------------------------------------

class Say(BaseModel):
    text: str


class Config(BaseModel):
    repo: str
    model: str = ""
    effort: str = ""


@app.get("/api/options")
def options() -> dict:
    """화면이 고를 수 있는 것 전부."""

    codex, error = [], ""
    try:
        codex = chat_channels.codex_models()
    except Exception as exc:
        error = f"Codex 모델 목록을 불러오지 못했습니다: {exc}"
    return {"projects": chat_channels.projects(),
            "models": chat_channels.MODELS + codex,
            "efforts": chat_channels.EFFORTS, "codex_error": error}


@app.get("/api/channels")
def channels() -> list[dict]:
    return [
        {"id": c.id, "label": c.label, "blurb": c.blurb,
         "live": session_key(c.id) in _sessions and _sessions[session_key(c.id)].alive,
         "model_name": _sessions[session_key(c.id)].model_name if session_key(c.id) in _sessions else "",
         # 답에 나오는 SHA 를 커밋 링크로 만들 때 쓴다. 리모트가 없으면 빈 값.
         "remote": repo_url(repo_of(c.id)),
         **config(c.id)}
        for c in chat_channels.CHANNELS
    ]


@app.post("/api/config/{cid}")
def configure(cid: str, body: Config) -> dict:
    """프로젝트는 전체 채널에, 모델·effort는 선택한 프로젝트의 채널에 적용한다."""
    global _project

    if cid not in chat_channels.BY_ID:
        raise HTTPException(404, "그런 채널이 없다")
    if chat_channels.repo_for(body.repo) is None:
        raise HTTPException(400, f"그런 저장소가 없다: {body.repo}")
    models = chat_channels.MODELS
    if body.model.startswith("codex:"):
        try:
            models = chat_channels.codex_models()
        except Exception as exc:
            raise HTTPException(503, f"Codex 모델 목록 확인 실패: {exc}") from exc
    selected = next((m for m in models if m["id"] == body.model), None)
    if selected is None:
        raise HTTPException(400, "지원하지 않는 모델 선택")
    efforts = {e["id"] for e in selected.get("efforts", chat_channels.EFFORTS)}
    if body.effort not in efforts:
        raise HTTPException(400, "이 모델이 지원하지 않는 effort")

    with _lock:
        switched = body.repo != project()
        if cid in _busy or (switched and _busy):
            raise HTTPException(409, "답변 생성이 끝난 뒤 설정을 바꿔 주세요")
        if switched:
            # 기록 중인 턴이 없을 때만 바꾼다. 디스크 쓰기 실패 시 선택도 그대로다.
            LOGS.mkdir(parents=True, exist_ok=True)
            path = LOGS / "project.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(body.repo, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(path)
            _project = body.repo
        cfg = config(cid)
        moved = not switched and body.model.startswith("codex:") != cfg["model"].startswith("codex:")
        if not switched:
            cfg.update(model=body.model, effort=body.effort or selected.get("default_effort", ""))
        key = session_key(cid)
        if moved:
            remember(cid, "context", "CLI 변경")
        chat = _sessions.pop(key, None) if moved else _sessions.get(key)
        inactive = [s for (repo, _), s in _sessions.items() if repo != key[0]] if switched else []
    for old in inactive:
        old.close()  # session_id는 남겨 두고 돌아오면 --resume으로 재개한다.
    if chat is not None:
        if moved:
            chat.close()
        else:
            chat.reconfigure(cfg["model"], cfg["effort"])
    return {"kept": not moved, "switched": switched, **cfg}


@app.get("/api/log/{cid}")
def log(cid: str, legacy: bool = False) -> list[dict]:
    if cid not in chat_channels.BY_ID:
        raise HTTPException(404, "그런 채널이 없다")
    return recall(cid, legacy)


@app.post("/api/reset/{cid}")
def reset(cid: str) -> dict:
    if cid not in chat_channels.BY_ID:
        raise HTTPException(404, "그런 채널이 없다")
    with _lock:
        if cid in _busy:
            raise HTTPException(409, "답변 생성이 끝난 뒤 대화를 초기화해 주세요")
        remember(cid, "context", "사용자가 문맥 지우기")
        chat = _sessions.pop(session_key(cid), None)
    if chat:
        chat.close()
    return {"ok": True}


@app.post("/api/say/{cid}")
def say(cid: str, body: Say) -> StreamingResponse:
    if cid not in chat_channels.BY_ID:
        raise HTTPException(404, "그런 채널이 없다")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "빈 발화")
    with _lock:
        if cid in _busy:
            raise HTTPException(409, "이 채널의 답변을 생성하고 있습니다")
        _busy.add(cid)
        cfg = dict(config(cid))

    def stream():
        answer: list[str] = []
        failed = ""
        simple = ""
        simple_error = ""
        finished = False
        metadata = {}
        simple_meta = {}
        try:
            remember(cid, "user", text)
            # 관련 규칙의 표시용 대조이며 실제 호스트 주입 확인은 아니다.
            pages = hits_for(cid, text)
            if pages:
                yield sse({"kind": "hits", "text": "", "pages": pages})
            for ev in session(cid).say(text):
                if ev.kind == "delta":
                    answer.append(ev.text)
                # 한도·API 오류는 `done` 에 error=True 로 온다. 본문이 아니라 오류다.
                # 부분 답과 따로 들지 않으면 되살렸을 때 왜 끊겼는지가 사라진다 —
                # 세션 한도에 걸린 회고가 "세겠습니다" 한 줄로만 남았다.
                if ev.kind == "done" and ev.meta.get("error"):
                    failed = ev.text or "완료된 답변이 없습니다"
                    yield sse({"kind": "error", "text": failed, **ev.meta})
                    break
                if ev.kind == "error":
                    failed = ev.text
                if ev.kind == "done":
                    answer = [ev.text or "".join(answer)]
                    finished = bool(answer[0].strip())
                    metadata = ev.meta
                    metadata.pop("error", None)
                yield sse({"kind": ev.kind, "text": ev.text, **ev.meta})
            if not finished and not failed:
                failed = "답변 생성이 완료되지 않았습니다"
                yield sse({"kind": "error", "text": failed})
            if finished and not failed:
                yield sse({"kind": "simple_start", "text": ""})
                try:
                    simple_finished = False
                    for ev in explain("".join(answer), cfg["model"], cfg["effort"]):
                        if ev.kind == "delta":
                            simple += ev.text
                        elif ev.kind == "done":
                            if ev.meta.get("error") or not ev.text.strip():
                                raise ValueError(ev.text or "쉬운 설명이 비어 있습니다")
                            simple = ev.text
                            simple_finished = True
                            simple_meta = ev.meta
                        elif ev.kind == "error":
                            raise ValueError(ev.text)
                        if ev.kind in ("delta", "done"):
                            yield sse({"kind": "simple_" + ev.kind, "text": ev.text, **ev.meta})
                    if not simple_finished:
                        raise ValueError("쉬운 설명 생성이 완료되지 않았습니다")
                except Exception as exc:
                    simple, simple_error = "", f"{type(exc).__name__}: {exc}"
                    yield sse({"kind": "simple_error", "text": simple_error})
        except Exception as exc:  # 스트림이 끊겨도 화면은 이유를 받아야 한다
            failed = f"{type(exc).__name__}: {exc}"
            yield sse({"kind": "error", "text": failed})
        finally:
            try:
                if answer or failed:
                    remember(cid, "assistant", "".join(answer), failed,
                             simple_text=simple, simple_error=simple_error, simple_meta=simple_meta,
                             provider="codex" if cfg["model"].startswith("codex:") else "claude", **metadata)
            finally:
                with _lock:
                    _busy.discard(cid)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


# -- 트리거 히트 ------------------------------------------------------------

def repo_of(cid: str) -> Path:
    repo = chat_channels.repo_for(project())
    if repo is None:
        raise HTTPException(409, "선택한 프로젝트를 찾을 수 없습니다")
    return repo


def hits_for(cid: str, text: str) -> list[str]:
    """표시용 트리거 대조. 실제 호스트 주입의 증거가 아니며 훅을 재실행하지 않는다."""
    from inject import label, match_pages, pages
    repo = repo_of(cid)
    try:
        return [label(path) for _severity, _body, path in match_pages(text, pages(repo.name, repo))]
    except Exception:
        return []


# -- 어긋났다 ---------------------------------------------------------------

class Mark(BaseModel):
    kind: str            # 교정 · 재입력 · 부분수행 · 되돌림
    user_text: str
    assistant_text: str = ""
    session_id: str = ""


KINDS = ("교정", "재입력", "부분수행", "되돌림")


@app.post("/api/mark/{cid}")
def mark(cid: str, body: Mark) -> dict:
    """틀린 그 순간에 사람이 표시한다. census 형식 그대로 쌓인다.

    census 는 세션 수십 개가 쌓여야 말하고, 표지 정규식의 편향을 탄다. 틀린
    순간에 사람이 부류를 찍으면 둘 다 없다. `raw/corrections.jsonl` 은 census
    출력과 같은 열(session · order · at · chars · text)을 갖고 `kind` 가 더 있다.
    """

    if cid not in chat_channels.BY_ID:
        raise HTTPException(404, "그런 채널이 없다")
    if body.kind not in KINDS:
        raise HTTPException(400, f"부류는 {' · '.join(KINDS)} 중 하나")
    CORRECTIONS.parent.mkdir(parents=True, exist_ok=True)
    order = sum(1 for _ in CORRECTIONS.open(encoding="utf-8")) if CORRECTIONS.exists() else 0
    row = {
        "session": body.session_id or f"chat:{cid}",
        "order": order,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "chars": len(body.user_text),
        "text": body.user_text,
        "kind": body.kind,
        "channel": cid,
        "repo": config(cid)["repo"],
        "answer": body.assistant_text[:600],
    }
    with CORRECTIONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True, "total": order + 1}


# -- 인계 -------------------------------------------------------------------

@app.post("/api/handoff/{cid}")
def handoff(cid: str) -> dict:
    """다음 세션에 붙일 프롬프트. census 가 20회 센 요청이다.

    기계가 셀 수 있는 것만 든다 — 브랜치 · 열린 계획 · 최근 결정 · 미커밋 변경 ·
    이 채널의 마지막 대화. "다음에 무엇을" 은 사람이 한 줄 더한다. 그 한 줄을
    기계가 지으면 틀린 것을 자신 있게 넘긴다.
    """

    if cid not in chat_channels.BY_ID:
        raise HTTPException(404, "그런 채널이 없다")
    repo = repo_of(cid)
    lines = [f"# 인계 — `{repo.name}` · {dt.date.today():%Y-%m-%d}", "",
             "## 지금", "", f"브랜치 {branch_line(repo)}"]

    changed = run(repo, "status", "--short")
    stat = run(repo, "diff", "--shortstat")
    if changed:
        lines += ["", "## 미커밋 변경", "", "```", changed, "```"]
        if stat:
            lines.append(stat)

    body, stale = active_page(repo)
    if body:
        lines += ["", "## 열린 계획 (`.wiki/plan-active.md`)", ""]
        if stale:
            lines.append(f"**낡았을 수 있다** — `{'`, `'.join(stale)}` 가 더 나중에 고쳐졌다.\n")
        lines.append(body)

    recent = decisions(repo)
    if recent:
        lines += ["", "## 최근 결정 — 뒤집기 전에 이유를 보라", ""]
        lines += [f"- {t} — {w}" if w else f"- {t}" for t, w in recent]

    tail = [r for r in recall(cid) if r.get("role") in ("user", "assistant")][-6:]
    if tail:
        lines += ["", f"## 이 채널(#{chat_channels.get(cid).label})에서 방금까지", ""]
        for r in tail:
            who = "나" if r["role"] == "user" else "답"
            text = " ".join(str(r.get("text", "")).split())
            lines.append(f"- **{who}**: {text[:400]}{' …' if len(text) > 400 else ''}")

    lines += ["", "## 다음에 할 것", "", "(여기부터 저기까지 — 사람이 한 줄 적는다)"]
    return {"text": "\n".join(lines)}


# -- 결정 -------------------------------------------------------------------

class Decide(BaseModel):
    candidate: str
    target: str          # wiki · claude_md · drop


def oneshot(repo: Path, prompt: str, system: str, tools: str, timeout: int = 600) -> dict:
    """버튼 한 번에 한 턴. 쓰기가 허용되는 유일한 경로다.

    채널 프로세스는 Edit·Write 가 없다 — 브라우저에서 열리는 것이 파일을 고치면
    원격 셸이다. 이 함수는 사람이 버튼을 눌러 **이 후보 하나**를 지목했을 때만
    돌고, 무엇이 바뀌었는지를 돌려준다. 버튼이 곧 허가다.
    """

    cmd = ["claude", "-p", prompt, "--output-format", "json",
           "--allowedTools", tools, "--append-system-prompt", system, "--effort", "high"]
    try:
        done = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        out = json.loads(done.stdout or "{}")
        return {"text": str(out.get("result") or ""), "error": bool(out.get("is_error")),
                "cost_usd": out.get("total_cost_usd")}
    except subprocess.TimeoutExpired:
        return {"text": f"{timeout}초 안에 안 끝났다.", "error": True}
    except Exception as exc:
        return {"text": f"{type(exc).__name__}: {exc}", "error": True}


WIKI_WRITER = (
    "너는 위키 페이지를 쓰는 사람이다. 받은 후보 하나만 다룬다. `SCHEMA.md` 의 "
    "'페이지의 최소 구조' 를 그대로 따른다 — front matter 에 scope·severity·"
    "triggers·slots·sources·links, 본문은 제목 · 규칙 · 왜 · 어겼을 때. "
    "severity 는 근거대로 — landmine 은 sources 없이 못 붙인다. "
    "후보에 '이미 페이지 있음' 이 적혀 있으면 **새로 만들지 말고** 그 페이지를 "
    "열어 사다리를 올려라(`enforce.deny` 나 트리거 보강). 파일 하나만 만들거나 "
    "고친다. 끝나면 `python tool/lint.py --repo <프로젝트 경로>` 를 돌리고 그 "
    "결과와 무엇을 어디에 썼는지를 마지막에 적어라."
)
CLAUDE_MD_WRITER = (
    "너는 이 저장소의 `CLAUDE.md` **한 파일만** 고치는 사람이다. 받은 후보 하나만 "
    "다룬다. 알맞은 절을 찾아 그 아래에 한 문장, 명령형으로. 이미 같은 뜻의 문장이 "
    "있으면 더하지 말고 그 문장을 짚어라. "
    "**다른 파일은 어떤 이유로도 건드리지 마라** — 알맞은 자리가 없으면 없다고 "
    "답하고 끝내라. 끝에 무엇을 어디에 썼는지 한 줄."
)


@app.post("/api/decide/{cid}")
def decide(cid: str, body: Decide) -> dict:
    """회고 후보 하나의 운명. `retrospect` 스킬 5번 걸음이 여기서 닫힌다.

    스킬은 '선택지로 물어라' 고 적었는데 헤드리스는 못 묻는다. 이 앱은 묻는다.
    """

    if cid not in chat_channels.BY_ID:
        raise HTTPException(404, "그런 채널이 없다")
    candidate = body.candidate.strip()
    if not candidate:
        raise HTTPException(400, "빈 후보")
    repo = repo_of(cid)

    if body.target == "drop":
        DROPPED.parent.mkdir(parents=True, exist_ok=True)
        with DROPPED.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": time.time(), "channel": cid, "repo": repo.name,
                                 "candidate": candidate}, ensure_ascii=False) + "\n")
        return {"text": "버렸다. 다음에 또 나면 그때 다시 본다.", "error": False}

    if body.target == "wiki":
        result = oneshot(chat_channels.WIKI,
                         f"후보: {candidate}\n대상 프로젝트 경로: {repo}",
                         WIKI_WRITER, "Read,Glob,Grep,Write,Edit,Bash")
        result["changed"] = run(chat_channels.WIKI, "status", "--short")
        return result

    if body.target == "claude_md":
        # 없으면 안 만든다. 산문으로 "다른 곳은 건드리지 마라" 라고만 했더니
        # CLAUDE.md 가 없는 저장소에서 **위키 페이지를 대신 고쳤다.** 이 위키의
        # 논지 그대로다 — 산문은 안 지켜지고 지켜지는 것은 막히는 것이다.
        # 그래서 여기서 먼저 막고, 허용 도구도 그 파일 하나로 좁힌다.
        if not (repo / "CLAUDE.md").exists():
            return {"text": f"`{repo.name}` 에는 `CLAUDE.md` 가 없다. "
                            "다른 파일을 대신 고치지 않았다.", "error": True}
        result = oneshot(repo, f"후보: {candidate}", CLAUDE_MD_WRITER,
                         "Read,Grep,Edit(CLAUDE.md)")
        result["changed"] = run(repo, "diff", "--stat")
        return result

    raise HTTPException(400, "target 은 wiki · claude_md · drop 중 하나")


# -- 파일 들여다보기 ---------------------------------------------------------

@app.get("/api/file")
def peek(repo: str, path: str, line: int = 1, around: int = 25) -> dict:
    """인용된 `경로:줄` 을 눌렀을 때 그 자리를 보여 준다. 저장소 밖은 안 준다."""

    base = chat_channels.repo_for(repo)
    if base is None:
        raise HTTPException(400, "그런 저장소가 없다")
    target = (base / path).resolve()
    if base.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "그 파일이 없다")
    if target.stat().st_size > 2_000_000:
        raise HTTPException(413, "너무 크다")
    rows = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, line - around)
    end = min(len(rows), line + around)
    return {"path": path, "start": start, "line": line, "total": len(rows),
            "lines": rows[start - 1:end]}


# -- 화면 -----------------------------------------------------------------

@app.get("/api/graph")
def wiki_graph() -> FileResponse:
    """정책 그래프. `graph.py` 가 낸 `graph.json` 을 그대로 준다.

    오래 여기서 `wiki.html` 을 통째로 줬다. 그러면 파이썬이 화면을 만들고 이
    앱이 그것을 iframe 으로 감싸는 두 겹이 되고, 같은 그래프를 그리는 코드가 두
    벌이 된다. 서버는 자료만 주고 그리는 것은 화면이 한다.
    """

    page = chat_channels.WIKI / "graph.json"
    if not page.exists():
        raise HTTPException(404, "python tool/graph.py 를 먼저 돌려라")
    return FileResponse(page, media_type="application/json")


if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def index() -> dict:
        return {"화면이 아직 없다": "npm --prefix web run build 를 먼저 돌려라"}


def taken(host: str, port: int) -> bool:
    """그 포트에 이미 누가 듣고 있나."""

    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def demo() -> None:
    """모델·effort 를 바꿔도 대화가 남는가. 한 번 조용히 안 남았던 자리다.

    HTTP 를 안 태운다. 버그는 `session()` 이 죽은 프로세스를 새 객체로 갈아서
    `session_id` 를 버린 것이었고, 그건 이 두 함수만 불러도 재현된다.

        python tool/chat.py --check
    """

    cid = "wiki"
    token = "QUOKKA-9"
    reset(cid)
    try:
        first = last = {}
        for ev in session(cid).say(f"이 표를 기억해라: {token}. '알겠다' 한 마디만."):
            if ev.kind == "done":
                first = ev.meta

        answer = configure(cid, Config(repo=config(cid)["repo"], effort="max"))
        assert answer["kept"], answer

        text = ""
        for ev in session(cid).say("아까 기억하라고 한 표를 그대로 적어라. 그것만."):
            if ev.kind == "done":
                text, last = ev.text, ev.meta

        assert first.get("session_id"), first
        assert first["session_id"] == last.get("session_id"), (first, last)
        assert token in text, text
        print(f"ok  effort 를 바꿔도 대화가 남는다 — session {first['session_id']}")
        print(f"    되찾은 표: {text.strip()[:40]}")
    finally:
        reset(cid)


def main() -> int:
    import uvicorn

    # 포트 안내도 자체 점검 출력도 한글이다. 인코딩을 환경에 안 맡긴다 —
    # 이 저장소가 cp949 한 글자에 여덟 번 데인 자리다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser()
    # 8000 은 이 기계에서 다른 프로젝트가 잡고 있다 (어댑터에 적혀 있다).
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--workspace", type=Path, help="프로젝트들이 들어 있는 폴더")
    # 127.0.0.1 에 묶는다. 이 서버는 인증이 없고, 인증 없이 LAN 에 여는 것은
    # 채팅이 아니라 남에게 셸을 주는 것이다.
    ap.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    ap.add_argument("--check", action="store_true", help="자체 점검만 하고 끝낸다")
    args = ap.parse_args()

    if args.workspace:
        chat_channels.WORKSPACE = args.workspace.expanduser().resolve()
    if not chat_channels.WORKSPACE.is_dir():
        ap.error("프로젝트 폴더가 없습니다. --workspace로 실제 폴더를 지정하세요.")
    # 위키 자신을 가리키면 그 아래에 저장소가 없어 목록이 위키 한 장으로 조용히 줄어든다.
    if chat_channels.WORKSPACE == chat_channels.WIKI:
        ap.error("프로젝트 폴더가 위키 자신입니다. 프로젝트들이 들어 있는 상위 폴더를 지정하세요: "
                 f"{chat_channels.WIKI.parent}")

    if args.check:
        demo()
        return 0

    # 포트가 막히면 uvicorn 은 영문 한 줄을 찍고 코드 1 로 끝난다. 더블클릭한
    # 창은 그 줄을 읽기 전에 닫히고, 그래서 "켜지다가 그냥 꺼진다" 로 보인다.
    # 실제로 그렇게 한 번 꺼졌다. 무엇이 막혔고 어떻게 푸는지를 먼저 말한다.
    if taken(args.host, args.port):
        print(
            f"\n{args.port} 번 포트를 이미 누가 듣고 있다. 그래서 안 뜬다.\n\n"
            f"  누구인지 본다   netstat -ano | findstr :{args.port}\n"
            f"  그것을 내린다   taskkill /pid <위에서 본 PID> /f\n"
            f"  다른 포트로     tool\\chat.cmd --port 9090\n",
            file=sys.stderr,
        )
        return 1

    print(f"http://{args.host}:{args.port}  — 끄려면 Ctrl+C")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
