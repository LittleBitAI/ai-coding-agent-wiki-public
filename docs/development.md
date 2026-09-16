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
채팅 설치 명령도 지도 파일을 새로 생성합니다.

자동 검사는 임시 프로젝트를 사용합니다. 실제 사용자의 대화 기록은 테스트 입력이 아닙니다.
설정 병합·재설치·한글 및 공백 경로·동명 checkout의 설정 분리를 확인합니다.
실제 OAuth 로그인 성공, 호스트 자동 이벤트, 답변 품질 검수는 이 검사 결과에 포함되지 않습니다.

hooks 구현을 바꿨다면 [호스트 확인 절차](hooks-setup.md)도 따릅니다.
공개 전에는 [공개본 갱신 절차](publishing.md)로 파일과 Git 이력을 검사합니다.
