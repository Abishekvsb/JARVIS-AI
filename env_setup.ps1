# D:\JARVIS\env_setup.ps1
# Sets up the environment variables for JARVIS to ensure zero spillover to Drive C:

$JarvisRoot = "D:\JARVIS"
$env:OPENJARVIS_HOME = $JarvisRoot
$env:UV_CACHE_DIR = "$JarvisRoot\.cache\uv"
$env:PIP_CACHE_DIR = "$JarvisRoot\.cache\pip"
$env:TEMP = "$JarvisRoot\.cache\temp"
$env:TMP = "$JarvisRoot\.cache\temp"
$env:HF_HOME = "$JarvisRoot\.cache\huggingface"
$env:OLLAMA_MODELS = "$JarvisRoot\.cache\ollama"

# Prepend the virtual environment Scripts directory to PATH for the current session
$VenvScripts = "$JarvisRoot\.venv\Scripts"
if ($env:PATH -notlike "*$VenvScripts*") {
    $env:PATH = "$VenvScripts;$JarvisRoot\bin;$env:PATH"
}

Write-Host "JARVIS environment initialized on D: drive." -ForegroundColor Cyan
Write-Host "Python: $VenvScripts\python.exe" -ForegroundColor Green
Write-Host "Caches & Models directed to: $JarvisRoot\.cache" -ForegroundColor Green
