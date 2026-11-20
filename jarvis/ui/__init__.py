"""JARVIS Futuristic Desktop UI Package.

Provides a modern Iron Man-inspired HUD desktop application interface with:
- Central animated Arc Reactor AI visualizer
- Live AI state machine (Idle, Listening, Processing, Thinking, Speaking, Executing, Error)
- Real-time CPU, RAM, and Battery telemetry gauges
- Voice interaction and Push-to-Talk controls
- Full multilingual chat (Tamil, Tanglish, English)
- Automation activity monitor with action feedback
- Hardware-level Emergency Stop killswitch
"""

from jarvis.ui.server import create_ui_app
from jarvis.ui.state import UIState, UIStateManager

__all__ = [
    "UIState",
    "UIStateManager",
    "create_ui_app",
]

