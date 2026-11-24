@echo off
chcp 65001 >nul
cd /d "%~dp0..\GPT-SoVITS-v5-20261006nvidia50x0"
set "PATH=%CD%\runtime;%PATH%"
echo Making comparison clips (a few minutes)...
runtime\python.exe -I voice_compare.py
start "" "%~dp0..\assets\voice\compare"
pause
