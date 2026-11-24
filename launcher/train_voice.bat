@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo [1/3] Freeing the GPU (stopping the chat model)...
ollama stop qwen3.5:2b >nul 2>&1
echo [2/3] Generating bilingual training clips (about 5 minutes)...
"Open-LLM-VTuber\.venv\Scripts\python.exe" "assets\voice\bilingual\make_data.py"
if errorlevel 1 goto fail
echo [3/3] Training the voice (30-60 minutes). Keep this window open.
cd GPT-SoVITS-v5-20261006nvidia50x0
set "PATH=%CD%\runtime;%PATH%"
runtime\python.exe -I train_xiaoke.py
if errorlevel 1 goto fail
echo.
echo ===== Training finished. Tell Claude it is done. =====
pause
exit /b 0
:fail
echo.
echo ===== Something failed. Send Claude the last lines above. =====
pause
exit /b 1
