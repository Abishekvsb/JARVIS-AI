"""Central Allowlisted Action Dispatcher for JARVIS Desktop Automation.

Executes only verified tools, enforces emergency stop, checks permissions,
and writes audit log entries for every action.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from jarvis.automation.app_controller import close_application, open_application, send_whatsapp_message
from jarvis.automation.browser_controller import control_media, open_url, search_google, search_youtube
from jarvis.automation.file_search import find_files, open_file_safely
from jarvis.automation.keyboard_controller import send_safe_hotkey, type_text, write_in_notepad
from jarvis.automation.safety import AuditLogger, EmergencyStopManager, PermissionGuard
from jarvis.automation.system_controller import capture_screenshot, change_volume, get_system_telemetry, open_settings_page

logger = logging.getLogger(__name__)


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an allowlisted automation tool with strict security checks."""
    t0 = time.time()
    guard = PermissionGuard()

    # Special case: emergency stop can always be called even if stopped
    if tool_name == "emergency_stop":
        reason = tool_input.get("reason", "User requested emergency stop")
        EmergencyStopManager.get_instance().trigger_stop(reason)
        msg = f"EMERGENCY STOP ACTIVATED: {reason}. All automation halted."
        AuditLogger.log_action(tool_name, tool_input, success=True, message=msg, duration_ms=(time.time() - t0) * 1000)
        return {"success": True, "message": msg}

    try:
        # 1. Assert system is not stopped and action is permitted
        guard.verify_action(tool_name, tool_input)

        # 2. Allowlisted Dispatcher
        if tool_name == "open_app":
            success, msg = open_application(tool_input.get("app_name", ""))
            res = {"success": success, "message": msg}

        elif tool_name == "close_app":
            success, msg = close_application(tool_input.get("app_name", ""))
            res = {"success": success, "message": msg}

        elif tool_name == "open_browser":
            success, msg = open_url(tool_input.get("url", "https://google.com"))
            res = {"success": success, "message": msg}

        elif tool_name == "search_web":
            platform = tool_input.get("platform", "google").lower()
            query = tool_input.get("query", "")
            if platform == "youtube":
                success, msg = search_youtube(query)
            else:
                success, msg = search_google(query)
            res = {"success": success, "message": msg}

        elif tool_name == "control_media":
            success, msg = control_media(tool_input.get("action", "play_pause"))
            res = {"success": success, "message": msg}

        elif tool_name == "search_files":
            success, msg, files = find_files(
                query=tool_input.get("query", ""),
                category=tool_input.get("category", "all"),
            )
            res = {"success": success, "message": msg, "files": files}

        elif tool_name == "open_file":
            success, msg = open_file_safely(tool_input.get("file_path", ""))
            res = {"success": success, "message": msg}

        elif tool_name == "take_screenshot":
            success, msg, path = capture_screenshot(prefix=tool_input.get("prefix", "jarvis"))
            res = {"success": success, "message": msg, "file_path": str(path) if path else ""}

        elif tool_name == "adjust_volume":
            success, msg = change_volume(
                action=tool_input.get("action", "up"),
                steps=tool_input.get("steps", 5),
            )
            res = {"success": success, "message": msg}

        elif tool_name == "get_system_info":
            telemetry = get_system_telemetry()
            res = {"success": True, "message": "Telemetry gathered.", "telemetry": telemetry}

        elif tool_name == "open_settings":
            success, msg = open_settings_page(tool_input.get("page", ""))
            res = {"success": success, "message": msg}

        elif tool_name == "type_text":
            success, msg = type_text(
                text=tool_input.get("text", ""),
                press_enter=tool_input.get("press_enter", False),
            )
            res = {"success": success, "message": msg}

        elif tool_name == "write_in_notepad":
            success, msg = write_in_notepad(content=tool_input.get("content", ""))
            res = {"success": success, "message": msg}

        elif tool_name == "send_whatsapp_message":
            success, msg = send_whatsapp_message(
                recipient=tool_input.get("recipient", ""),
                message=tool_input.get("message", ""),
            )
            res = {"success": success, "message": msg}

        else:
            res = {"success": False, "message": f"Tool '{tool_name}' is not in the approved allowlist."}

    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}")
        res = {"success": False, "message": f"Execution error: {e}"}

    duration = (time.time() - t0) * 1000
    AuditLogger.log_action(
        tool_name,
        tool_input,
        success=res.get("success", False),
        message=res.get("message", ""),
        duration_ms=duration,
    )
    return res

