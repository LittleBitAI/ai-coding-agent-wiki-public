@echo off
rem slack_post - run a scheduled Claude Code brief and post it to Slack.
rem
rem This file stays pure ASCII on purpose. The Korean lives in prompts\*.md,
rem read as UTF-8. A .cmd with non-ASCII literals is read as CP949 by cmd.exe
rem
rem   slack_post.cmd standup "path-to-project" "channel-id"
rem   slack_post.cmd retro "path-to-project" "channel-id"

setlocal
set "WIKI_ROOT=%~dp0.."
set "SLACK_CHANNEL=%~3"
if "%SLACK_CHANNEL%"=="" (
  echo Usage: slack_post.cmd standup-or-retro "path-to-project" "channel-id" 1>&2
  exit /b 1
)
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set KIND=%~1
if "%KIND%"=="" set KIND=standup

set PROMPT=%~dp0prompts\slack-%KIND%.md
if not exist "%PROMPT%" (
  echo no prompt file: %PROMPT% 1>&2
  exit /b 1
)

set "REPO=%~2"
if "%REPO%"=="" (
  echo Usage: slack_post.cmd standup "path-to-project" 1>&2
  exit /b 1
)
cd /d "%REPO%" || exit /b 1

rem allowedTools is an allowlist, so Edit and Write are absent by design:
rem a scheduled run reports, it does not change files.
type "%PROMPT%" | claude -p ^
  --allowedTools "Bash,Read,Glob,Grep,mcp__claude_ai_Slack__slack_send_message"

exit /b %ERRORLEVEL%
