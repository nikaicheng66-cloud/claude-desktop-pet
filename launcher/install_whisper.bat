@echo off
chcp 65001 >nul
rem [deskpet] Installs faster-whisper for the desk pet, downloads the Whisper model once,
rem and checks whether it can run on the graphics card.
cd /d "%~dp0..\Open-LLM-VTuber"

echo [1/2] 正在安装 faster-whisper ...
uv pip show faster-whisper >nul 2>&1 && (echo 已经装好了，跳过。) || call uv add faster-whisper
if errorlevel 1 (
  echo.
  echo 安装失败，请把上面的报错发给 Claude。
  pause
  exit /b 1
)

echo.
echo [1b] 正在安装显卡需要的 CUDA 运算库（cuBLAS、cuDNN，约 1GB）...
call uv add "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
if errorlevel 1 (
  echo CUDA 运算库安装失败，请把上面的报错发给 Claude。
)
echo.
echo [2/2] 正在下载 Whisper 模型（约 1.6GB，第一次比较慢）并测试显卡 ...
call uv run python "%~dp0whisper_check.py"

echo.
echo 完成。把上面以 RESULT 开头的那几行告诉 Claude，然后可以关掉这个窗口。
pause
