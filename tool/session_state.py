"""SessionStart 훅 — 세션을 "지금 어디인가" 를 아는 채로 시작하게 한다."""

from __future__ import annotations

import hook_diagnostics  # noqa: F401 -- 진입점의 제한 시간 전 스택 보존
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from wikilib import front_matter  # noqa: E402

MAX_PLANS = 2       # 계획 문서를 몇 개까지 볼 것인가
MAX_ROWS = 8        # 한 계획에서 미완 행 몇 개까지
MAX_DECISIONS = 4   # 최근 결정 몇 건


def run(repo: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        return done.stdout.strip() if done.returncode == 0 else ""
    except Exception:
        return ""


def branch_line(repo: Path) -> str:
    branch = run(repo, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    dirty = run(repo, "status", "--porcelain")
    ahead = run(repo, "rev-list", "--count", "@{u}..HEAD") if branch != "?" else ""
    bits = [f"`{branch}`"]
    if ahead and ahead != "0":
        bits.append(f"미푸시 {ahead}")
    bits.append(f"변경 {len(dirty.splitlines())}개" if dirty else "워크트리 깨끗")
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


def report(repo: Path) -> str:
    lines = [
        "이 저장소에서 지금 어디까지 와 있는지다. 위키가 세션 시작에 한 번 넣는다.",
        "",
        f"## 브랜치\n\n{branch_line(repo)}",
    ]
    body, stale = active_page(repo)
    if body:
        lines.append("\n## 하던 일\n")
        lines.append(body)
        if stale:
            lines.append(
                f"\n**이 목록이 낡았을 수 있다.** `{'`, `'.join(stale)}` 가 더 "
                "나중에 고쳐졌다. 무엇을 바꿀지 정하기 전에 그 문서를 읽고 "
                "`.wiki/plan-active.md` 를 맞춰라."
            )
    else:
        open_plans = plans(repo)
        if open_plans:
            lines.append("\n## 아직 안 끝난 계획 (표에서 뽑음)\n")
            for path, steps in open_plans:
                lines.append(f"`{path.relative_to(repo).as_posix()}`")
                lines += [f"- {s}" for s in steps]
                lines.append("")
            lines.append(
                "이 목록은 `## 단계` 표의 상태 칸만 본 것이라 취소된 이유도 "
                "다음 후보도 담지 못한다. 계획 문서를 읽기 전에 무엇을 바꿀지 "
                "정하지 마라."
            )
    listing = doc_catalog(repo)
    if listing:
        lines.append("\n## 이 저장소의 문서 전부\n")
        lines.append(
            "찾을 것이 있으면 여기서 고른 다음 그 파일을 열어라. 본문은 안 실린다."
        )
        lines.append("\n```\n" + listing + "\n```")

    recent = decisions(repo)
    if recent:
        lines.append("\n## 최근 결정 — 다시 뒤집기 전에 이유를 보라\n")
        for title, why in recent:
            lines.append(f"- {title}" + (f" — {why}" if why else ""))
        lines.append(
            "\n전체는 `.wiki/decisions/` 에 있다. 이미 재 보고 버린 방향을 "
            "다시 제안하는 것이 가장 비싼 반복이다."
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
