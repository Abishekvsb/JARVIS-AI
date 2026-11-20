"""Browser and Media Controller for JARVIS.

Handles opening web pages, searching Google and YouTube, and controlling
media playback (play, pause, next) safely.
"""

from __future__ import annotations

import ctypes
import logging
import urllib.parse
import webbrowser
from typing import Tuple

from jarvis.automation.safety import EmergencyStopManager

logger = logging.getLogger(__name__)

# Windows Virtual Key Codes for Media
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3


def _send_virtual_key(vk_code: int) -> None:
    """Send a virtual keyboard event via Windows user32."""
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def open_url(url: str) -> Tuple[bool, str]:
    """Open a validated web URL in the default browser."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    url_clean = url.strip()
    if not url_clean:
        return False, "URL cannot be empty."

    # Prepend https if protocol is missing
    if not (url_clean.startswith("http://") or url_clean.startswith("https://")):
        url_clean = f"https://{url_clean}"

    parsed = urllib.parse.urlparse(url_clean)
    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked unsafe URL protocol: '{parsed.scheme}'. Only http and https are permitted."

    try:
        webbrowser.open(url_clean)
        return True, f"Navigating to {url_clean}."
    except Exception as e:
        return False, f"Failed to open browser: {e}"


def search_google(query: str) -> Tuple[bool, str]:
    """Search Google for the specified query."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    q_clean = query.strip()
    if not q_clean:
        return False, "Search query cannot be empty."

    encoded = urllib.parse.quote_plus(q_clean)
    url = f"https://www.google.com/search?q={encoded}"
    webbrowser.open(url)
    return True, f"Searching Google for: '{q_clean}'."


def search_youtube(query: str = "") -> Tuple[bool, str]:
    """Open YouTube or search for specific videos on YouTube."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    q_clean = query.strip()
    if not q_clean:
        webbrowser.open("https://www.youtube.com")
        return True, "Opening YouTube home page."

    encoded = urllib.parse.quote_plus(q_clean)
    url = f"https://www.youtube.com/results?search_query={encoded}"
    webbrowser.open(url)
    return True, f"Searching YouTube for: '{q_clean}'."


def control_media(action: str) -> Tuple[bool, str]:
    """Control media playback (play_pause, next, prev)."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    act = action.strip().lower()
    if act in ("play", "pause", "play_pause", "toggle"):
        _send_virtual_key(VK_MEDIA_PLAY_PAUSE)
        return True, "Toggled media play/pause."
    elif act in ("next", "next_track"):
        _send_virtual_key(VK_MEDIA_NEXT_TRACK)
        return True, "Skipped to next track."
    elif act in ("prev", "previous", "previous_track"):
        _send_virtual_key(VK_MEDIA_PREV_TRACK)
        return True, "Returned to previous track."
    else:
        return False, f"Unknown media action: '{action}'. Available: play_pause, next, prev."

