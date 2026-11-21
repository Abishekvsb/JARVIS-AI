"""Ollama Daemon Lifecycle and Model Manager for JARVIS.

Ensures:
1. Model files reside strictly on Drive D: (D:\JARVIS\.cache\ollama).
2. Ollama runtime starts and shuts down cleanly.
3. Models can be pulled and verified safely.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import httpx

from jarvis.config import CACHE_DIR, JARVIS_ROOT

logger = logging.getLogger(__name__)

OLLAMA_INSTALL_DIR = JARVIS_ROOT / "ollama"
OLLAMA_EXE = OLLAMA_INSTALL_DIR / "ollama.exe"
OLLAMA_MODELS_DIR = CACHE_DIR / "ollama"
OLLAMA_ZIP_URL = "https://github.com/ollama/ollama/releases/download/v0.40.16/ollama-windows-amd64.zip"


def find_ollama_executable() -> Optional[Path]:
    """Find ollama executable, preferring D:\\JARVIS\\ollama\\ollama.exe."""
    if OLLAMA_EXE.exists() and OLLAMA_EXE.is_file():
        return OLLAMA_EXE

    path_which = shutil.which("ollama")
    if path_which:
        return Path(path_which)

    # Standard Windows install locations
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        standard_path = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if standard_path.exists():
            return standard_path

    return None


def is_ollama_listening(host: str = "127.0.0.1", port: int = 11434) -> bool:
    """Check if TCP port 11434 is listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def ensure_ollama_installed() -> Path:
    """Ensure Ollama runtime binary exists on Drive D:.

    Downloads portable ollama-windows-amd64.zip directly to D:\\JARVIS\\.cache\\temp
    and extracts to D:\\JARVIS\\ollama if not present.
    """
    found = find_ollama_executable()
    if found:
        return found

    print(f"\n[JARVIS] Ollama binary not found. Downloading portable Ollama to {OLLAMA_INSTALL_DIR} ...")
    OLLAMA_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    temp_zip = CACHE_DIR / "temp" / "ollama_windows.zip"
    temp_zip.parent.mkdir(parents=True, exist_ok=True)

    # Stream download directly to D:
    print(f"[JARVIS] Downloading: {OLLAMA_ZIP_URL} ...")
    urllib.request.urlretrieve(OLLAMA_ZIP_URL, temp_zip)

    print(f"[JARVIS] Extracting Ollama runtime to {OLLAMA_INSTALL_DIR} ...")
    with zipfile.ZipFile(temp_zip, "r") as zf:
        zf.extractall(OLLAMA_INSTALL_DIR)

    # Clean up temp zip
    if temp_zip.exists():
        temp_zip.unlink()

    exe = find_ollama_executable()
    if not exe:
        raise FileNotFoundError(f"Failed to find ollama.exe in {OLLAMA_INSTALL_DIR} after extraction.")

    print(f"[JARVIS] Ollama runtime successfully installed: {exe}")
    return exe


def start_ollama_service(
    host: str = "127.0.0.1",
    port: int = 11434,
    timeout: float = 15.0,
) -> bool:
    """Start the local Ollama daemon pointing model storage to D:\\JARVIS\\.cache\\ollama."""
    if is_ollama_listening(host, port):
        logger.info(f"Ollama daemon is already listening on {host}:{port}.")
        return True

    exe = ensure_ollama_installed()
    OLLAMA_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["OLLAMA_MODELS"] = str(OLLAMA_MODELS_DIR)
    env["OLLAMA_HOST"] = f"{host}:{port}"
    env["TEMP"] = str(CACHE_DIR / "temp")
    env["TMP"] = str(CACHE_DIR / "temp")

    print(f"[JARVIS] Launching Ollama daemon on {host}:{port} with models in {OLLAMA_MODELS_DIR} ...")

    # Launch detached background daemon process
    log_dir = JARVIS_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ollama.log"
    log_fp = open(log_file, "a", encoding="utf-8")

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        [str(exe), "serve"],
        env=env,
        creationflags=creationflags,
        stdout=log_fp,
        stderr=log_fp,
        close_fds=False if os.name == "nt" else True,
    )

    # Wait for daemon to respond
    start = time.time()
    while time.time() - start < timeout:
        if is_ollama_listening(host, port):
            print(f"[JARVIS] Ollama daemon is online and responsive on {host}:{port}.")
            return True
        time.sleep(0.5)

    return is_ollama_listening(host, port)


def pull_model_if_missing(
    model_name: str = "qwen2.5:1.5b",
    base_url: str = "http://127.0.0.1:11434",
) -> Tuple[bool, str]:
    """Pull the specified Ollama model if not already installed."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                installed_models = [m.get("name", "") for m in resp.json().get("models", [])]
                model_base = model_name.split(":")[0]
                if any(model_name in m or (model_base in m and "latest" in m) for m in installed_models):
                    return True, f"Model '{model_name}' is already installed locally."

        # Pull model
        print(f"[JARVIS] Pulling model '{model_name}' into {OLLAMA_MODELS_DIR} (This may take 1-3 minutes) ...")
        with httpx.Client(timeout=600.0) as client:
            resp = client.post(
                f"{base_url}/api/pull",
                json={"name": model_name, "stream": False},
            )
            if resp.status_code == 200:
                return True, f"Model '{model_name}' successfully downloaded into {OLLAMA_MODELS_DIR}."
            else:
                return False, f"Failed to pull model: HTTP {resp.status_code} - {resp.text}"

    except Exception as e:
        return False, f"Error pulling model '{model_name}': {e}"

