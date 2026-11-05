@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -Action first-run %*
set "setup_exit=%errorlevel%"
if not defined COURSE_SETUP_NO_PAUSE pause
exit /b %setup_exit%
