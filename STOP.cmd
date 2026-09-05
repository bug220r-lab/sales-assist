@echo off
rem SYNTHETIC-SALES-ASSIST-AUTHORED-M8
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo.ps1" -Action STOP -DevelopmentRuntime %*
set "SSA_RESULT=%ERRORLEVEL%"
if not "%SSA_NONINTERACTIVE%"=="1" pause
exit /b %SSA_RESULT%
