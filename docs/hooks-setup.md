# 내 프로젝트에 공용 규칙 연결하기

채팅 설치와 hooks 설치는 별개입니다. hooks는 CLI가 시작되거나 질문을 받을 때 실행하는 명령입니다.
공용 위키의 도구를 읽고 프로젝트에 맞는 규칙과 문서를 CLI에 전달합니다.

## 1. 위키 준비

먼저 [채팅 설치 안내](chat-setup.md)에 따라 필요한 CLI에 본인 계정으로 로그인합니다.
채팅 화면이 필요 없다면 Python 3.11 이상 환경에서
`python -m pip install -r <위키경로>/requirements-hooks.txt`만 준비해도 됩니다.
아래 명령의 `python`은 그 패키지들이 설치된 인터프리터여야 합니다.
hooks가 쓰는 패키지는 그 파일 하나에만 적혀 있고, `setup_agents`가 설치 전에 확인합니다.

위키는 경로가 유지되는 깨끗한 Git checkout을 사용합니다. 폴더 이름은 자유롭습니다.
공백·한글 경로를 지원하지만 현재 설치 도구는 따옴표·달러·백틱·줄바꿈이 포함된 경로를 거부합니다.
Windows에서 Claude hooks는 Git for Windows의 Git Bash, Codex hooks는 PowerShell이 필요합니다.

## 2. 프로젝트 설정

대상 프로젝트에 `.wiki/adapter.toml`을 만들고 아래 예시를 실제 검사 명령으로 바꿉니다.
`adapters/example.toml`은 검사에 쓰는 가상 예시이며 실제 프로젝트의 설정이 아닙니다.

```toml
agents = ["claude", "codex"]

[slots]
review_dir = "artifacts/review"
gate_cmd = "python -m pytest"
live_cmd = "새 세션에서 실제 이벤트를 확인한다"
server_stop = "직접 실행한 터미널에서 Ctrl+C"
scratch_dirs = "artifacts/"
```

위키 폴더에서 `git rev-parse HEAD`를 실행해 나온 40자리 값을
**대상 프로젝트**의 `.wiki/wiki-revision`에 한 줄로 저장합니다. UTF-8 without BOM·LF를 사용합니다.
이 값으로 팀원들이 같은 도구 버전을 쓰는지 확인합니다.

Codex를 연결한다면 대상 프로젝트의 `.codex/config.toml`에 다음 항목이 필요합니다.
기존 파일이 있으면 덮어쓰지 말고 해당 항목만 검토해 추가합니다.

```toml
[features]
hooks = true
```

프로젝트가 신뢰할 수 있는지 사용자가 판단하고 CLI에서 신뢰 설정과 `/hooks`를 확인합니다.
설치 도구는 신뢰나 hooks 승인 여부를 대신 결정하지 않습니다.

## 3. 설치와 재설치

공용 위키 폴더에서 실행합니다. 경로는 예시이므로 실제 대상 프로젝트를 지정합니다.

```powershell
python tool/setup_agents.py --project "../example-project" --agent both
python tool/setup_agents.py --project "../example-project" --agent both --check
```

한 CLI만 사용하면 `--agent claude` 또는 `--agent codex`를 선택합니다.
사용할 CLI는 해당 터미널의 PATH에서 찾아야 합니다.
설정은 해당 checkout에서 직접 읽으며 허브로 복사하지 않습니다.
재설치 시 다른 도구가 만든 설정과 이미 설치한 다른 호스트 설정을 보존합니다.

프로젝트나 위키 경로를 옮겼다면 같은 명령으로 다시 설치합니다.
위키 버전을 올릴 때는 변경 내용을 확인하고 `.wiki/wiki-revision`을 새 값으로 바꾼 뒤 재설치합니다.
`--allow-dirty-wiki`는 개발 검사용이며 배포 버전 검증을 대신하지 않습니다.

## 4. 실제 호스트에서 확인하기

`--check` 성공은 설정 배선 검사입니다. 실제 자동 이벤트 성공과 다릅니다.
새 Claude Code·Codex 세션을 각각 열고 다음을 확인합니다.

- 세션 시작 시 프로젝트 문서와 현황이 전달되는지
- 규칙과 관련된 질문에 해당 규칙이 전달되는지
- 수정·검사에 필요한 권한과 차단 규칙이 의도대로 동작하는지
- 선택형 질문 도구가 현재 호스트와 모드에서 실제로 제공되는지

`trajectory.jsonl`은 주입기 실행 흔적입니다. 수동 호출이나 화면용 조회로도 생길 수 있으므로
그 파일 하나만으로 호스트의 자동 이벤트를 검증했다고 판단하지 않습니다.
질문 도구가 제공되지 않거나 거부되면 그 결과를 그대로 기록합니다.

프로젝트의 `.wiki`에는 이후 실제 결정·분석 기록이 생길 수 있습니다.
팀 공유할 설정과 개인 기록을 구분해 해당 프로젝트의 Git 제외 설정을 정하세요.
