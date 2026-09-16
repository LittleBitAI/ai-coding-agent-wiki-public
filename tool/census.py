"""census — 새 프로젝트를 붙일 때 맨 처음 도는 진단."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MARKERS = HERE / "markers" / "ko.toml"

# 대화 로그에 사람 발화와 같은 자리로 들어오지만 사람이 친 것이 아닌 것들.
# 하네스가 주입하는 것이므로 언어와 무관하다.
INJECTED = (
    "<local-command-",
    "<command-name>",
    "<command-message>",
    "<system-reminder>",
    "<task-notification>",
    "Caveat: The messages below were generated",
    "[Request interrupted",
    "API Error",
    "Base directory for this skill:",
    "You have access to browser automation tools",
    "Goal check-in:",
    "is still active, and evaluation has been deferred",
    "This session is being continued from a previous",
    "A session-scoped Stop hook is now active",
    # 스킬 본문. 사람 발화와 같은 레코드 타입으로 들어오고 길어서, 안 거르면
    # "가장 많이 재입력된 지시문" 자리를 통째로 차지한다. 실제로 그랬다.
    "Approach this as the design lead",
    "Use this skill whenever you are about to create",
    "PONYTAIL MODE ACTIVE",
)

# 위 목록은 언제나 뒤처진다 — 스킬이 늘면 새 본문이 또 샌다. 그래서 길이로도
# 한 번 거른다. 사람이 한 번에 이만큼 치는 일은 드물고, 그 드문 경우는 대개
# 붙여넣은 로그이지 지시가 아니다.
MAX_HUMAN_CHARS = 20_000


@dataclass
class Turn:
    session: str
    order: int
    at: str
    text: str

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class Markers:
    correction: list[str] = field(default_factory=list)
    resume: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    incidents: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Markers":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return cls(
            correction=list(data.get("correction", [])),
            resume=list(data.get("resume", [])),
            partial=list(data.get("partial", [])),
            incidents={k: list(v) for k, v in (data.get("incidents") or {}).items()},
        )


def transcript_dir(project: Path, root: Path) -> Path:
    """Claude Code 는 체크아웃 경로를 납작하게 눌러 디렉터리 이름으로 쓴다.

    `C:\\projects\\demo`가 `C--projects-demo`가 된다. 구분자를 전부 `-`로 바꾸는데
    드라이브의 `:` 도 한 자리를 차지하므로 앞에 하이픈이 둘이다. 규칙을 추측하지
    말고, 맞는 것이 없으면 실제 디렉터리를 훑어 꼬리로 찾는다.
    """

    flat = re.sub(r"[:\\/]", "-", str(project.resolve()))
    exact = root / flat
    if exact.is_dir():
        return exact
    # 규칙이 안 맞는 환경을 위한 대비책. 이름 꼬리로 찾는다.
    tail = f"-{project.resolve().name}"
    for candidate in sorted(root.glob("*")):
        if candidate.is_dir() and candidate.name.endswith(tail):
            return candidate
    return exact


def human_turns(directory: Path) -> list[Turn]:
    """`type=user` 중 사람이 친 것만. 도구 결과와 주입 텍스트를 뺀다."""

    turns: list[Turn] = []
    for path in sorted(directory.glob("*.jsonl")):
        for order, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines()
        ):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if record.get("type") != "user":
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                body = content
            elif isinstance(content, list):
                # 블록이 하나라도 text 가 아니면 도구 결과다.
                if not content or any(
                    not isinstance(b, dict) or b.get("type") != "text" for b in content
                ):
                    continue
                body = "\n".join(str(b.get("text") or "") for b in content)
            else:
                continue
            body = body.strip()
            if not body or any(mark in body for mark in INJECTED):
                continue
            turns.append(Turn(path.stem, order, str(record.get("timestamp") or ""), body))
    turns.sort(key=lambda t: (t.at, t.session, t.order))
    return turns


def skeleton(text: str) -> str:
    """숫자·경로·해시를 지워 뼈대만 남긴다. 재붙여넣기를 찾기 위한 것."""

    t = " ".join(text.split())
    t = re.sub(r"#\d+", "#N", t)
    t = re.sub(r"\b[0-9a-f]{7,40}\b", "SHA", t)
    t = re.sub(r"\d+", "N", t)
    t = re.sub(r"[A-Za-z0-9_./\\-]{12,}", "PATH", t)
    return t[:220]


def cluster(turns: list[Turn], threshold: float = 0.88) -> dict[str, list[Turn]]:
    """뼈대가 비슷한 발화를 한 군집으로 묶는다.

    똑같을 때만 묶으면 조사·오타 한 글자로 갈린다. `difflib` 비율로 묶어 그것을
    막는다 - 어느 언어에서든 통하고, 이 규모(수백 건)에서는 O(n^2) 도 싸다.
    """

    from difflib import SequenceMatcher

    reps: list[str] = []
    groups: dict[str, list[Turn]] = {}
    for turn in turns:
        skel = skeleton(turn.text)
        for rep in reps:
            # 길이가 크게 다르면 볼 것도 없다. 비교를 건너뛰어 싸게 만든다.
            if min(len(skel), len(rep)) / max(len(skel), len(rep), 1) < threshold:
                continue
            if SequenceMatcher(None, skel, rep).ratio() >= threshold:
                groups[rep].append(turn)
                break
        else:
            reps.append(skel)
            groups[skel] = [turn]
    return groups


def governing_text(project: Path, names: list[str]) -> str:
    parts = []
    for name in names:
        path = project / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="세션 로그로 무엇이 고장 나는지 센다")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--transcripts", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--markers", type=Path, default=DEFAULT_MARKERS)
    parser.add_argument(
        "--governing",
        nargs="*",
        default=["CLAUDE.md", "AGENTS.md"],
        help="대상 저장소에서 항상 로드되는 파일",
    )
    parser.add_argument("--out", type=Path, help="사람 발화를 jsonl 로 저장할 경로")
    parser.add_argument("--samples", type=int, default=12, help="표지에 안 걸린 표본 수")
    parser.add_argument(
        "--since",
        help="이 시각 이후만 센다. `today` 또는 ISO 날짜(2026-09-01). "
             "회고가 오늘 난 것만 보려고 쓴다",
    )
    args = parser.parse_args()

    directory = transcript_dir(args.project, args.transcripts)
    if not directory.is_dir():
        print(f"세션 로그를 못 찾았다: {directory}", file=sys.stderr)
        return 2

    markers = Markers.load(args.markers)
    turns = human_turns(directory)
    if not turns:
        print("사람 발화가 없다. --transcripts 경로를 확인하라.", file=sys.stderr)
        return 2

    window = ""
    if args.since:
        # `at` 은 ISO 문자열이라 사전순 비교가 곧 시간순이다. 파싱하지 않는다.
        cut = (
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if args.since == "today"
            else args.since
        )
        whole = len(turns)
        turns = [t for t in turns if t.at >= cut]
        window = f" · `--since {cut}` 로 {whole}건 중 {len(turns)}건"
        if not turns:
            print(f"{cut} 이후 사람 발화가 없다.", file=sys.stderr)
            return 2

    print(f"# census — {args.project.name}\n")
    print(f"세션 {len({t.session for t in turns})}개에서 사람 발화 "
          f"{len(turns)}건 / {sum(t.chars for t in turns):,}자{window}\n")

    # --- 1. 반복 지시
    # 뼈대가 똑같을 때만 묶으면 조사 한 글자 차이로 갈린다("PR #N를" vs
    # "PR #N을"). 실제로 같은 지시문 10회가 5+5 로 쪼개져 나왔다. 그래서 뼈대끼리
    # 유사도로 묶는다 — 언어에 안 매이는 방법이다.
    groups = cluster(turns)
    repeats = sorted(
        ((k, v) for k, v in groups.items() if len(v) > 1), key=lambda i: -len(i[1])
    )
    print("## 반복 지시 — 같은 말을 다시 시킨 자리\n")
    print("실수가 아니라 자동화되지 않은 관습이다. 위키가 가장 싸게 없앤다.\n")
    print("| 횟수 | 총 글자 | 지시문 |")
    print("| ---: | ---: | --- |")
    for skel, group in repeats[:10]:
        chars = sum(t.chars for t in group)
        print(f"| {len(group)} | {chars:,} | {skel[:82]} |")
    print()

    # --- 2. 그 규칙이 이미 적혀 있는가 (이 census 의 핵심 지표)
    governing = governing_text(args.project, args.governing)
    if governing and repeats:
        # 횟수가 아니라 재입력된 글자수로 고른다. "이어서 해라" 는 23회지만
        # 7자라 규칙을 안 담는다. 규칙이 실린 것은 길고 여러 번 붙여넣어진 쪽이다.
        heaviest = max(repeats, key=lambda item: sum(t.chars for t in item[1]))[1]
        print("## 이미 적혀 있는데도 다시 쳤는가\n")
        print("이 census 의 핵심 지표다. 가장 많은 글자가 재입력된 지시문의 문장을 "
              f"`{'`, `'.join(args.governing)}` 와 대조한다. 이미 있는데 다시 쳤다면 "
              "그 규칙은 적혀만 있고 작동하지 않는다 — 병목은 검색이 아니라 강제다.\n")
        sentences = [
            s.strip()
            for s in re.split(r"[.\n·]", heaviest[0].text)
            if 12 < len(s.strip()) < 90
        ]
        print(f"- {len(heaviest)}회 반복 · 총 {sum(t.chars for t in heaviest):,}자 재입력\n")
        print("백분율을 내지 않는다. 문자열 대조로는 같은 규칙이 다른 말로 적힌 "
              "것을 못 잡는다(실제로 손으로 개념 대조하니 12/16 이었는데 문자열로는 "
              "0/42 가 나왔다). 대신 대조할 문장을 뽑아 준다 — 각 문장이 이미 "
              "적혀 있는지는 사람이 판단한다.\n")
        print("| 낱말이 걸림 | 재입력된 규칙 문장 |")
        print("| :---: | --- |")
        for sentence in sentences[:16]:
            # 흔한 낱말을 빼고 특징적인 것만 남겨 힌트를 준다. 판정이 아니라 힌트다.
            words = [w for w in re.findall(r"[A-Za-z_./]{4,}|[가-힣]{2,}", sentence)]
            hint = "○" if any(w in governing for w in words) else " "
            print(f"| {hint} | {sentence[:78]} |")
        print()

    # --- 3. 부류별 집계
    def hits(patterns: list[str], limit: int | None = None) -> list[Turn]:
        found = [t for t in turns if any(re.search(p, t.text) for p in patterns)]
        return [t for t in found if limit is None or t.chars < limit]

    print("## 부류별\n")
    print("| 건수 | 부류 |")
    print("| ---: | --- |")
    print(f"| {len(hits(markers.correction))} | 교정 — 내가 틀렸다고 말한 자리 |")
    print(f"| {len(hits(markers.resume, 120))} | 재개 요구 — 멈추지 말았어야 할 자리 |")
    print(f"| {len(hits(markers.partial))} | 부분 수행 — 나머지를 다시 시킨 자리 |")
    print()

    if markers.incidents:
        print("## 같은 실패가 몇 번 지적됐나\n")
        print("| 횟수 | 무엇 |")
        print("| ---: | --- |")
        for name, patterns in sorted(
            markers.incidents.items(), key=lambda i: -len(hits(i[1]))
        ):
            print(f"| {len(hits(patterns))} | {name} |")
        print()

    # --- 4. 표지가 놓친 것 (편향 점검)
    missed = [t for t in turns if not any(re.search(p, t.text) for p in markers.correction)]
    print("## 표지에 안 걸린 표본\n")
    print("이 표본을 눈으로 읽어라. 교정인데 표지가 못 잡은 것이 보이면 "
          f"`{args.markers.name}` 에 그 어휘를 더한다. 이 절이 없으면 census 는 "
          "표지를 쓴 사람의 편향을 잰다.\n")
    step = max(1, len(missed) // max(1, args.samples))
    for turn in missed[::step][: args.samples]:
        print(f"- {' '.join(turn.text.split())[:110]}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="\n") as handle:
            for turn in turns:
                handle.write(json.dumps(
                    {"session": turn.session, "order": turn.order, "at": turn.at,
                     "chars": turn.chars, "text": turn.text},
                    ensure_ascii=False,
                ) + "\n")
        print(f"\n사람 발화를 {args.out} 에 저장했다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
