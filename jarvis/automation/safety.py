"""Safety and Governance Subsystem for JARVIS Windows Automation.

Provides:
- Thread-safe Emergency Stop switch.
- Action permission validation and sensitive operation guardrails.
- Non-credential audit logging.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from jarvis.config import JARVIS_ROOT

logger = logging.getLogger(__name__)

EMERGENCY_STOP_FILE = JARVIS_ROOT / ".emergency_stop"
LOGS_DIR = JARVIS_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG_FILE = LOGS_DIR / "actions.log"


class EmergencyStopException(Exception):
    """Raised when an automation operation is blocked by the Emergency Stop switch."""
    pass


class PermissionDeniedException(Exception):
    """Raised when a sensitive operation does not receive required user confirmation."""
    pass


class EmergencyStopManager:
    """Global kill-switch for all JARVIS automation tasks."""

    _instance: Optional[EmergencyStopManager] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._stopped = False
        self._reason = ""

    @classmethod
    def get_instance(cls) -> EmergencyStopManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_stopped(self) -> bool:
        """Check if emergency stop is currently active."""
        if self._stopped:
            return True
        if EMERGENCY_STOP_FILE.exists():
            self._stopped = True
            self._reason = "Triggered via .emergency_stop sentinel file"
            return True
        return False

    def trigger_stop(self, reason: str = "User initiated emergency stop") -> None:
        """Immediately engage emergency stop."""
        self._stopped = True
        self._reason = reason
        try:
            EMERGENCY_STOP_FILE.write_text(
                f"STOPPED at {datetime.datetime.now().isoformat()} - Reason: {reason}",
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to write emergency stop file: {e}")
        logger.critical(f"EMERGENCY STOP ACTIVATED: {reason}")

    def reset(self) -> None:
        """Reset emergency stop to allow operations to resume."""
        self._stopped = False
        self._reason = ""
        if EMERGENCY_STOP_FILE.exists():
            try:
                EMERGENCY_STOP_FILE.unlink()
            except Exception as e:
                logger.error(f"Failed to remove emergency stop file: {e}")
        logger.info("Emergency stop reset. Automation resumed.")

    def assert_can_proceed(self) -> None:
        """Raise EmergencyStopException if stop is engaged."""
        if self.is_stopped():
            raise EmergencyStopException(
                f"Automation halted by Emergency Stop. Reason: {self._reason or 'Active kill-switch'}"
            )


class PermissionGuard:
    """Verifies permissions before executing actions."""

    # Sensitive operations that ALWAYS require explicit approval
    SENSITIVE_ACTIONS = {
        "delete_file",
        "overwrite_file",
        "install_software",
        "send_message",
        "send_email",
        "make_payment",
        "system_shutdown",
        "system_restart",
        "format_disk",
    }

    def __init__(self, auto_approve_safe_actions: bool = True) -> None:
        self.auto_approve_safe = auto_approve_safe_actions

    def verify_action(self, action_name: str, params: Dict[str, Any]) -> bool:
        """Check if an action is permitted. Raises PermissionDeniedException if blocked."""
        EmergencyStopManager.get_instance().assert_can_proceed()

        if action_name.lower() in self.SENSITIVE_ACTIONS:
            # Sensitive operations are blocked unless interactive approval mechanism is satisfied
            raise PermissionDeniedException(
                f"Action '{action_name}' is classified as a sensitive/irreversible operation "
                f"and requires explicit user confirmation. Execution was safely blocked."
            )

        return True


class AuditLogger:
    """Logs executed automation tasks without logging credentials or keys."""

    @staticmethod
    def log_action(
        action_name: str,
        params: Dict[str, Any],
        success: bool,
        message: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        record = {
            "timestamp": datetime.datetime.now().isoformat(),
            "action": action_name,
            "params": {k: str(v)[:200] for k, v in params.items() if "key" not in k.lower() and "token" not in k.lower()},
            "success": success,
            "message": message[:500],
            "duration_ms": round(duration_ms, 2),
        }
        try:
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Could not write audit log: {e}")

