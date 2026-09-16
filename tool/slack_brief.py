"""slack_brief — Slack 에 낼 진척도·회고의 **사실 부분**만 낸다."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from session_state import active_page, branch_line, decisions, run  # noqa: E402

MAX_COMMITS = 12
SESSIONS = Path.home() / ".claude" / "projects"


def repo_url(repo: Path) -> str:
    """`git@…` 도 `https://…` 도 웹 주소 하나로. 리모트가 없으면 빈 문자열."""

    remote = run(repo, "remote", "get-url", "origin")
    if not remote:
        return ""
    remote = re.sub(r"^git@([^:]+):", r"https://\1/", remote)
    return re.sub(r"\.git$", "", remote)


def since_default() -> str:
    """월요일이면 사흘, 아니면 하루. 금→월 사이에 머지된 것을 안 잃는다."""

    return "3 days ago" if dt.date.today().weekday() == 0 else "1 day ago"


def default_ref(repo: Path) -> str:
    """머지된 것을 어디서 세나. 통합 브랜치이지 지금 체크아웃한 것이 아니다.

    기능 브랜치에 서 있으면 HEAD 에는 오늘 머지된 것이 없어서 "오늘 0건" 이
    나온다. 실제로 그렇게 나왔고, 그날 여섯 건이 머지돼 있었다.

    ponytail: 기능 브랜치의 미머지 커밋은 안 센다. 그것은 `branch_line` 의
    "변경 N개" 가 든다. 합집합이 필요해지면 그때 ref 를 둘 받아라.
    """

    head = run(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head
    for guess in ("origin/main", "origin/master", "main", "master"):
        if run(repo, "rev-parse", "--verify", "--quiet", guess):
            return guess
    return "HEAD"


# `%h` 는 16진수라 `|` 를 담지 않는다. `partition` 이 첫 것만 가르므로 제목에
# `|` 가 있어도 안전하다. `\x1e` 를 쓰면 안 된다 — `splitlines()` 가 그것을
# 줄바꿈으로 쳐서 한 커밋이 두 줄이 되고, 그러면 조용히 0건이 된다.
SEP = "|"


def format_rows(raw: str, url: str) -> list[str]:
    lines = []
    for row in raw.split("\n")[:MAX_COMMITS]:
        short, _, subject = row.strip().partition(SEP)
        if not subject:
            continue
        link = f"[`{short}`]({url}/commit/{short})" if url else f"`{short}`"
        # PR 번호가 제목에 있으면 그것도 원본이다.
        pr = re.search(r"\(#(\d+)\)$", subject)
        if pr and url:
            subject = subject[: pr.start()].rstrip()
            link += f" [#{pr.group(1)}]({url}/pull/{pr.group(1)})"
        lines.append(f"- {link} {subject}")
    return lines


def merged(repo: Path, since: str, url: str) -> list[str]:
    raw = run(repo, "log", default_ref(repo), f"--since={since}",
              "--no-merges", f"--format=%h{SEP}%s")
    return format_rows(raw, url)


def today_sessions(repo: Path) -> list[Path]:
    """회고의 근거가 어느 파일에 있는지. 오늘 고쳐진 세션 로그.

    내용은 안 읽는다 — 그건 `retrospect` 스킬이 한다. 여기서는 어디를 열면
    되는지만 짚는다. 6MB 짜리가 섞여 있어 통째로 싣는 것은 답이 아니다.
    """

    flat = str(repo).replace(":", "-").replace("\\", "-").replace("/", "-")
    folder = SESSIONS / flat
    if not folder.is_dir():
        folder = next((p for p in SESSIONS.iterdir()
                       if p.is_dir() and p.name.endswith(repo.name)), None)
        if folder is None:
            return []
    midnight = dt.datetime.combine(dt.date.today(), dt.time.min).timestamp()
    return sorted((p for p in folder.glob("*.jsonl")
                   if p.stat().st_mtime >= midnight),
                  key=lambda p: p.stat().st_mtime)


def standup(repo: Path, since: str) -> str:
    url = repo_url(repo)
    lines = [f"*진척도* — `{repo.name}` · {dt.date.today():%Y-%m-%d}", ""]
    lines.append(f"브랜치 {branch_line(repo)}")

    rows = merged(repo, since, url)
    lines += ["", f"*{since} 이후 머지 {len(rows)}건*"]
    lines += rows or ["- 없다."]

    recent = decisions(repo)
    if recent:
        lines += ["", "*최근 결정 — 뒤집기 전에 이유를 보라*"]
        lines += [f"- {title} — {why}" for title, why in recent[:3]]

    _, stale = active_page(repo)
    lines += ["", "*계획*"]
    if stale:
        lines.append(
            f"- `.wiki/plan-active.md` 가 낡았을 수 있다 — `{'`, `'.join(stale)}` "
            "가 더 나중에 고쳐졌다."
        )
    else:
        lines.append("- `.wiki/plan-active.md` 가 최신이다.")
    return "\n".join(lines)


def retro(repo: Path) -> str:
    url = repo_url(repo)
    lines = [f"*회고* — `{repo.name}` · {dt.date.today():%Y-%m-%d}", ""]

    rows = merged(repo, "midnight", url)
    lines += [f"*오늘 커밋 {len(rows)}건*"]
    lines += rows or ["- 없다."]

    stat = run(repo, "diff", "--shortstat", "@{midnight}", "HEAD")
    if stat:
        lines += ["", f"*변경량* {stat}"]

    logs = today_sessions(repo)
    lines += ["", f"*오늘의 세션 로그 {len(logs)}개* — 어긋난 자리는 여기서 센다"]
    lines += [f"- `{p.name}` ({p.stat().st_size // 1024}KB)" for p in logs[-5:]] \
        or ["- 없다."]
    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--kind", choices=("standup", "retro"), default="standup")
    ap.add_argument("--since", default=None, help="기본: 월요일 3일, 아니면 1일")
    args = ap.parse_args()

    repo = args.project.expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"git 저장소가 아니다: {repo}", file=sys.stderr)
        return 1
    print(retro(repo) if args.kind == "retro"
          else standup(repo, args.since or since_default()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
