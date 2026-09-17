# 개발과 검사

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check tool
python -m pytest -q tool
python tool/test_lint.py
python tool/test_apply.py
python tool/test_inject.py
python tool/test_declared_continuation.py
python tool/test_repo_lint.py
python tool/test_slack_brief.py
python tool/test_trajectory.py
python tool/lint.py --check
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run build
python tool/graph.py
```

가상 환경을 사용한다면 그 환경의 Python으로 실행합니다.
`graph.json`은 공용 규칙에서 생성하며 Git에서 제외합니다. 실제 프로젝트를 지정해 지도를 만들면
그 프로젝트의 경로·상태가 포함될 수 있으므로 결과를 공개본에 추가하지 않습니다.
지도 파일은 위의 `python tool/graph.py` 명령으로 새로 생성합니다.

자동 검사는 임시 프로젝트를 사용합니다. 실제 사용자의 대화 기록은 테스트 입력이 아닙니다.
설정 병합·재설치·한글 및 공백 경로·동명 checkout의 설정 분리를 확인합니다.
실제 OAuth 로그인 성공, 호스트 자동 이벤트, 답변 품질 검수는 이 검사 결과에 포함되지 않습니다.

hooks 구현을 바꿨다면 [호스트 확인 절차](hooks-setup.md)도 따릅니다.
공개 전에는 [공개본 갱신 절차](publishing.md)로 파일과 Git 이력을 검사합니다.

## 이 저장소 자체를 규칙에 연결하기

이 위키도 유지보수 대상이므로 같은 hooks를 자기 자신에게 겁니다. 지정 방법은
[hooks 설치 안내](hooks-setup.md)와 같고 `--project`가 이 저장소일 뿐입니다. checkout마다 한 번 실행합니다.

먼저 이 저장소의 `.wiki/adapter.toml`을 만듭니다. 공개본은 배선 파일을 Git에 두지 않으므로
(`tool/test_distribution.py`가 검사합니다) 각 checkout에서 직접 씁니다.

```toml
agents = ["claude", "codex"]

[slots]
review_dir = "artifacts/review"
gate_cmd = "python -m pytest tool"
live_cmd = "새 Claude Code·Codex 세션을 각각 열어 훅이 실제로 도는지 확인한다"
server_stop = "tool/chat.cmd(macOS·Linux는 tool/chat.command)를 실행한 터미널에서 Ctrl+C"
scratch_dirs = "artifacts/"
```

```powershell
python tool/setup_agents.py --project . --agent both
```

대상이 위키 자신이면 `.wiki/wiki-revision` 핀과 실행 코드 dirty 검사를 하지 않습니다.
핀은 "대상이 어느 위키 버전에 묶였나"를 묻는 값인데 대상이 위키면 답이 언제나 현재 HEAD라,
커밋할 때마다 낡고 도구를 고치는 중에는 늘 dirty가 됩니다. 다른 프로젝트에 설치할 때는 그대로 검사합니다.

`.wiki/adapter.toml`·`.claude/settings.json`·`.codex/hooks.json`·`.codex/config.toml`은 모두 Git에서 제외합니다.
절대 경로와 기계별 설정이 들어가고, 공개본은 런타임 배선을 버전 관리 밖에 둡니다.
Codex를 쓴다면 자기 checkout의 `.codex/config.toml`에 `[features]`의 `hooks = true`를 직접 넣습니다.

Windows에서는 설치와 검사를 PowerShell에서 실행합니다. Git Bash 안에서 실행하면 `git`이
`mingw64/bin`으로 잡혀 설치 도구가 Git Bash를 찾지 못하고, 같은 이유로 `tool/test_codex_hooks.py`가
실패합니다. Git Bash에서 돌려야 한다면 `CLAUDE_CODE_GIT_BASH_PATH`에 실제 `bash.exe`를 지정합니다.

기록은 이 저장소의 `.wiki/`에만 쌓입니다. `corpus.json`·`graph.json`·`decisions/`는 저장소별이라
다른 프로젝트의 `.wiki/`와 섞이지 않습니다. 뿌리의 `graph.json`과 `raw/`는 채팅 화면이 쓰는 허브 자산으로 별개입니다.
