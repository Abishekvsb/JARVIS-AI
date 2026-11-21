"""State Management and Telemetry Broadcaster for JARVIS Futuristic Desktop UI."""

from __future__ import annotations

import asyncio
import datetime
import logging
import threading
from typing import Any, Dict, List, Optional, Set

from starlette.websockets import WebSocket

from jarvis.automation.safety import EmergencyStopManager
from jarvis.automation.system_controller import get_system_telemetry

logger = logging.getLogger(__name__)


class UIState:
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    EXECUTING = "EXECUTING"
    ERROR = "ERROR"


class UIStateManager:
    """Singleton manager tracking HUD state, actions, and connected clients."""

    _instance: Optional[UIStateManager] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.current_state: str = UIState.IDLE
        self.state_message: str = "All systems operational. Standing by, Sir."
        self.active_action: Optional[Dict[str, Any]] = None
        self.action_history: List[Dict[str, Any]] = []
        self.connected_websockets: Set[WebSocket] = set()
        self.telemetry_cache: Dict[str, Any] = {}
        self.voice_output_enabled: bool = True
        self.update_telemetry()

    @classmethod
    def get_instance(cls) -> UIStateManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def update_telemetry(self) -> Dict[str, Any]:
        """Fetch real system statistics via psutil."""
        try:
            self.telemetry_cache = get_system_telemetry()
            self.telemetry_cache["emergency_stop"] = EmergencyStopManager.get_instance().is_stopped()
            from jarvis.config import get_config
            cfg = get_config()
            self.telemetry_cache["ai_provider"] = getattr(cfg, "ai_provider", "ollama").upper()
            self.telemetry_cache["ai_model"] = getattr(cfg, "ollama_model", "qwen2.5:1.5b")
        except Exception as e:
            logger.error(f"Failed to fetch system telemetry: {e}")
        return self.telemetry_cache

    def set_state(self, new_state: str, message: str = "") -> None:
        """Update active AI state and message."""
        self.current_state = new_state
        if message:
            self.state_message = message
        elif new_state == UIState.IDLE:
            self.state_message = "All systems operational. Standing by, Sir."
        elif new_state == UIState.LISTENING:
            self.state_message = "Listening to microphone input..."
        elif new_state == UIState.PROCESSING:
            self.state_message = "Processing speech-to-text..."
        elif new_state == UIState.THINKING:
            self.state_message = "Analyzing command with Claude AI..."
        elif new_state == UIState.SPEAKING:
            self.state_message = "Synthesizing voice response..."
        elif new_state == UIState.EXECUTING:
            self.state_message = "Executing Windows desktop automation..."
        elif new_state == UIState.ERROR:
            self.state_message = "Alert: Emergency stop active or operation blocked."

    def add_action(self, tool: str, input_data: Any, status: str, message: str) -> Dict[str, Any]:
        """Record an automation action in the activity history."""
        action_item = {
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "tool": tool,
            "input": input_data,
            "status": status,
            "message": message,
        }
        self.action_history.insert(0, action_item)
        if len(self.action_history) > 60:
            self.action_history.pop()
        self.active_action = action_item
        return action_item

    async def register_ws(self, ws: WebSocket) -> None:
        self.connected_websockets.add(ws)

    async def unregister_ws(self, ws: WebSocket) -> None:
        self.connected_websockets.discard(ws)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        """Broadcast JSON payload to all active WebSockets."""
        dead_sockets = set()
        for ws in list(self.connected_websockets):
            try:
                await ws.send_json(payload)
            except Exception:
                dead_sockets.add(ws)
        for dead in dead_sockets:
            self.connected_websockets.discard(dead)

    async def broadcast_state(self) -> None:
        """Broadcast current AI state to all UI clients."""
        await self.broadcast({
            "type": "state_change",
            "state": self.current_state,
            "message": self.state_message,
            "active_action": self.active_action,
            "emergency_stop": EmergencyStopManager.get_instance().is_stopped(),
        })

    async def broadcast_telemetry(self) -> None:
        """Fetch and broadcast latest telemetry."""
        data = self.update_telemetry()
        await self.broadcast({
            "type": "telemetry",
            "telemetry": data,
            "emergency_stop": data.get("emergency_stop", False),
        })

