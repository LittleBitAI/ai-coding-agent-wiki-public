"""lint — 위키가 썩는 다섯 자리를 찾는다."""

from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from wikilib import (  # noqa: E402
    SCOPES, WIKI, git_ok, links_of, metadata_errors, pages, resolve,
)


def check(
    wiki: Path = WIKI,
    adapters: Path | None = None,
    repos: list[Path] | None = None,
) -> tuple[dict[str, tuple[dict, str, Path]], set[frozenset[str]], list[tuple[str, str]]]:
    """페이지를 읽어 발견을 낸다. 인쇄는 `main` 이 한다.

    `wiki` 를 인자로 받는 이유는 이 함수를 임시 위키에 돌려 각 검사가 실제로
    빨개지는지 보기 위해서다. 발견 0건짜리 초록은 검사가 도는 증거가 아니다.
    """

    adapters = adapters if adapters is not None else wiki / "adapters"
    repos = repos or []

    loaded = pages(wiki)
    names = set(loaded)
    findings: list[tuple[str, str]] = []
    for name, (_meta, _body, path) in loaded.items():
        findings.extend(("페이지 형식 오류", f"`{name}`: {error}") for error in metadata_errors(path))
    if wiki.resolve() == WIKI.resolve():
        from apply import wiring_drift
        findings += wiring_drift(wiki)
    findings += fragile_io(wiki)
    findings += loud_emphasis(wiki)
    # `--repo` 로 준 저장소도 본다. `repo_lint` 가 같은 검사를 들지만 그것은
    # 대상 저장소에서 따로 도는 것이라, 허브에서 한 번에 훑을 때 안 보면
    # "여기서는 전부 봤다" 가 거짓이 된다.
    for repo in repos:
        findings += loud_emphasis(repo)
    findings += missing_hook_guards(wiki, loaded)

    # --- 1. 끊어진 링크
    inbound: dict[str, set[str]] = {name: set() for name in names}
    for name, (meta, body, _path) in loaded.items():
        for target in links_of(meta, body):
            hit = resolve(target, names)
            if hit is None:
                findings.append(("끊어진 링크", f"`{name}` → `[[{target}]]` 가 없다"))
            else:
                inbound[hit].add(name)

    # --- 2. 고아 페이지
    for name in sorted(names):
        if not inbound[name]:
            findings.append((
                "고아 페이지",
                f"`{name}` 를 아무도 링크하지 않는다",
            ))

    # --- 3. 낡은 서술 (기계가 확실히 아는 것만)
    for name, (meta, body, _path) in loaded.items():
        severity = str(meta.get("severity") or "")
        # Public exports retain severity while withholding the private source records.
        if severity == "landmine" and not (meta.get("sources") or []) and meta.get("sources_withheld") is not True:
            findings.append((
                "근거 없는 landmine",
                f"`{name}` 이 `landmine` 인데 `sources` 가 비었다. "
                "무엇을 태웠는지 못 대면 등급을 내려라",
            ))
        if severity in ("landmine", "contract") and not (meta.get("triggers") or []):
            findings.append((
                "낡은 서술",
                f"`{name}` 이 `{severity}` 인데 `triggers` 가 없다. "
                "주입 대상인데 걸릴 발화가 없으니 아무 때도 안 실린다",
            ))
        for source in meta.get("sources") or []:
            path = wiki / str(source).split("#")[0]
            if not path.exists():
                findings.append(("낡은 서술", f"`{name}` 의 근거 `{source}` 가 없다"))
        refs = set(re.findall(r"`((?:feat|fix|chore|claude)/[a-z0-9-]+)`", body))
        for repo in repos:
            for ref in refs:
                if not git_ok(repo, ref):
                    findings.append((
                        "낡은 서술",
                        f"`{name}` 가 `{ref}` 를 가리키는데 `{repo.name}` 에 없다",
                    ))

    # --- 4. 모순 — 선언되지 않은 것만
    declared: set[frozenset[str]] = set()
    for name, (meta, _body, _path) in loaded.items():
        for entry in meta.get("conflicts_with") or []:
            other = entry.get("page") if isinstance(entry, dict) else str(entry)
            if other:
                declared.add(frozenset({name, other}))

    slot_values: dict[str, dict[str, str]] = {}
    if adapters.is_dir():
        for path in sorted(adapters.glob("*.toml")):
            import tomllib
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            for slot, value in (data.get("slots") or {}).items():
                slot_values.setdefault(slot, {})[path.stem] = str(value)

    for slot, by_project in sorted(slot_values.items()):
        distinct = set(by_project.values())
        if len(distinct) > 1:
            where = " · ".join(f"{k}={v!r}" for k, v in sorted(by_project.items()))
            findings.append((
                "모순(슬롯)",
                f"`{slot}` 이 프로젝트마다 다르다 — {where}. "
                "형태만 공유하고 값은 다른 것이 정상이면 그대로 두라. "
                "슬롯은 원래 그러라고 있다",
            ))

    # --- 5. 빠진 연결
    #
    # 같은 발화에 함께 주입되는가로 잰다. 한 턴에 나란히 실리는 두 규칙이
    # 서로를 모르면 읽는 쪽이 둘의 관계를 못 읽는다. 그것이 빠진 연결이다.
    #
    # 근거 공유로는 재지 않는다. 근거가 census 코퍼스 파일이면 모든 페이지가
    # 그것을 공유하므로 전부가 서로 이어진 것처럼 보인다. 코퍼스는 특정 주장이
    # 아니라 자료 전체다.
    triggers_of = {
        name: [str(t) for t in (meta.get("triggers") or [])]
        for name, (meta, _b, _p) in loaded.items()
    }
    for a in sorted(names):
        for b in sorted(names):
            if a >= b or not triggers_of[a] or not triggers_of[b]:
                continue
            if b in inbound[a] or a in inbound[b]:
                continue
            if frozenset({a, b}) in declared:
                continue
            shared = sorted(set(triggers_of[a]) & set(triggers_of[b]))
            if shared:
                findings.append((
                    "빠진 연결",
                    f"`{a}` 와 `{b}` 가 같은 발화에 함께 실리는데"
                    f"(공유 트리거 {shared[:2]}) 서로 링크하지 않는다",
                ))

    # --- 7. 인코딩을 환경에 맡긴 도구
    for name in fragile_tools(wiki):
        findings.append((
            "인코딩 미고정",
            f"`tool/{name}` 이 stdout 에 쓰는데 인코딩을 고정하지 않는다 — "
            'cp949 에서 한 글자에 죽는다. `sys.stdout.reconfigure(encoding="utf-8")`',
        ))

    # --- 8. 폭에 맞추려고 한 호흡을 갈라 놓은 줄바꿈
    for where, before, after in broken_wraps(wiki):
        findings.append((
            "끊긴 줄바꿈",
            f"`{where}` 이 `{before} / {after}` 사이에서 끊긴다 — "
            "폭이 아니라 문장·절 경계에서 끊어라",
        ))

    return loaded, declared, findings




