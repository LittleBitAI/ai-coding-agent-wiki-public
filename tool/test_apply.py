"""apply 의 병합이 기존 설정을 지우지 않는지 증명한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from apply import (  # noqa: E402
    continuation_entry,
    hook_entry,
    merge,
    script_entry,
    sync_entry,
)

PY = "C:/py.exe"
OTHER_HOOK = {
    "hooks": [{"type": "command", "command": "echo 남의-훅"}],
}
OTHER_PRE = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "echo 남의-사전훅"}],
}
OTHER_STOP = {
    "hooks": [{"type": "command", "command": "echo 남의-정지훅"}],
}
LIVED_IN = {
    "permissions": {
        "deny": ["Read(./secrets/**)", "Edit(./protected-data/**)"],
        "allow": ["Bash(npm *)"],
    },
    "hooks": {
        "UserPromptSubmit": [OTHER_HOOK],
        "PreToolUse": [OTHER_PRE],
        "PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "fmt"}]}],
    },
    "model": "opus",
}
SCRIPTS = {"english_progress.py": script_entry(PY, "english_progress.py", "확인")}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'통과' if ok else '실패'}  {label}{'  ← ' + detail if detail and not ok else ''}")
    return ok


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    denies = ["Bash(sed -i*)", "Bash(git reset --hard*)"]
    hook = hook_entry(PY, "proj")
    results: list[bool] = []

    print("빈 설정에서\n")
    fresh: dict = {}
    changes = merge(fresh, denies, hook, SCRIPTS)
    results.append(check(
        "deny 두 개가 생긴다",
        fresh["permissions"]["deny"] == denies,
    ))
    results.append(check(
        "훅이 하나 생긴다",
        len(fresh["hooks"]["UserPromptSubmit"]) == 1,
    ))
    results.append(check(
        "PreToolUse 훅이 생긴다",
        len(fresh["hooks"]["PreToolUse"]) == 1,
    ))
    results.append(check("바뀐 것을 보고한다", len(changes) == 4, str(changes)))

    print("\n이미 살던 설정에서\n")
    lived = json.loads(json.dumps(LIVED_IN))
    merge(lived, denies, hook, SCRIPTS)
    deny = lived["permissions"]["deny"]
    results.append(check(
        "기존 deny 가 남는다",
        deny[:2] == LIVED_IN["permissions"]["deny"],
        str(deny),
    ))
    results.append(check("새 deny 가 뒤에 붙는다", deny[2:] == denies, str(deny)))
    results.append(check(
        "allow 를 안 건드린다",
        lived["permissions"]["allow"] == ["Bash(npm *)"],
    ))
    results.append(check(
        "남의 UserPromptSubmit 훅이 남는다",
        OTHER_HOOK in lived["hooks"]["UserPromptSubmit"],
    ))
    results.append(check(
        "남의 PreToolUse 훅이 남는다",
        OTHER_PRE in lived["hooks"]["PreToolUse"],
    ))
    results.append(check(
        "다른 이벤트 훅을 안 건드린다",
        lived["hooks"]["PostToolUse"] == LIVED_IN["hooks"]["PostToolUse"],
    ))
    results.append(check("모르는 키를 안 건드린다", lived["model"] == "opus"))

    print("\n두 번 돌려도\n")
    again = merge(lived, denies, hook, SCRIPTS)
    results.append(check("바뀌는 것이 없다", again == [], str(again)))
    results.append(check(
        "훅이 안 늘어난다",
        len(lived["hooks"]["UserPromptSubmit"]) == 2
        and len(lived["hooks"]["PreToolUse"]) == 2,
    ))

    print("\nStop 이 둘일 때\n")
    # 한 이벤트에 이 위키의 훅이 둘 걸리는 유일한 자리다. `put_hook` 이 이름이
    # 아니라 명령 안의 스크립트 경로로 자기 것을 알아보므로 둘이 서로를 덮으면
    # 안 되고, 남의 Stop 훅도 그대로 남아야 한다.
    both: dict = {"hooks": {"Stop": [OTHER_STOP]}}
    merge(both, [], hook, SCRIPTS, None, sync_entry(PY, "proj"), continuation_entry(PY))
    stop = [e["command"] for g in both["hooks"]["Stop"] for e in g["hooks"]]
    results.append(check("sync 가 선다", any("sync.py" in c for c in stop), str(stop)))
    results.append(check(
        "되돌림 훅이 선다",
        any("declared_continuation.py" in c for c in stop),
        str(stop),
    ))
    results.append(check("남의 Stop 훅이 남는다", OTHER_STOP in both["hooks"]["Stop"]))
    twice = merge(
        both, [], hook, SCRIPTS, None, sync_entry(PY, "proj"), continuation_entry(PY)
    )
    results.append(check("두 번 돌려도 안 늘어난다", twice == [], str(twice)))

    print("\n어댑터가 바뀌면\n")
    moved = merge(lived, denies, hook_entry(PY, "다른프로젝트"), SCRIPTS)
    commands = [
        e["command"]
        for g in lived["hooks"]["UserPromptSubmit"]
        for e in g["hooks"]
        if "inject.py" in e["command"]
    ]
    results.append(check(
        "명령을 갱신한다",
        moved == ["UserPromptSubmit 훅 명령 갱신: tool/inject.py"],
        str(moved),
    ))
    results.append(check("훅을 새로 안 만든다", len(commands) == 1, str(commands)))
    results.append(check("새 어댑터를 쓴다", "다른프로젝트" in commands[0], commands[0]))

    # A renamed hook. Without this check the old entry stayed in
    # `settings.json`, and deleting the script failed every tool call with
    # "can't open file" until the shim went back.
    old = {"hooks": {"PreToolUse": [script_entry(PY, "korean_progress.py", "옛것")]}}
    merge(old, [], hook, SCRIPTS)
    left = [
        e["command"]
        for g in old["hooks"]["PreToolUse"]
        for e in g["hooks"]
    ]
    results.append(check(
        "이름이 바뀐 옛 훅을 지운다",
        not any("korean_progress.py" in c for c in left),
        str(left),
    ))
    results.append(check(
        "새 훅은 남긴다",
        any("english_progress.py" in c for c in left),
        str(left),
    ))
    # Twice has to give the same answer: an upgrade reads an existing install.
    merge(old, [], hook, SCRIPTS)
    twice_left = [e["command"] for g in old["hooks"]["PreToolUse"] for e in g["hooks"]]
    results.append(check("두 번 적용해도 같다", twice_left == left, str(twice_left)))

    # No replacement wired means no removal. Removing it would turn the
    # enforcement off without saying so.
    alone = {"hooks": {"PreToolUse": [script_entry(PY, "korean_progress.py", "옛것")]}}
    from apply import retire

    results.append(check(
        "새것이 없으면 옛것을 안 지운다",
        retire(alone, "korean_progress.py", "english_progress.py") == []
        and len(alone["hooks"]["PreToolUse"]) == 1,
        str(alone),
    ))

    # The person's own hook that merely names the retired script. Matching on
    # the bare filename deleted it, which is the loss this whole file exists
    # to prevent — and `put_hook` would have overwritten it on the way in.
    theirs = {"hooks": {"PreToolUse": [{"hooks": [{
        "type": "command",
        "command": "python audit.py --watch korean_progress.py",
    }]}]}}
    merge(theirs, [], hook, SCRIPTS)
    kept = [e["command"] for g in theirs["hooks"]["PreToolUse"] for e in g["hooks"]]
    results.append(check(
        "이름만 같은 남의 훅은 안 지운다",
        any("audit.py" in c for c in kept),
        str(kept),
    ))
    results.append(check(
        "남의 훅을 덮어쓰지도 않는다",
        any(c == "python audit.py --watch korean_progress.py" for c in kept),
        str(kept),
    ))

    # 소유 판정은 명령 문자열에 이름이 들어 있느냐가 아니다. 두 라운드가 그
    # 답으로 갔다 — 먼저 맨 파일명이, 그다음 `tool/` 접두가 뚫렸다.
    # `custom-tool/` 은 `tool/` 로 끝난다.
    from apply import runs

    import tempfile
    from apply import HERE

    here = HERE.as_posix()
    # 남이 진짜로 `tool/` 안에 같은 이름의 스크립트를 갖고 있는 경우. 부모
    # 디렉터리 이름만 보던 판정이 이것을 자기 것이라고 했다 — 세 라운드째
    # 같은 자리다. 실제로 파일을 만들어야 재현된다.
    with tempfile.TemporaryDirectory() as tmp:
        theirs = Path(tmp) / "tool"
        theirs.mkdir()
        (theirs / "korean_progress.py").write_text("# 남의 것\n", encoding="utf-8")
        for command, script, want, why in [
            ("python audit.py --watch korean_progress.py", "korean_progress.py",
             False, "이름만 대는 남의 훅"),
            ('"py" "C:/repo/custom-tool/korean_progress.py"', "korean_progress.py",
             False, "디렉터리 이름이 tool 로 끝나는 남의 훅"),
            (f'"py" "{(theirs / "korean_progress.py").as_posix()}"',
             "korean_progress.py", False, "진짜 tool/ 안에 있는 남의 스크립트"),
            (f'"py" "{here}/korean_progress.py"', "korean_progress.py",
             True, "우리 디렉터리, 이미 지운 스크립트"),
            (f'& "py" "{here}/declared_continuation.py" --codex',
             "declared_continuation.py", True, "Codex 가 붙이는 & 와 인자"),
            ('"py" "Z:/team/tool/inject.py" --adapter x', "inject.py",
             False, "끊긴 드라이브 위의 남의 훅 — 없는 경로는 안 가진다"),
            ('"python" "tool/inject.py"', "inject.py",
             False, "대상 프로젝트의 상대경로 훅"),
            ('"python" "tool/korean_progress.py"', "korean_progress.py",
             False, "상대경로 — 지운 이름이어도 남의 것"),
            # 우리 경로를 *데이터로* 넘기는 남의 훅. 따옴표 인자를 전부 훑으면
            # 이것이 우리 것이 되고, `put_hook` 이 남의 audit.py 훅을 덮는다.
            (f'"C:/Python/python.exe" "C:/project/audit.py" --watch "{here}/inject.py"',
             "inject.py", False, "우리 경로를 인자로 받는 남의 훅"),
            (f'"py" "{here}/inject.py" --adapter x', "sync.py",
             False, "다른 스크립트"),
        ]:
            results.append(check(f"소유 판정: {why}", runs(command, script) == want, command))

        # 판정이 `apply.py` 를 어디서 돌렸는지에 따라 달라지면 안 된다.
        # 허브 루트에서 돌리면 `tool/inject.py` 가 `HERE/inject.py` 로
        # 풀려서 남의 훅이 우리 것이 됐다.
        import os

        was = Path.cwd()
        try:
            os.chdir(HERE.parent)
            here_says = runs('"python" "tool/inject.py"', "inject.py")
            os.chdir(tmp)
            there_says = runs('"python" "tool/inject.py"', "inject.py")
        finally:
            os.chdir(was)
        results.append(check(
            "소유 판정: 작업 디렉터리를 안 탄다",
            here_says is False and there_says is False,
            f"허브에서 {here_says}, 다른 곳에서 {there_says}",
        ))

    # 없는 경로를 가진 훅은 지우지 않고 말한다. 위키를 옮긴 흔적일 수도,
    # 잠깐 끊긴 공유 드라이브 위의 남의 훅일 수도 있고 명령만 보고는
    # 구별이 안 된다. 지우는 쪽을 고르면 남의 설정을 네트워크 한 번
    # 끊겼다고 부순다.
    from apply import stale

    ghost = {"hooks": {"PreToolUse": [{"hooks": [
        {"type": "command", "command": '"py" "Z:/team/tool/inject.py"'},
    ]}]}}
    said = stale(ghost)
    results.append(check("없는 경로를 가진 훅을 말한다", len(said) == 1, str(said)))
    results.append(check(
        "말하되 안 지운다",
        len(ghost["hooks"]["PreToolUse"][0]["hooks"]) == 1,
        str(ghost),
    ))
    results.append(check(
        "멀쩡한 자기 훅은 안 말한다",
        stale({"hooks": {"UserPromptSubmit": [hook]}}) == [],
        str(stale({"hooks": {"UserPromptSubmit": [hook]}})),
    ))
    # 실행되는 것은 `audit.py` 다. 없는 경로는 그 훅이 지켜보는 대상일 뿐이라
    # "훅이 없는 파일을 가리킨다" 는 말이 사실이 아니다.
    watcher = {"hooks": {"PreToolUse": [{"hooks": [{
        "type": "command",
        "command": '"py" "C:/project/audit.py" --watch "Z:/archive/tool/inject.py"',
    }]}]}}
    results.append(check(
        "인자로 받은 없는 경로는 안 말한다", stale(watcher) == [], str(stale(watcher)),
    ))

    print()
    if all(results):
        print(f"{len(results)}건 전부 통과. 병합이 기존 설정을 안 지운다.")
        return 0
    print(f"{results.count(False)}건 실패.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
