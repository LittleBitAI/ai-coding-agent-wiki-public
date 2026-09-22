"""SessionStart 훅 — 세션을 "지금 어디인가" 를 아는 채로 시작하게 한다."""

from __future__ import annotations

import hook_diagnostics  # noqa: F401 -- 진입점의 제한 시간 전 스택 보존
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import translate  # noqa: E402
from wikilib import front_matter  # noqa: E402

MAX_PLANS = 2       # 계획 문서를 몇 개까지 볼 것인가
MAX_ROWS = 8        # 한 계획에서 미완 행 몇 개까지
MAX_DECISIONS = 4   # 최근 결정 몇 건

# 번역 전체에 주는 시간. 훅 예산 25초 아래에 둔다 — 넘기면 번역이 아니라
# 주입 전체를 잃는다. 못 끝낸 문자열은 한국어 원문으로 나간다.
BUDGET = 18.0


def run(repo: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        return done.stdout.strip() if done.returncode == 0 else ""
    except Exception:
        return ""


def branch_line(repo: Path, english: bool = False) -> str:
    """기본은 한국어다. 영어는 부르는 쪽이 명시적으로 고른다.

    `slack_brief.standup` 과 `chat.handoff` 가 이 함수를 같이 쓰고, 둘 다
    사람이 읽는 화면에 그대로 싣는다. 여기서 언어를 바꾸면 에이전트 컨텍스트
    하나를 고치려다 Slack 과 웹 인계까지 영어가 된다.

    번역기에 안 태운다. 우리가 만드는 고정 문자열이라 영어 표기를 그냥 적으면
    되고, 세션 시작마다 왕복 하나를 아낀다.
    """

    branch = run(repo, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    dirty = run(repo, "status", "--porcelain")
    ahead = run(repo, "rev-list", "--count", "@{u}..HEAD") if branch != "?" else ""
    bits = [f"`{branch}`"]
    if ahead and ahead != "0":
        bits.append(f"{ahead} unpushed" if english else f"미푸시 {ahead}")
    if dirty:
        count = len(dirty.splitlines())
        bits.append(f"{count} changed" if english else f"변경 {count}개")
    else:
        bits.append("worktree clean" if english else "워크트리 깨끗")
    return " · ".join(bits)


def open_steps(path: Path) -> list[str]:
    """계획 문서의 `## 단계` 표에서 아직 안 끝난 행.

    이 저장소의 계획 문서는 단계마다 상태 칸을 갖는다. 완료도 취소도 아닌 행이
    지금 남은 일이다. 표가 없으면 빈 목록이고, 그때는 아무 말도 안 한다 —
    형식을 못 읽었는데 읽은 척하면 틀린 것을 자신 있게 말하게 된다.
    """

    text = path.read_text(encoding="utf-8")
    block = re.search(r"^##+ 단계\s*$(.*?)(?=^##+ |\Z)", text, re.M | re.S)
    if not block:
        return []
    rows = []
    for line in block.group(1).splitlines():
        if not line.startswith("|") or set(line) <= set("|- :"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("#", ""):
            continue
        state = cells[-1].replace("*", "").strip()
        if state in ("완료", "취소", "상태") or "~~" in cells[1]:
            continue
        rows.append(f"{cells[0]} {cells[2] if len(cells) > 2 else ''} — {state or '미착수'}")
    return rows[:MAX_ROWS]


def plans(repo: Path) -> list[tuple[Path, list[str]]]:
    directory = repo / "docs" / "plans"
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.md"), reverse=True):
        steps = open_steps(path)
        if steps:
            found.append((path, steps))
        if len(found) >= MAX_PLANS:
            break
    return found


def active_page(repo: Path) -> tuple[str, list[str]]:
    """`.wiki/plan-active.md` 와 그것이 낡았는지.

    자유 형식 계획 문서를 기계가 파싱하면 없는 것을 있다고 말한다. 실제로 한
    저장소의 계획은 `## 단계` 표가 다 끝났는데 남은 일은 상태 칸이 없는 다른
    표에 있었다. 그래서 무엇이 열려 있는지는 사람이 손대는 페이지가 든다.

    대신 낡음은 기계가 안다 — 가리키는 계획 문서가 이 페이지보다 나중에
    고쳐졌으면 그렇게 말한다.
    """

    path = repo / ".wiki" / "plan-active.md"
    if not path.exists():
        return "", []
    meta, body = front_matter(path.read_text(encoding="utf-8"))
    stale = []
    mine = path.stat().st_mtime
    for target in meta.get("reads") or []:
        doc = repo / str(target)
        if doc.exists() and doc.stat().st_mtime > mine:
            stale.append(str(target))
    return body.strip(), stale


def decisions(repo: Path) -> list[tuple[str, str]]:
    directory = repo / ".wiki" / "decisions"
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.md"), reverse=True)[:MAX_DECISIONS]:
        meta, body = front_matter(path.read_text(encoding="utf-8"))
        title = str(meta.get("title") or "")
        if not title:
            first = next((x for x in body.splitlines() if x.startswith("# ")), "")
            title = first[2:].strip() or path.stem
        why = next(
            (x[3:].strip() for x in body.splitlines() if x.startswith("왜.")),
            "",
        )
        # 첫 문장만. 전문은 파일에 있고, 세션 시작에 네 건의 전문을 실으면
        # 정작 하던 일이 밀린다.
        head = re.split(r"(?<=다\.)\s", why, maxsplit=1)[0]
        found.append((title, head[:160] + (" …" if len(head) > 160 else "")))
    return found


def doc_catalog(repo: Path) -> str:
    """저장소 문서 목록. 없으면 빈 문자열.

    목록 전체가 9천 자라 세션 시작에 한 번 실으면 발화마다 드는 비용이 0 이다.
    무엇을 열지 고르는 것은 이 목록을 받은 쪽이 한다 — 대화 맥락을 다 가진
    쪽이 코사인보다 낫고, 한국어 질의와 영어 문서 사이도 그냥 잇는다.
    """

    try:
        import corpus

        index = corpus.load(repo)
        return corpus.catalog(index["docs"]) if index else ""
    except Exception:
        return ""


def titled(listing: str) -> tuple[list[str], list[int]]:
    """`(제목들, 그 제목이 있던 줄 번호)`. 경로는 제목이 아니다.

    목록 전체를 번역기에 넣으면 파일 이름과 디렉터리까지 번역 대상이 된다.
    코드 펜스로 감싸서 막으려 하면 이번엔 통째로 보호돼 제목도 안 바뀐다.
    그래서 제목만 뽑아 보내고 경로는 손대지 않는다.
    """

    rows, at = [], []
    for n, line in enumerate(listing.splitlines()):
        if line.startswith("  ") and " — " in line:
            rows.append(line.split(" — ", 1)[1])
            at.append(n)
    return rows, at


def retitled(listing: str, rows: list[str], at: list[int]) -> str:
    lines = listing.splitlines()
    for n, title in zip(at, rows):
        lines[n] = lines[n].split(" — ", 1)[0] + " — " + title
    return "\n".join(lines).replace("(저장소 루트)", "(repo root)")


def report(repo: Path) -> str:
    """세션 시작 컨텍스트. **에이전트 입력이므로 영어다.**

    한국어는 이 저장소의 정본으로 남는다 — 커밋 메시지도 `.wiki/decisions/`
    도 사람이 GitHub 에서 읽으니까. 번역은 그것이 에이전트에게 건너가는
    **이 한 자리**에서만 일어난다. 읽어 오는 함수들은 한국어 그대로 둔다.

    번역은 한 번에 묶어 보낸다. 문자열마다 따로 기다리면 결정 네 건만으로도
    24초이고 훅 예산이 25초다 — 그러면 번역이 아니라 주입 전체를 잃는다.
    마감까지 못 끝낸 것은 한국어 원문으로 조립해 **반드시** 내보낸다.
    """

    deadline = time.monotonic() + BUDGET

    body, stale = active_page(repo)
    open_plans = [] if body else plans(repo)
    recent = decisions(repo)
    listing = doc_catalog(repo)
    titles, title_at = titled(listing)

    step_rows = [s for _p, steps in open_plans for s in steps]
    pairs = [t for pair in recent for t in pair]
    chunks = [[body], step_rows, pairs, titles]
    flat = [t for chunk in chunks for t in chunk]
    done = translate.translate(flat, translate.KO_EN, deadline)
    cut, taken = [], 0
    for chunk in chunks:
        cut.append(done[taken:taken + len(chunk)])
        taken += len(chunk)
    (body,), step_rows, pairs, titles = cut
    recent = list(zip(pairs[::2], pairs[1::2]))

    lines = [
        "Where this repository stands right now. The wiki puts this in once, "
        "at session start.",
        "",
        f"## Branch\n\n{branch_line(repo, english=True)}",
    ]
    if body:
        lines.append("\n## In progress\n")
        lines.append(body)
        if stale:
            lines.append(
                f"\n**This list may be stale.** `{'`, `'.join(stale)}` changed "
                "later than it did. Read those documents and bring "
                "`.wiki/plan-active.md` into line before deciding what to change."
            )
    elif open_plans:
        lines.append("\n## Plans still open (read off their step tables)\n")
        taken = 0
        for path, steps in open_plans:
            lines.append(f"`{path.relative_to(repo).as_posix()}`")
            lines += [f"- {s}" for s in step_rows[taken:taken + len(steps)]]
            lines.append("")
            taken += len(steps)
        lines.append(
            "This only reads the status column of the `## 단계` table, so it "
            "carries neither why something was cancelled nor what comes next. "
            "Read the plan document before deciding what to change."
        )
    if listing:
        lines.append("\n## Every document in this repository\n")
        lines.append(
            "Pick from here and open that file. No bodies are loaded."
        )
        lines.append("\n```\n" + retitled(listing, titles, title_at) + "\n```")

    if recent:
        lines.append("\n## Recent decisions — read the reason before reversing one\n")
        for title, why in recent:
            lines.append(f"- {title}" + (f" — {why}" if why else ""))
        lines.append(
            "\nThe full records are in `.wiki/decisions/`. Re-proposing a "
            "direction already weighed and dropped is the most expensive "
            "repetition there is."
        )
    return "\n".join(lines)


def main() -> int:
    # 훅 stdout 은 파이프고 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="세션 시작에 현재 상태를 넣는다")
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()

    try:
        sys.stdin.read()  # 훅 입력은 안 쓰지만 파이프는 비워 준다
    except Exception:
        pass

    repo = args.project.expanduser()
    if not (repo / ".git").exists():
        return 0
    text = report(repo)
    if text.count("\n") < 4:
        return 0  # 브랜치 한 줄뿐이면 넣을 값어치가 없다

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": text,
            },
            "systemMessage": "위키: 현재 상태 주입",
        },
        sys.stdout,
        ensure_ascii=False,
    )
    return 0


if __name__ == "__main__":
    # 훅은 무슨 일이 있어도 세션을 멈추면 안 된다. 이름만 남기고 통과시킨다.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