def fragile_tools(wiki: Path = WIKI) -> list[str]:
    """stdout 에 쓰면서 인코딩을 고정하지 않는 `tool/*.py`.

    **한글이 있는지는 안 본다.** 오늘 ASCII 만 내보내는 도구도 내일 한 줄이
    늘면 죽고, 고정은 한 줄이다 — 조건을 좁히면 그 좁힌 자리가 다음 사고다.
    실제로 이 검사를 쓰게 만든 것이 `lint.py` 자신이었고, 그것은 파일을
    `encoding="utf-8"` 로 읽고 있었다. 읽기를 고쳐도 쓰기는 안 고쳐진다.

    `craft/hooks-fail-open` 은 이 실패를 훅에 대해 적었지만, 실패하는 조건은
    훅이라는 것이 아니라 **stdout 이 파이프인 파이썬** 이다. 훅 넷이 고쳐지고
    같은 조건의 CLI 여덟이 안 고쳐진 채 남은 것이 그 좁힘의 값이다.
    """
    directory = wiki / "tool"
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.py")):
        calls = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                 if isinstance(n, ast.Call)]
        writes = any(ast.unparse(n.func) in ("print", "json.dump", "sys.stdout.write") for n in calls)
        fixed = any(ast.unparse(n.func) == "sys.stdout.reconfigure" and any(
            k.arg == "encoding" and isinstance(k.value, ast.Constant) and k.value.value == "utf-8"
            for k in n.keywords
        ) for n in calls)
        if writes and not fixed:
            found.append(path.name)
    return found


