@echo off
rem chat - start the local ask-the-wiki server.
rem
rem ASCII only, on purpose. cmd.exe reads this file as CP949 and one non-ASCII
rem character has killed a hook in this repo before.
rem
rem The window is kept open on any failure. Double-clicking a .cmd closes the
rem window the instant the script ends, so a one-line error (a taken port, a
rem failed build) looks like "it just closed by itself". It did that once.
rem
rem   chat.cmd                 -> http://127.0.0.1:8787
rem   chat.cmd --port 9090

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

"%PY%" "%~dp0chat.py" %*
if errorlevel 1 goto :halt
exit /b 0

:halt
echo.
echo ^(stopped. press any key to close this window^)
pause >nul
exit /b 1
