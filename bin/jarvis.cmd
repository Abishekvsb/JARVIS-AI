@echo off
setlocal
set "JARVIS_ROOT=D:\JARVIS"
set "OPENJARVIS_HOME=%JARVIS_ROOT%"
set "UV_CACHE_DIR=%JARVIS_ROOT%\.cache\uv"
set "PIP_CACHE_DIR=%JARVIS_ROOT%\.cache\pip"
set "TEMP=%JARVIS_ROOT%\.cache\temp"
set "TMP=%JARVIS_ROOT%\.cache\temp"
set "HF_HOME=%JARVIS_ROOT%\.cache\huggingface"
set "OLLAMA_MODELS=%JARVIS_ROOT%\.cache\ollama"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

if "%~1"=="" (
    "%JARVIS_ROOT%\.venv\Scripts\python.exe" -m jarvis.cli_chat
    goto :eof
)

if "%~1"=="chat" (
    "%JARVIS_ROOT%\.venv\Scripts\python.exe" -m jarvis.cli_chat
    goto :eof
)

if "%~1"=="voice" (
    "%JARVIS_ROOT%\.venv\Scripts\python.exe" -m jarvis.voice.voice_cli
    goto :eof
)

if "%~1"=="ui" (
    "%JARVIS_ROOT%\.venv\Scripts\python.exe" -m jarvis.ui.launcher
    goto :eof
)

"%JARVIS_ROOT%\.venv\Scripts\python.exe" -m openjarvis.cli %*
