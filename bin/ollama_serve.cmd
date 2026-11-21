@echo off
setlocal
set "JARVIS_ROOT=D:\JARVIS"
set "OLLAMA_MODELS=%JARVIS_ROOT%\.cache\ollama"
set "OLLAMA_HOST=127.0.0.1:11434"
set "TEMP=%JARVIS_ROOT%\.cache\temp"
set "TMP=%JARVIS_ROOT%\.cache\temp"

echo [JARVIS] Starting Ollama Daemon...
echo [JARVIS] Model directory: %OLLAMA_MODELS%
echo [JARVIS] Host: %OLLAMA_HOST%
"%JARVIS_ROOT%\ollama\ollama.exe" serve

