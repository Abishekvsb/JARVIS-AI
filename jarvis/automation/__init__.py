"""JARVIS Windows Desktop Automation Subsystem.

Provides allowlisted application launching, browser controls, file searching,
screenshot capture, audio controls, keyboard dictation, and emergency stop.
"""

from jarvis.automation.agent import AutomationAgent
from jarvis.automation.app_controller import close_application, open_application
from jarvis.automation.browser_controller import control_media, open_url, search_google, search_youtube
from jarvis.automation.executor import execute_tool
from jarvis.automation.file_search import find_files, open_file_safely
from jarvis.automation.keyboard_controller import send_safe_hotkey, type_text, write_in_notepad
from jarvis.automation.safety import (
    AuditLogger,
    EmergencyStopException,
    EmergencyStopManager,
    PermissionDeniedException,
    PermissionGuard,
)
from jarvis.automation.system_controller import (
    capture_screenshot,
    change_volume,
    get_system_telemetry,
    open_settings_page,
)
from jarvis.automation.tools_schema import AUTOMATION_TOOLS

__all__ = [
    "AUTOMATION_TOOLS",
    "AuditLogger",
    "AutomationAgent",
    "EmergencyStopException",
    "EmergencyStopManager",
    "PermissionDeniedException",
    "PermissionGuard",
    "capture_screenshot",
    "change_volume",
    "close_application",
    "control_media",
    "execute_tool",
    "find_files",
    "get_system_telemetry",
    "open_application",
    "open_file_safely",
    "open_settings_page",
    "open_url",
    "search_google",
    "search_youtube",
    "send_safe_hotkey",
    "type_text",
    "write_in_notepad",
]

