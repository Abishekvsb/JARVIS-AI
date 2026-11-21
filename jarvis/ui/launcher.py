"""Launcher for the JARVIS Futuristic Desktop UI.

Starts the FastAPI server and launches Microsoft Edge or Chrome in standalone
'--app' mode to present a modern, borderless floating desktop HUD window.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn

from jarvis.config import JARVIS_ROOT
from jarvis.ui.auth import MobileAuthManager, get_local_network_ip
from jarvis.ui.server import create_ui_app

logger = logging.getLogger("jarvis.ui.launcher")

EDGE_PATHS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")) / r"Microsoft\Edge\Application\msedge.exe",
]

CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")) / r"Google\Chrome\Application\chrome.exe",
]


def find_free_port(start_port: int = 8000) -> int:
    """Find an available TCP port starting from start_port."""
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def find_browser_executable() -> Optional[Path]:
    """Find Microsoft Edge or Chrome on the Windows system."""
    for p in EDGE_PATHS:
        if p.exists() and p.is_file():
            return p
    for p in CHROME_PATHS:
        if p.exists() and p.is_file():
            return p
    return None


def run_server(host: str, port: int) -> None:
    """Run uvicorn server in a blocking call."""
    app = create_ui_app()
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


def launch_desktop_ui(
    host: str = "0.0.0.0",
    port: int = 8000,
    open_window: bool = True,
    block: bool = True,
) -> int:
    """Launch the JARVIS Futuristic Desktop UI & Mobile Access Engine.

    Returns the port number used.
    """
    actual_port = find_free_port(port)
    local_ip = get_local_network_ip()
    local_url = f"http://127.0.0.1:{actual_port}"
    mobile_url = f"http://{local_ip}:{actual_port}"
    auth_mgr = MobileAuthManager.get_instance()

    print("\n" + "=" * 68)
    print("  JARVIS FUTURISTIC HUD & MOBILE ACCESS ONLINE")
    print("=" * 68)
    print(f"  Desktop Interface : {local_url}")
    print(f"  Mobile Wi-Fi URL  : {mobile_url}")
    print(f"  Mobile Access PIN : {auth_mgr.pairing_pin}")
    print("=" * 68 + "\n")

    # Start FastAPI server in background thread
    server_thread = threading.Thread(
        target=run_server,
        args=(host, actual_port),
        daemon=True,
    )
    server_thread.start()

    # Wait for server to become responsive
    max_wait = 5.0
    start_time = time.time()
    server_up = False
    check_host = "127.0.0.1" if host == "0.0.0.0" else host
    while time.time() - start_time < max_wait:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((check_host, actual_port)) == 0:
                server_up = True
                break
        time.sleep(0.1)

    if not server_up:
        print(f"[JARVIS] Warning: Server on {local_url} took longer than expected to start.")

    browser_proc = None
    if open_window:
        browser_exe = find_browser_executable()
        if browser_exe:
            print(f"[JARVIS] Launching HUD Window via {browser_exe.name} App Mode...")
            hud_cache = JARVIS_ROOT / ".cache" / "hud_profile"
            hud_cache.mkdir(parents=True, exist_ok=True)
            # Edge / Chrome App Mode parameters
            app_args = [
                str(browser_exe),
                f"--app={local_url}",
                "--window-size=1260,820",
                "--window-position=120,60",
                f"--user-data-dir={hud_cache}",
            ]
            try:
                browser_proc = subprocess.Popen(app_args)
            except Exception as e:
                print(f"[JARVIS] App mode launch failed: {e}. Opening in default browser...")
                webbrowser.open(local_url)
        else:
            print("[JARVIS] Opening HUD in default browser...")
            webbrowser.open(local_url)

    print(f"[JARVIS] Desktop HUD Active: {local_url}")
    print(f"[JARVIS] Mobile Access Link : {mobile_url} (PIN: {auth_mgr.pairing_pin})")
    print("[JARVIS] Press Ctrl+C in this console to shut down the HUD.")

    if block:
        try:
            if browser_proc:
                browser_proc.wait()
            else:
                while True:
                    time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[JARVIS] Shutting down HUD Server. Goodbye, Sir.")
            if browser_proc and browser_proc.poll() is None:
                browser_proc.terminate()

    return actual_port


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS Futuristic Desktop UI & Mobile Access")
    parser.add_argument("--host", default="0.0.0.0", help="Host address (0.0.0.0 allows Wi-Fi mobile access)")
    parser.add_argument("--port", type=int, default=8000, help="Base TCP port")
    parser.add_argument("--no-browser", action="store_true", help="Start server only without launching browser")
    args = parser.parse_args()

    launch_desktop_ui(
        host=args.host,
        port=args.port,
        open_window=not args.no_browser,
        block=True,
    )


if __name__ == "__main__":
    main()

