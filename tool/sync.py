"""sync — 위키를 저장소의 현재 상태에 맞춘다."""

from __future__ import annotations

import hook_diagnostics  # noqa: F401 -- 진입점의 제한 시간 전 스택 보존
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
import harvest  # noqa: E402
import repo_graph  # noqa: E402
import repo_lint  # noqa: E402

STAMP = ".sync"
DEFAULT_EVERY = 6 * 3600  # 결정 수확을 몇 초마다 한 번 볼 것인가


def stale_docs(repo: Path, roots: list[str]) -> tuple[bool, str]:
    """목록이 문서보다 낡았는가. 파일 시각만 본다."""

    index = repo / ".wiki" / "corpus.json"
    if not index.exists():
        return True, "목록이 없다"
    mine = index.stat().st_mtime
    known = {d["path"] for d in (corpus.load(repo) or {}).get("docs", [])}

    paths = corpus.walk(repo, roots)
    seen = {path.relative_to(repo).as_posix() for path in paths}
    newer = sum(1 for path in paths if path.stat().st_mtime > mine)
    gone = known - seen
    added = seen - known
    if added or gone:
        return True, f"문서 {len(added)}개 늘고 {len(gone)}개 사라졌다"
    if newer:
        return True, f"문서 {newer}개가 목록보다 나중에 고쳐졌다"
    return False, ""


def recorded(repo: Path) -> set[int]:
    """이미 기록된 PR 번호."""

    found = set()
    for path in (repo / ".wiki" / "decisions").glob("*.md"):
        for line in path.read_text(encoding="utf-8").splitlines()[:12]:
            if line.startswith("pr:"):
                try:
                    found.add(int(line.split(":", 1)[1].strip()))
                except ValueError:
                    pass
                break
    return found


def due(repo: Path, every: int) -> bool:
    stamp = repo / ".wiki" / STAMP
    if not stamp.exists():
        return True
    try:
        return time.time() - float(stamp.read_text(encoding="utf-8").strip()) > every
    except Exception:
        return True


def touch(repo: Path) -> None:
    stamp = repo / ".wiki" / STAMP
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(f"{time.time():.0f}", encoding="utf-8")


def new_decisions(repo: Path, limit: int) -> list[str]:
    """기록에 없는 결정을 캐서 쓴다. 쓴 파일 이름을 돌려준다.

    PR 을 먼저 보고, 원격이 없거나 `gh` 가 안 되면 커밋에서 읽는다. 두 저장소가
    서로 다른 방식으로 일해도 같은 기록이 남게 하려는 것이다.
    """

    known = recorded(repo)
    written = []
    source = harvest.prs(repo, limit) or harvest.commits(repo, limit)
    for pr in source:
        if pr["number"] in known:
            continue
        name, text = harvest.record(pr)
        out = repo / ".wiki" / "decisions"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.md").write_text(text, encoding="utf-8")
        written.append(name)
    return written


def main() -> int:
    # 훅 stdout 은 파이프고 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="위키를 저장소 상태에 맞춘다")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--roots", nargs="*", default=corpus.DEFAULT_ROOTS,
    )
    parser.add_argument("--every", type=int, default=DEFAULT_EVERY)
    parser.add_argument("--force", action="store_true", help="시간 제한을 무시한다")
    parser.add_argument("--quiet", action="store_true", help="바뀐 것이 없으면 침묵")
    args = parser.parse_args()

    repo = args.project.expanduser().resolve()
    if not (repo / ".wiki").is_dir():
        return 0

    lines: list[str] = []

    stale, why = stale_docs(repo, args.roots)
    if stale:
        docs = corpus.collect(repo, args.roots)
        (repo / ".wiki" / "corpus.json").write_text(
            json.dumps({"docs": docs}, ensure_ascii=False), encoding="utf-8"
        )
        lines.append(f"목록을 다시 만들었다 — {why} (문서 {len(docs)}개)")

        # 지식 그래프는 목록 위에 얹히므로 목록이 바뀔 때만 다시 만든다. 매번
        # 만들면 문서 전부를 읽게 되고, 그러면 이 훅이 비싸져서 꺼진다.
        graph = repo_graph.write(repo)
        if graph:
            counts = graph["counts"]
            lines.append(
                f"지식 그래프 — 문서 {counts['docs']}개 중 "
                f"아무도 안 가리키는 것 {counts['orphans']}개"
            )

    if args.force or due(repo, args.every):
        try:
            fresh = new_decisions(repo, 30)
        except Exception:
            fresh = []
        touch(repo)
        if fresh:
            lines.append(
                f"결정 기록 {len(fresh)}건을 캤다: " + ", ".join(fresh[:4])
            )

    # 이 저장소의 축만 본다. 허브 위키의 검진은 허브의 게이트와 `after-merge`
    # 가 든다 — 남의 축의 발견을 여기 뿌리면 이 세션에서 할 수 있는 일이 없는
    # 줄이 매번 뜨고, 그러면 읽는 쪽이 전체를 안 읽게 된다.
    findings = repo_lint.check(repo)
    if findings:
        lines.append(f"검진 발견 {len(findings)}건")
        lines += [f"  - {kind}: {message}" for kind, message in findings[:6]]

    if not lines:
        if not args.quiet:
            print("위키가 저장소와 맞는다.")
        return 0

    text = "위키 자동 갱신\n" + "\n".join(f"- {line}" for line in lines)
    if sys.stdin.isatty():
        print(text)
        return 0
    json.dump({"systemMessage": text}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    # 훅은 무슨 일이 있어도 세션을 멈추면 안 된다. 이름만 남기고 통과시킨다.
    try:
        _code = main()
    except Exception as _error:  # noqa: BLE001
        print(f"hook skipped: {type(_error).__name__}", file=sys.stderr)
        _code = 0
    raise SystemExit(_code)