def missing_hook_guards(wiki: Path, loaded: dict) -> list[tuple[str, str]]:
    """공유 이벤트 훅과 페이지가 선언한 훅의 진입점 가드를 검사한다."""
    names = {"inject.py", "session_state.py", "sync.py", "declared_continuation.py", "codex_pretool.py"}
    for meta, _body, _path in loaded.values():
        enforce = meta.get("enforce") or {}
        if isinstance(enforce, dict) and enforce.get("pretooluse"):
            names.add(str(enforce["pretooluse"]))
    found = []
    for name in sorted(names):
        path = wiki / "tool" / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        entries = [node for node in tree.body if isinstance(node, ast.If)
                   and ast.unparse(node.test) == "__name__ == '__main__'"]
        guarded = any(
            isinstance(node, ast.Try) and any(
                isinstance(call, ast.Call)
                for statement in node.body for call in ast.walk(statement)
            ) and any(
                handler.type and ast.unparse(handler.type) == "Exception" and (any(
                    isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Constant)
                    and statement.value.value == 0 for statement in handler.body
                ) or not any(isinstance(statement, ast.Raise) for statement in ast.walk(entry)))
                for handler in node.handlers
            ) for entry in entries for node in entry.body
        )
        if not guarded:
            found.append(("훅 가드 누락", f"`tool/{name}`: 진입점 예외를 통과시키는 가드가 없다"))
    return found


def tracked_markdown(root: Path) -> list[str]:
    """이 저장소가 자기 것이라고 보는 `.md`. 손으로 쓴 제외 목록을 안 쓴다.

    처음엔 `web/`·`artifacts/`·`raw/`·`node_modules` 를 이름으로 걸렀다. 허브의
    사정이고 대상 저장소의 사정이 아니라, 남의 저장소에서는 진짜 문서가 통째로
    빠졌다. `node_modules-guide.md` 처럼 이름이 앞자리만 같은 파일도 같이 빠졌다.

    "이 파일이 우리 것인가" 는 git 이 이미 답을 안다. 추적되는 것과 아직
    `git add` 안 했지만 무시 대상도 아닌 것을 본다 — 생성물과 vendor 는
    `.gitignore` 에 있으므로 빠지고, 아무도 리뷰하지 않는다.
    """

    # `-c` 는 인덱스, `-o` 는 아직 `git add` 안 한 것, `--exclude-standard` 가
    # 무시 대상을 뺀다. `-c` 만 보면 방금 `Write` 로 만든 새 문서가 통째로 안
    # 보이고, 그 파일에 조각 편집이 쌓이면 어느 검사도 그것을 안 보게 된다.
    #
    # 확장자를 pathspec 으로 안 거른다. `*.md` 는 대소문자를 가려 `UPPER.MD` 를
    # 빼는데 훅은 소문자로 바꿔 판정하므로, 두 검사가 서로 다른 집합을 보게 된다.
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "-co", "--exclude-standard"],
        capture_output=True, check=False,
    )
    if done.returncode == 0:
        names = done.stdout.decode("utf-8", "replace").split("\0")
    else:
        # git 저장소가 아니면 전부 본다. 이 경로는 임시 디렉터리를 쓰는 시험이다.
        names = [p.relative_to(root).as_posix() for p in root.rglob("*")]
    # 인덱스에 남고 작업 트리에서 지워진 것은 뺀다. 지우는 중인 파일을 못 읽었다고
    # 보고하면 정상적인 삭제가 게이트를 빨갛게 만든다.
    return sorted(
        name for name in names
        if name.lower().endswith(".md") and (root / name).is_file()
    )


def loud_emphasis(wiki: Path = WIKI) -> list[tuple[str, str]]:
    """강조가 소음이 된 `.md`. 훅이 못 보는 자리를 여기서 본다.

    `markdown_emphasis` 훅은 쓰기 **전에** 불리므로 `Edit` 이나 패치가 만들
    문서를 못 본다. 그것을 예측하려 한 판이 리뷰 세 라운드 동안 입력 모양마다
    구멍을 냈다 — 여러 hunk, `replace_all`, 백틱 네 개. 예측을 지우고 여기서
    실제 파일을 읽는다. 읽을 것이 이미 디스크에 있으므로 틀릴 자리가 없다.
    """

    import markdown_emphasis

    found = []
    if markdown_emphasis.parser() is None:
        # 검사를 못 돌린 것과 돌려서 깨끗한 것은 다른 일이다. 여기서 조용히
        # 빈 목록을 돌려주면 게이트가 초록인 채로 이 규칙만 꺼져 있게 된다.
        return [("강조 과다", markdown_emphasis.MISSING)]
    for name in tracked_markdown(wiki):
        path = wiki / name
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as error:
            # 못 읽은 파일을 건너뛰면 "전부 봤다" 가 거짓이 된다. 이 저장소는
            # UTF-8 로 적는 것이 규칙이므로, 못 읽은 것 자체가 발견이다.
            found.append(("강조 과다", f"`{name}`: 읽지 못했다 ({type(error).__name__})"))
            continue
        for line in markdown_emphasis.findings(text):
            found.append(("강조 과다", f"`{name}`: {line.lstrip('- ')}"))
    return found


