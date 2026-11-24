"""Keyboard Automation and Dictation Controller for JARVIS.

Handles safe text typing, Unicode/Tamil clipboard pasting, keyboard shortcuts,
and the specialized 'Open Notepad and Write' dictation workflow.
"""

from __future__ import annotations

import logging
import time
from typing import List, Tuple

try:
    import pyautogui
    # Disable PyAutoGUI corner fail-safe in automation backend to prevent false aborts
    # when session mouse position rests at (0, 0).
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.05
except Exception as e:
    pyautogui = None

try:
    import pygetwindow as gw
except Exception:
    gw = None

try:
    import pyperclip
except Exception:
    pyperclip = None

from jarvis.automation.app_controller import open_application
from jarvis.automation.safety import EmergencyStopManager

logger = logging.getLogger(__name__)

ALLOWED_SHORTCUTS = {
    ("ctrl", "c"),
    ("ctrl", "v"),
    ("ctrl", "a"),
    ("ctrl", "z"),
    ("ctrl", "y"),
    ("ctrl", "s"),
    ("ctrl", "f"),
    ("alt", "tab"),
    ("enter",),
    ("esc",),
    ("escape",),
    ("tab",),
    ("backspace",),
    ("space",),
}


def type_text(text: str, press_enter: bool = False) -> Tuple[bool, str]:
    """Type text into the currently active window safely.

    Uses clipboard paste for Unicode (e.g. Tamil) to ensure correct character representation.
    """
    EmergencyStopManager.get_instance().assert_can_proceed()

    if pyautogui is None:
        return False, "Desktop keyboard automation is not supported in this headless/cloud environment."

    if not text:
        return False, "Text to type cannot be empty."

    # If text contains non-ASCII characters (e.g. Tamil), use clipboard paste
    has_unicode = any(ord(c) > 127 for c in text)
    try:
        if has_unicode:
            old_clip = pyperclip.paste()
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            # Restore previous clipboard after a brief delay
            try:
                pyperclip.copy(old_clip)
            except Exception:
                pass
        else:
            pyautogui.write(text, interval=0.01)

        if press_enter:
            pyautogui.press("enter")

        preview = text[:40] + ("..." if len(text) > 40 else "")
        return True, f"Typed text: '{preview}' into active window."
    except Exception as e:
        return False, f"Failed to type text: {e}"


def send_safe_hotkey(keys: List[str]) -> Tuple[bool, str]:
    """Send an allowlisted keyboard shortcut."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    if pyautogui is None:
        return False, "Desktop keyboard shortcuts not supported in this headless/cloud environment."

    clean_keys = tuple(k.strip().lower() for k in keys)
    if clean_keys not in ALLOWED_SHORTCUTS:
        return False, f"Shortcut {clean_keys} is not in the approved safe shortcuts list."

    try:
        pyautogui.hotkey(*clean_keys)
        return True, f"Executed shortcut: {' + '.join(clean_keys)}."
    except Exception as e:
        return False, f"Failed to execute shortcut: {e}"


def write_in_notepad(content: str) -> Tuple[bool, str]:
    """Open Notepad and write the dictated content into it."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    # 1. Launch Notepad
    success, msg = open_application("notepad")
    if not success:
        return False, msg

    # Wait for Notepad window to render and take focus
    time.sleep(1.0)

    # 2. Type or paste the content
    type_success, type_msg = type_text(content, press_enter=True)
    if not type_success:
        return False, type_msg

    preview = content[:50] + ("..." if len(content) > 50 else "")
    return True, f"Opened Notepad and wrote: '{preview}'."

