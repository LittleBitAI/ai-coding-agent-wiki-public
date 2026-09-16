"""두 축의 예산이 실제로 갈려 있는지 본다."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

WORD = "예산시험어"
MARK = "<!-- wiki:decisions -->"

RULE = f"""---
scope: craft
severity: contract
triggers: ["{WORD}"]
slots: []
sources: []
links: []
---

# 규칙 제목

규칙. {"버" * 120}

왜. {"근" * 120}
"""

DECISION = """---
scope: project
severity: contract
triggers: ["{word}"]
---

# 결정 {n} 의 제목

왜. {why} 그리고 여기부터는 요약에 안 들어간다.
"""


def build(decisions: int, rule_budget: int | None, repo_budget: int | None) -> str:
    """임시 위키와 임시 저장소를 세우고 훅을 한 번 돌린다. 주입문을 돌려준다."""

    root = Path(tempfile.mkdtemp())
    wiki, project = root / "wiki", root / "project"
    (wiki / "craft").mkdir(parents=True)
    (wiki / "craft" / "big.md").write_text(RULE, encoding="utf-8")

    (wiki / "adapters").mkdir()
    slots = ["[slots]"]
    if rule_budget:
        slots.append(f"rule_budget = {rule_budget}")
    if repo_budget:
        slots.append(f"repo_budget = {repo_budget}")
    (wiki / "adapters" / "x.toml").write_text("\n".join(slots) + "\n", encoding="utf-8")

    out = project / ".wiki" / "decisions"
    out.mkdir(parents=True)
    for n in range(decisions):
        (out / f"2026-01-{n + 1:02d}-{n}.md").write_text(
            DECISION.format(word=WORD, n=n, why="왜" * 60), encoding="utf-8"
        )

    done = subprocess.run(
        [sys.executable, str(HERE / "inject.py"), "--adapter", "x",
         "--project", str(project)],
        input=json.dumps({"prompt": f"{WORD} 를 쓴다", "session_id": "t"}),
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "WIKI_ROOT": str(wiki), "PYTHONIOENCODING": "utf-8"},
    )
    payload = json.loads(done.stdout or "{}")
    return payload.get("hookSpecificOutput", {}).get("additionalContext", "")


def rule_half(text: str) -> str:
    """주입문의 규칙 쪽만. 머리말과 부분 사이의 `---` 는 떼어 낸다.

    결정이 없으면 그 구분자도 없다. 안 떼면 결정의 유무 자체가 차이로 잡혀,
    정작 재려는 것을 못 잰다.

    머리말도 뺀다. 출처 표에 대상 저장소의 절대 경로가 들어 있고 `build` 는
    부를 때마다 새 임시 폴더를 만들므로, 안 빼면 경로가 달라 매번 다르다고
    나온다. 이 함수가 재려는 것은 **규칙이 줄었는가** 하나다.
    """

    head = text.split(MARK)[0]
    first = head.find("<!-- wiki:")
    body = head[first:] if first >= 0 else head
    return body.strip().rstrip("-").strip()


def test_결정이_늘어도_규칙이_한_글자도_안_줄어든다():
    # 예산은 규칙 혼자면 남고 결정까지 더하면 모자라도록 잡았다. 한 예산이던
    # 시절이라면 여기서 규칙이 "규칙 한 줄" 로 줄어든다.
    alone = build(decisions=0, rule_budget=700, repo_budget=None)
    crowded = build(decisions=10, rule_budget=700, repo_budget=None)
    assert MARK in crowded, "결정이 실리지 않았다. 시험이 아무것도 안 재고 있다"
    assert rule_half(alone) == rule_half(crowded)
    assert "줄임" not in rule_half(crowded), rule_half(crowded)[:200]


def test_규칙_예산이_모자라면_규칙만_다듬는다():
    text = build(decisions=10, rule_budget=200, repo_budget=None)
    assert "줄임" in rule_half(text), rule_half(text)[:200]
    # 규칙을 다듬었다고 결정이 사라지지는 않는다.
    assert MARK in text


def test_지식_예산은_결정만_다듬는다():
    wide = build(decisions=10, rule_budget=None, repo_budget=None)
    tight = build(decisions=10, rule_budget=None, repo_budget=300)
    assert rule_half(wide) == rule_half(tight)
    assert len(tight.split(MARK)[1]) < len(wide.split(MARK)[1])


def test_지식을_아무리_조여도_이름은_남는다():
    text = build(decisions=10, rule_budget=None, repo_budget=1)
    block = text.split(MARK)[1]
    # 이름은 최신순 여덟까지만 보인다. 가장 새것은 어떤 예산에서도 안 사라진다.
    assert "2026-01-10-9" in block, block
    assert "결정이 10건 있다" in block, block


def test_한_예산이었다면_지식이_규칙을_밀어냈다():
    """왜 갈랐는지를 코드로 남긴다.

    `fit` 은 규칙만 다듬는다. 그런데 한 예산에 둘을 같이 넣으면 넘친 양을
    규칙에서 빼게 되므로, 지식이 늘어난 만큼 규칙이 줄어든다. 다듬는 부담이
    전부 안 늘어난 쪽으로 간다.

    이 시험은 갈라 놓은 지금 코드가 아니라 **갈라 놓지 않았을 때**를 잰다.
    그래야 이 설계가 무엇을 막고 있는지가 초록 하나로 안 지워진다.
    """

    from inject import fit, knowledge

    body = RULE.split("---", 2)[-1].lstrip("\n")
    page = Path("craft") / "big.md"
    rules = [("contract", body, page)]
    rule_parts = [f"<!-- wiki:craft/big (contract) -->\n{body}"]

    decisions = [
        ("contract", DECISION.format(word=WORD, n=n, why="왜" * 60), Path(f"d{n}.md"))
        for n in range(3)
    ]
    repo_parts = knowledge(decisions, None)

    # 규칙 혼자면 남고, 지식까지 더하면 모자라는 예산. 같은 값을 두 방식에 준다.
    limit = len(rule_parts[0]) + 40
    assert len(rule_parts[0]) <= limit < len(rule_parts[0]) + len(repo_parts[0])

    old, squeezed = fit(list(rule_parts) + list(repo_parts), rules, limit)
    new, untouched = fit(list(rule_parts), rules, limit)

    assert untouched == 0 and new == rule_parts, "갈라 놓으면 규칙은 안 줄어든다"
    assert squeezed and old[0] != rule_parts[0], "한 예산이면 규칙이 줄어든다"
    assert old[1] == repo_parts[0], "그런데 지식은 한 글자도 안 줄었다"


def test_예산이_없으면_아무것도_안_다듬는다():
    text = build(decisions=10, rule_budget=None, repo_budget=None)
    assert "줄임" not in text


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