def fragile_io(wiki: Path = WIKI) -> list[tuple[str, str]]:
    """stdin과 운영 도구의 텍스트 자식 출력. 테스트의 엄격한 디코딩은 유지한다."""
    found = []
    for path in sorted((wiki / "tool").glob("*.py")):
        calls = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                 if isinstance(n, ast.Call)]
        reads = any(ast.unparse(n.func).startswith("sys.stdin.read") or (
            ast.unparse(n.func) == "json.load" and n.args and ast.unparse(n.args[0]) == "sys.stdin"
        ) for n in calls)
        fixed = any(ast.unparse(n.func) == "sys.stdin.reconfigure" and any(
            k.arg == "encoding" and isinstance(k.value, ast.Constant) and k.value.value == "utf-8"
            for k in n.keywords
        ) for n in calls)
        if reads and not fixed:
            found.append(("인코딩 미고정", f"`tool/{path.name}`: stdin UTF-8 고정이 없다"))
        if path.name.startswith("test_"):
            continue
        for call in calls:
            if ast.unparse(call.func) not in ("subprocess.run", "subprocess.Popen"):
                continue
            kw = {k.arg: ast.literal_eval(k.value) for k in call.keywords if isinstance(k.value, ast.Constant)}
            if (kw.get("text") or kw.get("universal_newlines") or kw.get("encoding")) and (
                kw.get("encoding") != "utf-8" or kw.get("errors") != "replace"
            ):
                found.append(("인코딩 미고정", f"`tool/{path.name}:{call.lineno}`: 자식 출력의 UTF-8/replace 누락"))
    return found


# 한국어에서 `쓰는 것`·`없을 때`·`한 줄` 은 띄어 쓰되 한 호흡이다. 그 사이가
# 줄바꿈이면 읽는 쪽이 두 번 읽는다. 폭 상한에 맞추다 여기를 끊은 자리가
# 네 저장소에 있었고, 한글 주석 줄의 61%·54%가 표시폭 70~79칸에 몰려 있었다.
#
# 뒷말은 앞을 좁게 본다. `것` 은 그 글자로 시작하는 다른 낱말이 없어 그냥 두지만,
# `수`·`때`·`데` 는 `수집`·`때문에`가 아닌 것을 조사로 갈라야 한다. 넓게 잡으면
# `채우는 / 자리` 같은 평범한 수식-피수식 줄바꿈까지 짚고, 그건 판단이다.
BOUND_NOUN = re.compile(
    r"^(?:것"
    r"|수(?=[\s가는도를]|$)"
    r"|때(?=문|만|는|가|에|도|까지|$)"
    r"|데(?=만|는|가|에|다|서|$)"
    r"|뿐(?=[\s이만]|$)"
    r"|만큼(?=[\s은는이]|$)"
    r"|듯(?=[\s이하]|$)"
    r"|터(?=[\s이는]|$))"
)
COUNTER_MOD = re.compile(r"(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|몇|여러|\d+)$")
COUNTER = re.compile(r"^(?:줄|번|개|장|건|칸|가지|쪽|권|명)(?=[\s으로은는이가도만짜]|$)")


def ends_adnominal(word: str) -> bool:
    """마지막 글자의 받침이 ㄴ·ㄹ 인가. 관형형은 전부 그렇게 끝난다.

    `굳은`·`쓰는`·`없을`·`만든` 이 한 줄로 걸린다. 낱자를 나열하는 정규식으로는
    `만든` 을 못 잡는다 — `만들 + ㄴ` 이 한 글자로 합쳐져 있어서, 봐야 하는 것이
    낱자가 아니라 받침이기 때문이다.
    """

    if not word:
        return False
    code = ord(word[-1]) - 0xAC00
    return 0 <= code < 11172 and code % 28 in (4, 8)


def splits_a_phrase(before: str, after: str) -> bool:
    """앞 줄의 마지막 낱말과 뒷 줄의 첫 낱말이 갈라놓으면 안 되는 짝인가."""

    before = before.rstrip("`*_")
    after = after.lstrip("`*_(")
    if ends_adnominal(before) and BOUND_NOUN.match(after):
        return True
    return bool(COUNTER_MOD.search(before) and COUNTER.match(after))


