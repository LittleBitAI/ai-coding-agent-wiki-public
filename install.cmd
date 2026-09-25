@echo off
rem install - prepare this wiki's Python side on a team member's PC.
rem
rem   1. .venv, from Python 3.11 or later (py launcher first, then python)
rem   2. the chat, hook and search packages into that .venv
rem   3. the search model (multilingual-e5-small, about 120 MB) into
rem      %USERPROFILE%\.cache\ai-coding-agent-wiki\models\e5
rem
rem Safe to run again: an existing .venv and a downloaded model are kept.
rem The page build and the CLI sign-in are tool\setup_chat.py's job.
rem
rem ASCII only, on purpose. cmd.exe reads this file as CP949 and one non-ASCII
rem character has killed a hook in this repo before. The window is kept open
rem on failure, as in tool\chat.cmd.

setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if exist "%PY%" goto :version

set "BASE="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && set "BASE=py -3"
if not defined BASE python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && set "BASE=python"
if not defined BASE (
  echo Python 3.11 or later was not found. Install it and open a new terminal.
  goto :halt
)
echo 1/3: creating .venv with %BASE%
%BASE% -m venv .venv
if errorlevel 1 goto :halt

:version
rem An existing .venv is checked too: one made from 3.10 installs fine here
rem and is then refused by setup_chat.py, the step this script points to.
"%PY%" -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
  echo .venv uses Python older than 3.11. Delete the .venv folder and run this again.
  goto :halt
)

echo 2/3: installing packages
"%PY%" -m pip install -r requirements-chat.txt -r requirements-search.txt
if errorlevel 1 goto :halt

echo 3/3: downloading the search model
"%PY%" tool\searchd.py --fetch-model
if errorlevel 1 goto :halt

echo.
echo Done. Next: .venv\Scripts\python tool\setup_chat.py install --agent both
echo (or --agent claude / codex) builds the page and checks the CLI sign-in.
exit /b 0

:halt
echo.
echo ^(stopped. press any key to close this window^)
pause >nul
exit /b 1
