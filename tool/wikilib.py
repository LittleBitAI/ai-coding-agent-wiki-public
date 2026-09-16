"""wikilib — 페이지를 읽는 법. 도구 여럿이 같은 정의를 쓰게 한다."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WIKI = Path(os.environ.get("WIKI_ROOT") or HERE.parent)
SCOPES = ("operator", "craft")


def front_matter(text: str, *, strict: bool = False) -> tuple[dict[str, object], str]:
    """front matter 를 YAML 로 읽는다.

    손으로 쓴 줄 단위 파서를 쓰다가 두 번 데었다. 한 번은 정규식 안의 `{0,10}` 이
    가진 쉼표로 목록이 쪼개져 페이지가 통째로 안 걸렸고, 한 번은 `SCHEMA.md` 가
    규정한 `conflicts_with` 의 중첩 모양을 아예 못 읽었다 — 규약에 적힌 형식을
    파서가 못 읽으면 그 규약은 없는 것이다.
    """

    if not text.startswith("---"):
        if strict:
            raise ValueError("front matter가 없다")
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        if strict:
            raise ValueError("front matter가 닫히지 않았다")
        return {}, text
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as error:
        if strict:
            raise ValueError("front matter YAML 파싱 실패") from error
        meta = {}
    if strict and (not isinstance(meta, dict) or not meta):
        raise ValueError("front matter는 비어 있지 않은 매핑이어야 한다")
    return (meta if isinstance(meta, dict) else {}), text[end + 4 :].lstrip("\n")


def metadata_errors(path: Path) -> list[str]:
    """훅은 실패를 통과시키되 검진은 잃어버린 페이지를 드러낸다."""
    try:
        meta, _body = front_matter(path.read_text(encoding="utf-8"), strict=True)
    except ValueError as error:
        return [str(error)]
    triggers = meta.get("triggers", [])
    if not isinstance(triggers, list):
        return ["triggers는 목록이어야 한다"]
    errors = []
    for pattern in triggers:
        try:
            re.compile(str(pattern))
        except re.error:
            errors.append(f"잘못된 트리거 정규식: {pattern}")
    return errors


def pages(wiki: Path = WIKI) -> dict[str, tuple[dict, str, Path]]:
    """허브의 규칙 페이지. 이름은 `범위/이름`."""

    found: dict[str, tuple[dict, str, Path]] = {}
    for scope in SCOPES:
        directory = wiki / scope
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            meta, body = front_matter(path.read_text(encoding="utf-8"))
            found[f"{scope}/{path.stem}"] = (meta, body, path)
    return found


def project_pages(repo: Path) -> dict[str, tuple[dict, str, Path]]:
    """대상 저장소의 `.wiki/`. 결정 기록은 뺀다 — 수가 많고 링크를 안 갖는다."""

    directory = repo / ".wiki"
    if not directory.is_dir():
        return {}
    found = {}
    for path in sorted(directory.glob("*.md")):
        meta, body = front_matter(path.read_text(encoding="utf-8"))
        found[f".wiki/{path.stem}"] = (meta, body, path)
    return found


def links_of(meta: dict, body: str) -> set[str]:
    """본문의 `[[이름]]` 과 front matter 의 `links:` 는 둘 다 링크다.

    본문만 세면 `links:` 로만 이어진 페이지가 고아로 잡힌다. 실제로 그렇게
    5장 중 3장이 고아로 나왔고, 셋 다 front matter 에 링크가 있었다.
    """

    declared = {str(name) for name in (meta.get("links") or [])}
    return set(re.findall(r"\[\[([^\]]+)\]\]", body)) | declared


def resolve(target: str, names: set[str]) -> str | None:
    """`[[name]]` 은 범위를 안 적으므로 꼬리로 찾는다."""

    if target in names:
        return target
    for name in names:
        if name.split("/", 1)[1] == target:
            return name
    return None


def git_ok(repo: Path, ref: str) -> bool:
    """이 저장소에 그 ref 가 실재하는가.

    `subprocess` 를 함수 안에서 부른다. 이 모듈은 주입 훅이 매 발화마다 읽는데,
    훅은 git 을 안 부르면서 그 import 값 14ms 를 매번 낸다.
    훅이 비싸지면 꺼질 것이고, 꺼진 훅은 없는 것과 같다.
    """

    import subprocess

    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
            capture_output=True, timeout=10,
        ).returncode == 0
    except Exception:
        return False
