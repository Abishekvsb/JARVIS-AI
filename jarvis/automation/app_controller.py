"""Application Controller for Windows Desktop Automation.

Provides safe application launching by name and graceful process termination
with a protected system process blacklist.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import urllib.parse
import webbrowser
import winreg
from typing import Dict, List, Optional, Tuple

import psutil

from jarvis.automation.safety import EmergencyStopManager

logger = logging.getLogger(__name__)

# System processes that can NEVER be closed by JARVIS
PROTECTED_PROCESSES = {
    "explorer.exe",
    "svchost.exe",
    "csrss.exe",
    "services.exe",
    "lsass.exe",
    "dwm.exe",
    "smss.exe",
    "wininit.exe",
    "winlogon.exe",
    "fontdrvhost.exe",
    "system",
    "registry",
    "idle",
    "antigravity.exe",
}

# Standard Windows App Name to Executable/Protocol Mapping
COMMON_APPS = {
    "notepad": "notepad.exe",
    "note pad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "vscode": "code.cmd",
    "vs code": "code.cmd",
    "whatsapp": "whatsapp:",
    "whats app": "whatsapp:",
    "watsapp": "whatsapp:",
    "whatsapp desktop": "whatsapp:",
    "whatsapp web": "https://web.whatsapp.com",
}


def _find_in_registry_app_paths(app_name: str) -> Optional[str]:
    """Look up the application executable path in the Windows Registry App Paths."""
    for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(
                root_key,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            ) as key:
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    subkey_name = winreg.EnumKey(key, i)
                    if app_name.lower() in subkey_name.lower():
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            val, _ = winreg.QueryValueEx(subkey, "")
                            if val and os.path.exists(val):
                                return val
        except Exception:
            pass
    return None


def open_application(app_name: str) -> Tuple[bool, str]:
    """Launch an application safely by name.

    Returns (success, message).
    """
    EmergencyStopManager.get_instance().assert_can_proceed()

    app_clean = app_name.strip().lower()
    if not app_clean:
        return False, "Application name cannot be empty."

    # 1. Check known mappings
    target = COMMON_APPS.get(app_clean)

    # Special handling for WhatsApp
    if "whatsapp" in app_clean or app_clean in ("whats app", "watsapp"):
        try:
            os.startfile("whatsapp:")
            return True, "Successfully opened WhatsApp Desktop, Sir."
        except Exception:
            try:
                import webbrowser
                webbrowser.open("https://web.whatsapp.com")
                return True, "Opened WhatsApp Web in browser, Sir."
            except Exception as e:
                return False, f"Could not launch WhatsApp: {e}"

    # Handle URLs (e.g. WhatsApp Web)
    if target and (target.startswith("http://") or target.startswith("https://")):
        try:
            import webbrowser
            webbrowser.open(target)
            return True, f"Opened {app_name} in web browser, Sir."
        except Exception as e:
            return False, f"Could not open {app_name}: {e}"

    # 2. Check protocol handler (e.g. ms-settings:, whatsapp:)
    if target and target.endswith(":"):
        try:
            os.startfile(target)
            return True, f"Opened Windows {app_name}."
        except Exception as e:
            return False, f"Could not launch {app_name}: {e}"

    # 3. If target not found in mapping, search App Paths registry
    if not target:
        target = _find_in_registry_app_paths(app_clean)

    # 4. If still not found, try directly with .exe suffix
    if not target:
        target = f"{app_clean}.exe"

    try:
        # Use os.startfile for native Windows shell execution without cmd.exe
        os.startfile(target)
        return True, f"Successfully launched {app_name} ({target})."
    except FileNotFoundError:
        return False, f"Application '{app_name}' was not found on your system."
    except Exception as e:
        return False, f"Failed to open '{app_name}': {e}"


def close_application(app_name: str) -> Tuple[bool, str]:
    """Close an application by name after verifying it is not a protected system process.

    Returns (success, message).
    """
    EmergencyStopManager.get_instance().assert_can_proceed()

    app_clean = app_name.strip().lower()
    target_exe = COMMON_APPS.get(app_clean, app_clean)
    if not target_exe.endswith(".exe"):
        target_exe = f"{target_exe}.exe"

    # Verify protected process blacklist
    if target_exe in PROTECTED_PROCESSES or app_clean in PROTECTED_PROCESSES:
        return False, f"Security Warning: '{app_name}' is a critical system process and cannot be terminated."

    matched_processes = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            p_name = proc.info["name"].lower()
            if p_name == target_exe or app_clean in p_name:
                matched_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not matched_processes:
        return False, f"No running instance of '{app_name}' was found."

    closed_count = 0
    for proc in matched_processes:
        try:
            if proc.name().lower() not in PROTECTED_PROCESSES:
                proc.terminate()
                closed_count += 1
        except Exception as e:
            logger.warning(f"Could not terminate process {proc.pid}: {e}")

    if closed_count > 0:
        return True, f"Successfully closed {closed_count} running instance(s) of '{app_name}'."
    return False, f"Could not terminate '{app_name}' due to system access restrictions."


def send_whatsapp_message(recipient: str, message: str) -> Tuple[bool, str]:
    """Open WhatsApp with a pre-filled or direct message to recipient or phone number."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    clean_msg = message.strip()
    clean_rec = recipient.strip()
    if not clean_msg:
        return False, "Message content cannot be empty."

    encoded_text = urllib.parse.quote(clean_msg)

    # Check if recipient contains a phone number
    digits_only = re.sub(r"[^\d]", "", clean_rec)
    if len(digits_only) >= 10:
        if len(digits_only) == 10:
            digits_only = f"91{digits_only}"

        try:
            os.startfile(f"whatsapp://send?phone={digits_only}&text={encoded_text}")
            return True, f"Opened WhatsApp chat with {clean_rec} and drafted message: '{clean_msg}'."
        except Exception:
            webbrowser.open(f"https://web.whatsapp.com/send?phone={digits_only}&text={encoded_text}")
            return True, f"Opened WhatsApp Web chat with {clean_rec} and drafted message: '{clean_msg}'."
    else:
        # Recipient is a contact name (e.g. Ramesh, Mom)
        try:
            os.startfile(f"whatsapp://send?text={encoded_text}")
            return True, f"Opened WhatsApp with drafted message for {clean_rec}: '{clean_msg}'."
        except Exception:
            webbrowser.open(f"https://web.whatsapp.com/send?text={encoded_text}")
            return True, f"Opened WhatsApp Web with drafted message for {clean_rec}: '{clean_msg}'."

