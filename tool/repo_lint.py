"""repo_lint — 대상 저장소의 지식이 썩는 자리를 찾는다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from wikilib import metadata_errors, project_pages  # noqa: E402

NEWER_ALLOWED = 3   # 목록이 이만큼 뒤처지는 것은 아직 안 짚는다


def stale_index(repo: Path) -> list[tuple[str, str]]:
    """문서 목록이 문서보다 낡았는가.

    색인은 파생물이라 문서가 바뀌면 뒤처진다. 뒤처진 색인은 없는 색인보다
    나쁘다 — 지워진 문서를 자신 있게 가리킨다.
    """

    index = repo / ".wiki" / "corpus.json"
    if not index.exists():
        return []

    mine = index.stat().st_mtime
    docs = repo / "docs"
    newer = [
        path for path in docs.rglob("*.md") if path.stat().st_mtime > mine
    ] if docs.is_dir() else []

    gone = []
    try:
        listed = json.loads(index.read_text(encoding="utf-8")).get("docs") or []
    except (OSError, ValueError):
        listed = []
    for doc in listed:
        if not (repo / doc["path"]).exists():
            gone.append(doc["path"])

    if gone:
        return [(
            "낡은 목록",
            f"목록이 없는 문서 {len(gone)}개를 가리킨다 (예: `{gone[0]}`). "
            "`tool/corpus.py --write` 로 다시 만들어라",
        )]
    if len(newer) > NEWER_ALLOWED:
        return [(
            "낡은 목록",
            f"문서 {len(newer)}개가 목록보다 나중에 고쳐졌다. "
            "`tool/corpus.py --write` 로 다시 만들어라",
        )]
    return []


def dangling_pointers(repo: Path) -> list[tuple[str, str]]:
    """프로젝트 페이지가 가리키는 것이 실제로 있는가.

    프로젝트 페이지는 권위 문서를 통째로 싣지 않고 가리킨다. 그러면 가리키는
    쪽이 움직였을 때 조용히 틀린 것을 자신 있게 말하게 되므로, 그 경로가
    존재하는지는 기계가 매번 본다.
    """

    found = []
    for name, (meta, _body, _path) in project_pages(repo).items():
        for target in meta.get("reads") or []:
            if not (repo / str(target)).exists():
                found.append(("끊어진 포인터", f"`{name}` 이 `{target}` 를 가리키는데 없다"))
        if str(meta.get("severity")) in ("landmine", "contract") and not (
            meta.get("triggers") or []
        ):
            found.append(
                ("안 실리는 규칙", f"`{name}` 에 `triggers` 가 없어 아무 때도 안 실린다")
            )
    return found


def misplaced_scope(repo: Path) -> list[tuple[str, str]]:
    """허브 범위 페이지가 대상 저장소에 들어와 있는가.

    `operator` 와 `craft` 는 저장소를 안 가리므로 허브가 든다. 그것이 여기 있으면
    같은 교훈을 저장소마다 다시 배우게 되고, 그것이 이 위키를 만든 사고다.

    산문이 아니라 검사인 이유. 두 곳 다 "위키" 라고 불리고, 한 세션이 "위키에
    기록해라" 를 현재 저장소의 `.wiki/` 로 읽어 저장소를 안 가리는 규칙을 거기
    적었다. 주입 헤더가 이제 출처를 절대 경로로 적지만, 그것은 읽는 사람이 그
    줄을 읽어야 성립한다. **이 검사는 안 읽어도 빨개진다.**
    """

    found = []
    for name, (meta, _body, _path) in project_pages(repo).items():
        scope = str(meta.get("scope") or "").strip()
        if scope in ("operator", "craft"):
            found.append(
                (
                    "범위가 어긋난 페이지",
                    f"`{name}` 의 scope 가 `{scope}` 인데 저장소의 `.wiki/` 에 있다. "
                    "저장소를 안 가리는 규칙은 허브가 든다",
                )
            )
    return found


def check(repo: Path) -> list[tuple[str, str]]:
    """이 저장소의 발견. 인쇄는 부르는 쪽이 한다."""

    from apply import wiring_drift
    malformed = [
        ("페이지 형식 오류", f"`{path.relative_to(repo).as_posix()}`: {error}")
        for path in sorted((repo / ".wiki").glob("**/*.md"))
        for error in metadata_errors(path)
    ]
    # 강조 검사가 여기 있어야 그 계약이 대상 저장소에서도 성립한다.
    # 훅은 쓰기 전에 불리므로 `Edit` 과 패치가 만들 문서를 못 본다.
    # 그 자리를 메우는 것이 실제 파일을 읽는 이 검사이고, 허브에만 걸어 두면
    # 설치된 저장소에서는 조각이 통과한 뒤 아무도 안 본다 —
    # 붙었다고 적힌 강제가 실제로는 안 걸리는 그 모양이다.
    from lint import loud_emphasis

    return (stale_index(repo) + dangling_pointers(repo) + misplaced_scope(repo)
            + malformed + wiring_drift(repo) + loud_emphasis(repo))


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="대상 저장소의 지식을 검진한다")
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    findings = check(repo)

    print(f"# repo_lint — {repo.name}\n")
    if not findings:
        print("새 발견 없음.")
        return 0

    print(f"## 발견 {len(findings)}건\n")
    kinds: dict[str, list[str]] = {}
    for kind, message in findings:
        kinds.setdefault(kind, []).append(message)
    for kind, messages in kinds.items():
        print(f"### {kind} — {len(messages)}건\n")
        for message in messages:
            print(f"- {message}")
        print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
