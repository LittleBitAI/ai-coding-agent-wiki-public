"""harvest — 이미 있는 기록에서 결정을 캐낸다."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_WHY = 400      # 이유를 몇 자까지 담을 것인가
MAX_WHAT = 260

# 도메인 표. (이름, 브랜치·제목에서 찾을 표시, 그 도메인을 부르는 트리거)
#
# 순서가 중요하다. 위에서부터 처음 걸리는 것을 쓰므로, 좁은 것이 먼저 와야
# 한다. 여기에 없는 PR 은 도메인이 없고, 도메인이 없으면 주입되지 않는다 —
# 트리거 없이 파일만 남는 것이 억지로 흔한 낱말에 거는 것보다 낫다.
DOMAINS: list[tuple[str, tuple[str, ...], list[str]]] = [
    ("vision", ("vision", "screen", "frame", "화면", "시각", "프레임"),
     ["화면", "vision", "프레임", "스크린", "캡처", "공유"]),
    ("memory", ("memory", "mem0", "recall", "기억", "회상"),
     ["기억", "memory", "회상", "mem0", "저장소.{0,4}기억"]),
    ("tts", ("tts", "qwen", "voice", "audio", "음성", "발화"),
     ["tts", "qwen", "음성", "목소리", "합성", "재생"]),
    # `프롬프트` 와 `응답` 은 홀로 두면 안 된다. "사용자 프롬프트를 작성해줘"
    # (세션 인계문)와 "대화 프롬프트"(제품)가 같은 낱말이고 앞엣것이 훨씬
    # 잦다. 복합어로만 건다.
    ("dialogue", ("dialogue", "response", "prompt", "persona", "gemini",
                  "openai", "대화", "응답", "프롬프트"),
     ["대화\\s*(모델|프롬프트|응답|생성)", "응답\\s*(정책|수리|스키마)",
      "페르소나", "말투", "gemini", "openai"]),
    ("browser", ("browser", "frontend", "client", "브라우저", "클라이언트"),
     ["브라우저", "frontend", "클라이언트", "화면 클라"]),
    ("api", ("api", "route", "turn", "latency", "telemetry", "지연", "턴"),
     ["지연", "latency", "텔레메트리", "턴 조립", "api 조립"]),
    ("infra", ("ci", "launcher", "migration", "postgres", "런처", "게이트"),
     ["런처", "게이트", "postgres", "마이그레이션", "ci"]),
]


def commits(repo: Path, limit: int) -> list[dict]:
    """커밋 메시지에서 결정을 읽는다. PR 이 없는 저장소를 위한 것.

    이 저장소들의 커밋 메시지는 PR 본문과 같은 모양을 갖는다 — 제목 한 줄과
    무엇·왜가 적힌 본문. 그래서 같은 추출기가 그대로 통한다.
    """

    sep = "\x1e"
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), "log", f"-{limit}",
             f"--format=%H{sep}%ad{sep}%s{sep}%b{sep}", "--date=short"],
            capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
        )
    except Exception:
        return []
    if done.returncode != 0:
        return []
    found = []
    for block in done.stdout.split("\x1e\n"):
        parts = block.split(sep)
        if len(parts) < 4:
            continue
        sha, date, subject, body = parts[0].strip(), parts[1], parts[2], parts[3]
        if not sha:
            continue
        found.append({
            "number": int(sha[:6], 16) % 1000,
            "sha": sha[:9],
            "title": subject,
            "body": body,
            "mergedAt": date,
            "headRefName": "",
        })
    return found


def prs(repo: Path, limit: int) -> list[dict]:
    try:
        done = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--limit", str(limit),
             "--json", "number,title,body,mergedAt,headRefName"],
            cwd=repo, capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace",
        )
    except Exception:
        return []
    if done.returncode != 0:
        return []
    try:
        return json.loads(done.stdout)
    except Exception:
        return []


def section(body: str, name: str) -> str:
    hit = re.search(rf"^##+\s*{name}\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    return hit.group(1).strip() if hit else ""


def _prose(block: str) -> str:
    """한 문단에서 마크다운 제목 줄을 걷고 한 줄로 만든다. 남는 게 없으면 빈 문자열."""

    lines = [ln for ln in block.splitlines() if not re.match(r"\s*#{1,6}\s", ln)]
    return " ".join(" ".join(lines).split())


def squeeze(text: str, limit: int) -> str:
    """굵게와 목록 기호를 걷고 문장 단위로 자른다."""

    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.M)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind("."), cut.rfind("다 "), cut.rfind("다."))
    return (cut[: stop + 1] if stop > limit // 2 else cut).strip() + " …"


def triggers_for(title: str, branch: str) -> tuple[str, list[str]]:
    """이 결정이 어느 도메인의 것인가, 그리고 그 도메인을 부르는 말.

    결정을 부르는 것은 낱말이 아니라 주제다. 제목에서 낱말을 뽑으면
    `세션`·`어떻게`·`메모리`·`요약` 같은 흔한 말이 걸리고, 그건 그 결정과
    아무 상관이 없다. 그래서 도메인 하나를 정하고 그 도메인의 말에만 건다.
    도메인은 이 저장소들이 PR 을 가르는 단위이기도 하다 — 두 도메인은 같은
    PR 을 공유하지 않는다.
    """

    text = f"{branch} {title}".lower()
    for domain, marks, triggers in DOMAINS:
        if any(_marks(text, m) for m in marks):
            return domain, triggers
    return "", []


def _marks(text: str, mark: str) -> bool:
    """표지가 낱말로 서 있는가.

    부분문자열로 보면 짧은 ASCII 표지가 낱말 **안에서** 걸린다 -- `ci` 가
    `de-ci-sion` 에, `turn` 이 `re-turn` 에, `frame` 이 `frame-work` 에. 그리고
    도메인이 붙으면 트리거도 붙고, `inject.py` 는 트리거가 있으면 규칙처럼
    주입하므로 오분류는 상관없는 세션마다 그 기록을 띄운다.

    한글 표지는 낱말 경계가 없으므로 그대로 포함으로 본다. 좁히는 쪽으로만
    바뀌므로, 이 변경이 놓치는 것은 애초에 낱말로 서 있지 않던 표지뿐이다.
    """

    if not mark.isascii():
        return mark in text
    return re.search(rf"(?<![a-z0-9]){re.escape(mark)}(?![a-z0-9])", text) is not None


def record(pr: dict) -> tuple[str, str]:
    number = pr["number"]
    date = str(pr.get("mergedAt") or "")[:10] or "0000-00-00"
    title = " ".join(str(pr.get("title") or "").split())
    branch = str(pr.get("headRefName") or "")
    # GitHub 은 본문을 CRLF 로 돌려준다. 아래 폴백이 `\n\n` 으로 문단을 가르므로,
    # 정규화를 빼면 CRLF 본문은 통째로 한 덩어리가 되어 `왜` 가 늘 비고 `무엇` 은
    # 본문 전체를 잘라 담는다. PR #95 의 기록이 정확히 그렇게 나왔다.
    body = str(pr.get("body") or "").replace("\r\n", "\n").replace("\r", "\n")

    what = squeeze(section(body, "변경 요약"), MAX_WHAT)
    why = squeeze(section(body, "변경 이유"), MAX_WHY)
    if not (what or why):
        # 절 제목이 없는 커밋 메시지. 첫 문단이 무엇, 나머지가 왜다.
        #
        # **제목 줄은 재료가 아니다.** 이 저장소들의 PR 본문은 거의 다 마크다운
        # 제목으로 시작하므로, 첫 덩어리를 그대로 담으면 `무엇. ## 결론` 이 기록이
        # 된다. 2026-09-10 의 131~135 가 전부 그렇게 나갔다. 덩어리째 버리지 않고
        # 제목 *줄* 만 걷는 이유는, 제목과 본문 사이에 빈 줄이 없으면 둘이 한
        # 덩어리라 통째로 버리면 본문까지 잃기 때문이다.
        blocks = [_prose(b) for b in body.split("\n\n")]
        blocks = [b for b in blocks if b]
        what = squeeze(blocks[0], MAX_WHAT) if blocks else ""
        why = squeeze(" ".join(blocks[1:]), MAX_WHY) if len(blocks) > 1 else ""
    domain, trig = triggers_for(title, branch or title)

    # 번호를 이름에 넣는다. 브랜치 이름만 쓰면 재사용된 이름끼리 겹쳐 나중
    # 것이 앞엣것을 조용히 덮는다.
    slug = re.sub(r"[^a-z0-9]+", "-", (branch or pr.get("sha", "")).lower()).strip("-")
    name = f"{date}-{number:03d}-{slug or 'commit'}"[:74]

    lines = [
        "---",
        "scope: project",
        # 도메인이 없으면 주입 대상이 아니다. 파일로는 남아 검색과 세션 시작
        # 요약에 쓰이지만, 흔한 낱말에 억지로 걸지는 않는다.
        "severity: contract" if (why and trig) else "severity: preference",
        f"triggers: {json.dumps(trig, ensure_ascii=False)}",
        f"domain: {domain}" if domain else "domain: ''",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"pr: {number}",
        f"merged: {date}",
        f"branch: {json.dumps(branch, ensure_ascii=False)}",
        "---",
        "",
        f"# {title}",
        "",
        f"무엇. {what}" if what else "무엇. (PR 본문에 요약 절이 없다)",
        "",
        f"왜. {why}" if why else
        "왜. (PR 본문에 이유 절이 없다. 이 결정의 근거는 기록되지 않았다)",
        "",
        f"출처. PR #{number} · `{branch}`" if branch
        else f"출처. 커밋 `{pr.get('sha', '')}`",
        "",
    ]
    return name, "\n".join(lines)


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="PR 본문에서 결정 기록을 캐낸다")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--from", dest="source", choices=("prs", "commits"), default="prs",
        help="PR 이 없는 저장소는 `commits`",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    repo = args.project.expanduser().resolve()
    merged = (prs if args.source == "prs" else commits)(repo, args.limit)
    if not merged:
        print(f"{args.source} 에서 아무것도 못 읽었다.")
        return 2

    out = repo / ".wiki" / "decisions"
    written, thin, homeless = 0, [], []
    by_domain: dict[str, int] = {}
    what = "머지된 PR" if args.source == "prs" else "커밋"
    print(f"# harvest — {repo.name}\n")
    print(f"{what} {len(merged)}건\n")
    for pr in merged:
        name, text = record(pr)
        if "이유 절이 없다" in text:
            thin.append(f"#{pr['number']} {pr['title'][:52]}")
        domain, _ = triggers_for(str(pr.get("title") or ""), str(pr.get("headRefName") or ""))
        by_domain[domain or "(없음)"] = by_domain.get(domain or "(없음)", 0) + 1
        if not domain:
            homeless.append(f"#{pr['number']} {pr['title'][:52]}")
        if args.write:
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{name}.md").write_text(text, encoding="utf-8")
            written += 1

    print(f"이유 절이 있는 것 {len(merged) - len(thin)}건 · 없는 것 {len(thin)}건\n")
    print("## 도메인별\n")
    for domain, count in sorted(by_domain.items(), key=lambda i: -i[1]):
        print(f"- {domain}: {count}건")
    print()
    if homeless:
        print("## 도메인을 못 정한 PR — 파일로만 남고 주입은 안 된다\n")
        for line in homeless[:10]:
            print(f"- {line}")
        print("\n표에 표시를 더하거나, 그대로 두라. 흔한 낱말에 억지로 걸면 "
              "적중률이 오르고 정작 규칙이 밀린다.\n")
    if thin:
        print("## 근거가 안 적힌 PR — 캐도 빈 자리로 남는다\n")
        for line in thin[:12]:
            print(f"- {line}")
        print()
    if not args.write:
        name, text = record(merged[0])
        print(f"## 미리보기 — `.wiki/decisions/{name}.md`\n")
        print("```markdown")
        print(text.rstrip())
        print("```\n")
        print("`--write` 를 주면 전부 쓴다.")
        return 0
    print(f"썼다: {out} ({written}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
