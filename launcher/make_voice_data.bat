@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo Generating bilingual voice training data (about 5 minutes)...
"Open-LLM-VTuber\.venv\Scripts\python.exe" "assets\voice\bilingual\make_data.py"
echo.
pause
