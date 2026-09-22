"""slack_brief — produce only the factual half of a standup or retro for Slack.

What goes to Slack is read by the team, so those strings stay Korean.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from session_state import active_page, branch_line, decisions, run  # noqa: E402
from sessions import logs  # noqa: E402

MAX_COMMITS = 12


def repo_url(repo: Path) -> str:
    """`git@…` and `https://…` both to one web address. Empty with no remote."""

    remote = run(repo, "remote", "get-url", "origin")
    if not remote:
        return ""
    remote = re.sub(r"^git@([^:]+):", r"https://\1/", remote)
    return re.sub(r"\.git$", "", remote)


def since_default() -> str:
    """Three days on a Monday, one otherwise, so nothing merged over a weekend
    is lost."""

    return "3 days ago" if dt.date.today().weekday() == 0 else "1 day ago"


def default_ref(repo: Path) -> str:
    """Where merges get counted: the integration branch, not what is checked out.

    Standing on a feature branch, HEAD has nothing merged today and the brief
    says "0 today". It really did say that, on a day with six merges.

    ponytail: unmerged commits on a feature branch are not counted. Those are
    held by `branch_line`'s "N changed". If the union is ever needed, take two
    refs then.
    """

    head = run(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head
    for guess in ("origin/main", "origin/master", "main", "master"):
        if run(repo, "rev-parse", "--verify", "--quiet", guess):
            return guess
    return "HEAD"


# `%h` is hexadecimal and cannot contain `|`, and `partition` splits on the
# first one only, so a `|` in the title is safe. `\x1e` must not be used here:
# `splitlines()` treats it as a line break, one commit becomes two lines, and
# the count quietly goes to zero.
SEP = "|"


def format_rows(raw: str, url: str) -> list[str]:
    lines = []
    for row in raw.split("\n")[:MAX_COMMITS]:
        short, _, subject = row.strip().partition(SEP)
        if not subject:
            continue
        link = f"[`{short}`]({url}/commit/{short})" if url else f"`{short}`"
        # A PR number in the title is a source as well.
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
    """Which files hold the grounds for a retro: the session logs touched today.

    The contents are not read — that is the `retrospect` skill's job. This
    only points at what to open. Some of these run to 6MB, so carrying them
    whole is not an answer.
    """

    midnight = dt.datetime.combine(dt.date.today(), dt.time.min).timestamp()
    return sorted((p for p in logs(repo)
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
