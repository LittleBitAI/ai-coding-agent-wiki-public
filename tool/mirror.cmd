@echo off
rem mirror - open the Korean mirror.
rem
rem ASCII only, on purpose. cmd.exe reads this file as CP949 and one non-ASCII
rem character has killed a hook in this repo before.
rem
rem The mirror is a tab of the wiki app, not a server of its own. So this walks
rem the same path chat.cmd does and lands on that tab. If the app is already
rem running it just opens the tab instead of fighting for the port.
rem
rem   mirror.cmd                -> http://127.0.0.1:8787/#mirror
rem   mirror.cmd --port 9090
rem
rem Which repository it watches is chosen in the page, not here.

setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Run: python "%~dp0setup_chat.py" install --agent codex
  echo Or use --agent claude / --agent both. See docs\chat-setup.md.
  goto :halt
)

if not exist "%~dp0..\web\dist\index.html" (
  echo Run the setup command again to build the page.
  goto :halt
)

"%PY%" "%~dp0chat.py" --open "#mirror" %*
if errorlevel 1 goto :halt
exit /b 0

:halt
echo.
echo ^(stopped. press any key to close this window^)
pause >nul
exit /b 1
