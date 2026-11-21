"""Ollama Installer for JARVIS on Drive D:.

Downloads and installs Ollama strictly to D:\JARVIS\ollama,
ensuring temporary files and model layers stay on Drive D:.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
import psutil

JARVIS_ROOT = Path("D:/JARVIS").resolve()
OLLAMA_DIR = JARVIS_ROOT / "ollama"
CACHE_DIR = JARVIS_ROOT / ".cache"
TEMP_DIR = CACHE_DIR / "temp"
MODELS_DIR = CACHE_DIR / "ollama"

def check_disk_space():
    d_usage = psutil.disk_usage("D:\\")
    free_gb = d_usage.free / (1024**3)
    print(f"[JARVIS] Available space on Drive D: {free_gb:.2f} GB")
    if free_gb < 5.0:
        raise RuntimeError(f"Insufficient disk space on Drive D: ({free_gb:.2f} GB available, 5.0 GB required).")
    return free_gb

def install_ollama():
    check_disk_space()

    # Check if already installed
    existing_exe = OLLAMA_DIR / "ollama.exe"
    if existing_exe.exists():
        print(f"[JARVIS] Ollama binary already present at: {existing_exe}")
        return str(existing_exe)

    OLLAMA_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[JARVIS] Installing Ollama to {OLLAMA_DIR} ...")

    # Configure environment to strictly use D: drive
    env = os.environ.copy()
    env["TEMP"] = str(TEMP_DIR)
    env["TMP"] = str(TEMP_DIR)
    env["OLLAMA_INSTALL_DIR"] = str(OLLAMA_DIR)
    env["OLLAMA_MODELS"] = str(MODELS_DIR)

    ps_script = f"""
    $env:TEMP = '{TEMP_DIR}'
    $env:TMP = '{TEMP_DIR}'
    $env:OLLAMA_INSTALL_DIR = '{OLLAMA_DIR}'
    $env:OLLAMA_MODELS = '{MODELS_DIR}'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Write-Host "[JARVIS] Downloading Ollama installer via install.ps1..."
    irm https://ollama.com/install.ps1 | iex
    """

    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)

    print("STDOUT:", proc.stdout)
    if proc.stderr:
        print("STDERR:", proc.stderr)

    if existing_exe.exists():
        print(f"[JARVIS] Installation successful: {existing_exe}")
        return str(existing_exe)

    # Check if installer put it in LocalAppData
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        standard_path = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if standard_path.exists():
            print(f"[JARVIS] Ollama installed at: {standard_path}")
            return str(standard_path)

    raise RuntimeError(f"Ollama installation did not produce ollama.exe. Return code: {proc.returncode}")

if __name__ == "__main__":
    exe_path = install_ollama()
    print("Ollama Exe Path:", exe_path)
    res = subprocess.run([exe_path, "--version"], capture_output=True, text=True)
    print("Ollama Version:", res.stdout.strip() or res.stderr.strip())