def prose_lines(path: Path) -> list[tuple[int, str]]:
    """산문 줄만 (줄번호, 본문) 으로. 코드·표·목록·front matter 는 안 본다.

    `.py` 는 주석과 삼중따옴표 문자열을 본다. 둘은 같은 규칙을 받는다 — 폭에
    맞추다 호흡을 가르는 것에 주석과 docstring 의 구별이 없다.
    """

    text = path.read_text(encoding="utf-8")
    rows: list[tuple[int, str]] = []

    if path.suffix == ".md":
        lines = text.splitlines()
        start = 0
        if lines and lines[0].strip() == "---":
            closing = next(
                (i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), 0
            )
            start = closing + 1
        fenced = False
        for number, raw in enumerate(lines[start:], start + 1):
            line = raw.strip()
            if line.startswith("```"):
                fenced = not fenced
                continue
            if fenced or not line or line.startswith(("|", "#", "-", "*", ">", "1.")):
                continue
            rows.append((number, line))
        return rows

    lines = text.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    for token in tokens:
        if token.type == tokenize.COMMENT:
            body = lines[token.start[0] - 1].strip()
            if body.startswith("#"):
                rows.append((token.start[0], body.lstrip("# ").strip()))
        elif token.type == tokenize.STRING and token.string.lstrip(
            "rbuRBUfF"
        ).startswith(('"""', "'''")):
            for offset, body in enumerate(token.string.splitlines()):
                stripped = body.strip().strip("\"'")
                if stripped:
                    rows.append((token.start[0] + offset, stripped))
    return sorted(rows)


def broken_wraps(wiki: Path = WIKI) -> list[tuple[str, str, str]]:
    """폭에 맞추려고 한 호흡을 갈라 놓은 자리. `(어디, 앞말, 뒷말)`.

    페이지 산문도 같이 본다. 규칙을 담은 문서가 그 규칙을 어기고 있던 자리가
    실제로 다섯이었고, 그중 하나는 이 위키가 어떻게 끊어야 하는지 설명하는
    문단이었다. 검사가 자기를 못 보는 자리는 오래 산다.
    """

    targets = sorted((wiki / "tool").glob("*.py"))
    for scope in SCOPES:
        targets += sorted((wiki / scope).glob("*.md"))

    found: list[tuple[str, str, str]] = []
    for path in targets:
        rows = prose_lines(path)
        for (number, first), (following, second) in zip(rows, rows[1:]):
            if following != number + 1:
                continue
            before, after = first.split(), second.split()
            if not before or not after:
                continue
            if splits_a_phrase(before[-1], after[0]):
                where = path.relative_to(wiki).as_posix()
                found.append((f"{where}:{number}", before[-1], after[0]))
    return found


def main() -> int:
    # 출력이 파이프로 가면 기본이 cp949 다. 인코딩을 환경에 안 맡긴다.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="위키의 썩은 자리를 찾는다")
    parser.add_argument("--wiki", type=Path, default=WIKI)
    parser.add_argument("--adapters", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="게이트용: 슬롯 값 차이만 종료 코드에서 제외")
    parser.add_argument(
        "--repo", action="append", type=Path, default=[],
        help="같이 검진할 저장소. 낡은 서술과 그 저장소의 `.md` 강조를 본다. "
             "무시 대상이 아닌 `.md` 는 아직 `git add` 안 한 것도 본다. "
             "여러 번 줄 수 있다",
    )
    args = parser.parse_args()

    loaded, declared, findings = check(args.wiki, args.adapters, args.repo)

    print(f"# lint — 페이지 {len(loaded)}장\n")

    if declared:
        print(f"## 선언된 갈림 {len(declared)}쌍 — lint 가 지나간다\n")
        for pair in sorted(declared, key=lambda s: sorted(s)):
            print(f"- {' ↔ '.join(sorted(pair))}")
        print()

    if not findings:
        print("새 발견 없음.")
        return 0

    print(f"## 발견 {len(findings)}건\n")
    kinds: dict[str, list[str]] = {}
    for kind, message in findings:
        kinds.setdefault(kind, []).append(message)
    for kind in (
        "훅 배선 드리프트", "훅 가드 누락", "페이지 형식 오류", "인코딩 미고정", "강조 과다", "끊어진 링크", "근거 없는 landmine", "낡은 서술",
        "모순(슬롯)", "고아 페이지", "빠진 연결", "끊긴 줄바꿈",
    ):
        if kind not in kinds:
            continue
        print(f"### {kind} — {len(kinds[kind])}건\n")
        for message in kinds[kind]:
            print(f"- {message}")
        print()
    return int(any(kind != "모순(슬롯)" for kind, _message in findings)) if args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
