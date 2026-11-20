$JarvisRoot = "D:\JARVIS"
$env:OPENJARVIS_HOME = $JarvisRoot
$env:UV_CACHE_DIR = "$JarvisRoot\.cache\uv"
$env:PIP_CACHE_DIR = "$JarvisRoot\.cache\pip"
$env:TEMP = "$JarvisRoot\.cache\temp"
$env:TMP = "$JarvisRoot\.cache\temp"
$env:HF_HOME = "$JarvisRoot\.cache\huggingface"
$env:OLLAMA_MODELS = "$JarvisRoot\.cache\ollama"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

if ($args.Count -eq 0 -or $args[0] -eq "chat") {
    & "$JarvisRoot\.venv\Scripts\python.exe" -m jarvis.cli_chat
} elseif ($args[0] -eq "voice") {
    & "$JarvisRoot\.venv\Scripts\python.exe" -m jarvis.voice.voice_cli
} elseif ($args[0] -eq "ui") {
    & "$JarvisRoot\.venv\Scripts\python.exe" -m jarvis.ui.launcher
} else {
    & "$JarvisRoot\.venv\Scripts\python.exe" -m openjarvis.cli $args
}
