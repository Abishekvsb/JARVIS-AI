"""System Controls, Telemetry, and Screenshot Capture for JARVIS.

Controls volume, captures screenshots to D:\JARVIS\screenshots,
queries battery/CPU/RAM status, and launches Windows Settings.
"""

from __future__ import annotations

import ctypes
import datetime
import logging
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import psutil
from PIL import Image

from jarvis.automation.safety import EmergencyStopManager
from jarvis.config import JARVIS_ROOT

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = JARVIS_ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Windows Virtual Key Codes for Audio
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

# Windows Settings Page URI Mapping
SETTINGS_PAGES = {
    "": "ms-settings:",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "bluetooth": "ms-settings:bluetooth",
    "network": "ms-settings:network",
    "wifi": "ms-settings:network-wifi",
    "battery": "ms-settings:batterysaver",
    "power": "ms-settings:powersleep",
    "apps": "ms-settings:appsfeatures",
    "update": "ms-settings:windowsupdate",
    "privacy": "ms-settings:privacy",
    "storage": "ms-settings:storagesense",
}


def _send_vk(vk_code: int) -> None:
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def change_volume(action: str, steps: int = 5) -> Tuple[bool, str]:
    """Adjust system volume (up, down, mute)."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    act = action.strip().lower()
    clamped_steps = max(1, min(steps, 25))

    if act in ("up", "increase", "higher"):
        for _ in range(clamped_steps):
            _send_vk(VK_VOLUME_UP)
        return True, f"Increased volume by {clamped_steps * 2}%."
    elif act in ("down", "decrease", "lower"):
        for _ in range(clamped_steps):
            _send_vk(VK_VOLUME_DOWN)
        return True, f"Decreased volume by {clamped_steps * 2}%."
    elif act in ("mute", "unmute", "toggle"):
        _send_vk(VK_VOLUME_MUTE)
        return True, "Toggled volume mute."
    else:
        return False, f"Unknown volume action: '{action}'. Available: up, down, mute."


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def _gdi_screenshot(output_path: Path) -> Tuple[int, int]:
    """Capture Windows desktop screen directly using GDI BitBlt."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)

    hdc = user32.GetDC(0)
    cdc = gdi32.CreateCompatibleDC(hdc)
    hbmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(cdc, hbmp)
    SRCCOPY = 0x00CC0020
    gdi32.BitBlt(cdc, 0, 0, w, h, hdc, 0, 0, SRCCOPY)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down DIB
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(cdc, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    img = img.convert("RGB")
    img.save(str(output_path), "PNG")

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(cdc)
    user32.ReleaseDC(0, hdc)

    return w, h


def capture_screenshot(prefix: str = "jarvis_screenshot") -> Tuple[bool, str, Optional[Path]]:
    """Capture full desktop screenshot and save to D:\JARVIS\screenshots.

    Returns (success, message, file_path).
    """
    EmergencyStopManager.get_instance().assert_can_proceed()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_prefix = "".join(c for c in prefix if c.isalnum() or c in ("-", "_")) or "screenshot"
    filename = f"{clean_prefix}_{timestamp}.png"
    save_path = SCREENSHOTS_DIR / filename

    try:
        w, h = _gdi_screenshot(save_path)
        msg = f"Screenshot saved successfully: {save_path} (Resolution: {w}x{h})."
        return True, msg, save_path
    except Exception as e:
        logger.error(f"GDI screenshot failed: {e}")
        return False, f"Failed to capture screenshot: {e}", None


def get_system_telemetry() -> Dict[str, Any]:
    """Retrieve current system telemetry (battery, CPU, RAM, disk)."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    cpu_usage = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()

    battery_info = "Not present (Desktop PC)"
    battery = psutil.sensors_battery()
    if battery:
        plugged_str = "Plugged in (Charging)" if battery.power_plugged else "Running on Battery"
        battery_info = f"{battery.percent}% - {plugged_str}"

    disk_c = psutil.disk_usage("C:")
    disk_d = psutil.disk_usage("D:") if os.path.exists("D:") else None

    return {
        "cpu_percent": f"{cpu_usage}%",
        "memory_used_gb": f"{(mem.total - mem.available) / (1024**3):.1f} GB",
        "memory_total_gb": f"{mem.total / (1024**3):.1f} GB",
        "memory_percent": f"{mem.percent}%",
        "battery": battery_info,
        "disk_c_free_gb": f"{disk_c.free / (1024**3):.1f} GB",
        "disk_d_free_gb": f"{disk_d.free / (1024**3):.1f} GB" if disk_d else "N/A",
    }


def open_settings_page(page_name: str = "") -> Tuple[bool, str]:
    """Launch a Windows Settings page by name."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    p_clean = page_name.strip().lower()
    target_uri = SETTINGS_PAGES.get(p_clean, f"ms-settings:{p_clean}")

    try:
        os.startfile(target_uri)
        return True, f"Opened Windows Settings ({page_name or 'Home'})."
    except Exception as e:
        return False, f"Could not open Windows Settings page '{page_name}': {e}"
