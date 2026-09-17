"""trajectory — 어느 발화에 무엇을 실었고, 그 턴이 교정을 받았나."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from census import DEFAULT_MARKERS, Markers  # noqa: E402

KEEP = 500          # 발화를 몇 자까지 남기나
RESUME_MAX = 120    # census 와 같은 값. 긴 지시문 안의 "이어서" 는 재개 요구가 아니다
TAIL = 8192         # 마지막 줄을 찾으려고 읽는 꼬리 크기
FILENAME = "trajectory.jsonl"


def path_for(wiki: Path) -> Path:
    return wiki / FILENAME


def hush(wiki: Path) -> None:
    """`.wiki/` 는 커밋되는데 이 파일은 매 턴 바뀐다.

    커밋되는 것은 여기서 걷어 간 **측정**이지 스트림이 아니다. `.wiki/.sync` 가
    이미 같은 이유로 무시되고 있고, 그쪽은 저장소의 `.gitignore` 가 들지만
    이 파일은 대상 저장소마다 생기므로 자기가 스스로 든다.
    """

    ignore = wiki / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    if FILENAME in lines:
        return
    # 줄끝을 환경에 안 맡긴다. Windows 기본으로 쓰면 이미 있던 줄까지 CRLF 로 뒤집혀
    # 한 줄 추가가 파일 전체 diff 로 보인다.
    ignore.write_text("\n".join([*lines, FILENAME]) + "\n", encoding="utf-8", newline="\n")


def last_row(path: Path) -> dict | None:
    """마지막 줄. 파일 전체는 안 읽는다 — 이것은 매 턴 도는 훅이다.

    꼬리만 읽으므로 첫 줄이 중간에서 잘릴 수 있다. 뒤에서부터 보면서 처음
    파싱되는 줄을 쓰면 그 잘린 조각은 자연히 지나간다.
    """

    if not path.exists():
        return None
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        handle.seek(max(0, handle.tell() - TAIL))
        chunk = handle.read().decode("utf-8", errors="replace")
    for line in reversed(chunk.splitlines()):
        if not line.strip():
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def verdict(prompt: str, markers: Markers) -> str:
    """이 발화가 **앞 턴에 대해** 무엇을 말하는가.

    `resume` 만 길이를 본다. 긴 지시문 안의 "이어서" 는 재개 요구가 아니라 그냥
    지시인데, census 가 그 자리를 120자로 갈라 두었다. 같은 값을 쓴다.

    판정이 아니라 표지다. 무엇이 오탐인지는 사람이 본다 — 여기서 점수를 매기면
    census 가 못 믿게 되는 바로 그 자동 판정이 된다.
    """

    if any(re.search(pattern, prompt) for pattern in markers.correction):
        return "교정"
    if len(prompt) < RESUME_MAX and any(
        re.search(pattern, prompt) for pattern in markers.resume
    ):
        return "재개요구"
    if any(re.search(pattern, prompt) for pattern in markers.partial):
        return "부분수행"
    return "ok"


def record(
    wiki: Path | None,
    prompt: str,
    injected: list[str],
    cost: int,
    session: str,
) -> str | None:
    """한 턴을 남기고, 같은 세션이면 앞 줄을 채점한다.

    실패는 전부 삼킨다. 기록 하나 때문에 세션을 멈추지 않는다 —
    `craft/hooks-fail-open`. 다만 **조용히 삼키지는 않는다.** 예외 이름을
    돌려주고, 그것을 화면에 낼지는 스트림을 소유한 쪽이 정한다. 라이브러리가
    남의 stderr 에 직접 쓰면 그 스트림의 인코딩을 누가 고정했는지 알 수 없다.
    """

    if wiki is None:
        return None
    try:
        wiki.mkdir(parents=True, exist_ok=True)
        hush(wiki)
        path = path_for(wiki)
        row: dict[str, object] = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "session": session,
            "utterance": prompt[:KEEP],
            "chars": len(prompt),
            "injected": injected,
            "cost": cost,
        }
        previous = last_row(path)
        if session and previous and previous.get("session") == session:
            row["prev"] = verdict(prompt, Markers.load(DEFAULT_MARKERS))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as error:  # noqa: BLE001
        return type(error).__name__
    return None


def rows(wiki: Path) -> list[dict]:
    """읽는 쪽. 이 형식이 두 곳에 정의되면 두 곳이 어긋난다."""

    path = path_for(wiki)
    if not path.exists():
        return []
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            found.append(json.loads(line))
        except ValueError:
            continue
    return found
