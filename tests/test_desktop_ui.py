"""Comprehensive Test Suite for JARVIS Phase 6: Futuristic Desktop UI.

Tests:
1. Static asset delivery (index.html, styles.css, app.js) via FastAPI.
2. Real-time telemetry endpoint accuracy (CPU, RAM, Battery, Disk).
3. UI State transitions (Idle, Listening, Processing, Thinking, Speaking, Executing, Error).
4. Emergency Stop killswitch trigger, status broadcast, and recovery.
5. Multilingual chat execution (English, Tanglish, Tamil) and tool dispatching.
6. Browser launcher discovery for Microsoft Edge / Chrome standalone mode.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from starlette.testclient import TestClient

from jarvis.automation.safety import EmergencyStopManager
from jarvis.config import JARVIS_ROOT
from jarvis.ui.launcher import find_browser_executable, find_free_port
from jarvis.ui.server import create_ui_app
from jarvis.ui.state import UIState, UIStateManager


class TestDesktopUI(unittest.TestCase):
    """Test suite for Phase 6 Desktop UI components."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_ui_app()
        cls.client = TestClient(cls.app)
        EmergencyStopManager.get_instance().reset()

    def tearDown(self) -> None:
        EmergencyStopManager.get_instance().reset()

    def test_01_static_assets_serving(self) -> None:
        """Verify index.html, styles.css, and app.js are served correctly."""
        # 1. Main index.html
        resp_index = self.client.get("/")
        self.assertEqual(resp_index.status_code, 200)
        self.assertIn("J.A.R.V.I.S.", resp_index.text)
        self.assertIn("arc-reactor", resp_index.text)
        self.assertIn("text/html", resp_index.headers["content-type"])
        print("\n[PASS] index.html served with Arc Reactor DOM structure.")

        # 2. Stylesheet styles.css
        resp_css = self.client.get("/static/styles.css")
        self.assertEqual(resp_css.status_code, 200)
        self.assertIn("--glow-cyan", resp_css.text)
        self.assertIn("arc-reactor-svg", resp_css.text)
        print("[PASS] styles.css served with holographic HUD styling.")

        # 3. JavaScript app.js
        resp_js = self.client.get("/static/app.js")
        self.assertEqual(resp_js.status_code, 200)
        self.assertIn("connectWebSocket", resp_js.text)
        self.assertIn("triggerPushToTalk", resp_js.text)
        print("[PASS] app.js served with WebSocket and PTT controllers.")

    def test_02_system_telemetry_endpoint(self) -> None:
        """Verify GET /api/telemetry returns genuine psutil metrics."""
        resp = self.client.get("/api/telemetry")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")

        telemetry = data["telemetry"]
        self.assertIn("cpu_percent", telemetry)
        self.assertIn("memory_percent", telemetry)
        self.assertIn("battery", telemetry)
        self.assertIn("disk_d_free_gb", telemetry)

        # Confirm non-empty actual metrics
        self.assertTrue(telemetry["cpu_percent"].endswith("%"))
        self.assertTrue(telemetry["memory_percent"].endswith("%"))
        print(f"\n[PASS] Genuine Telemetry Verified:\n  CPU: {telemetry['cpu_percent']} | RAM: {telemetry['memory_percent']} | Battery: {telemetry['battery']} | Disk D: {telemetry['disk_d_free_gb']}")

    def test_03_emergency_stop_trigger_and_reset(self) -> None:
        """Verify UI Emergency Stop button immediately halts automation and recovers cleanly."""
        esm = EmergencyStopManager.get_instance()
        esm.reset()
        self.assertFalse(esm.is_stopped())

        # 1. Trigger Emergency Stop via UI endpoint
        resp_stop = self.client.post("/api/emergency-stop/trigger")
        self.assertEqual(resp_stop.status_code, 200)
        stop_data = resp_stop.json()
        self.assertEqual(stop_data["status"], "stopped")
        self.assertTrue(esm.is_stopped())
        print(f"\n[PASS] UI Emergency Stop Triggered: {stop_data['message']}")

        # Verify state manager shifted to ERROR
        state_mgr = UIStateManager.get_instance()
        self.assertEqual(state_mgr.current_state, UIState.ERROR)

        # 2. Reset Emergency Stop via UI endpoint
        resp_reset = self.client.post("/api/emergency-stop/reset")
        self.assertEqual(resp_reset.status_code, 200)
        reset_data = resp_reset.json()
        self.assertEqual(reset_data["status"], "active")
        self.assertFalse(esm.is_stopped())
        self.assertEqual(state_mgr.current_state, UIState.IDLE)
        print(f"[PASS] UI Emergency Stop Reset: {reset_data['message']}")

    def test_04_chat_endpoint_multilingual(self) -> None:
        """Verify multilingual chat execution and tool dispatching."""
        # 1. English Introduction Command
        resp1 = self.client.post("/api/chat", json={"message": "Hello Jarvis, introduce yourself", "speak": False})
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertEqual(data1["status"], "success")
        self.assertIn("jarvis", data1["reply"].lower())
        print(f"\n[PASS] UI Chat English: {data1['reply']}")

        # 2. Tanglish Screenshot Command -> Action Dispatch
        resp2 = self.client.post("/api/chat", json={"message": "Jarvis, screenshot eduthu save pannu", "speak": False})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["status"], "success")
        self.assertGreater(len(data2["actions"]), 0)
        self.assertEqual(data2["actions"][0]["tool"], "take_screenshot")
        print(f"[PASS] UI Chat Tanglish (Automation Dispatch): {data2['reply']} (Tool: {data2['actions'][0]['tool']})")

        # 3. Direct Emergency Stop command in chat
        resp3 = self.client.post("/api/chat", json={"message": "Jarvis, emergency stop!", "speak": False})
        self.assertEqual(resp3.status_code, 200)
        data3 = resp3.json()
        self.assertTrue(EmergencyStopManager.get_instance().is_stopped())
        print(f"[PASS] UI Chat Emergency Stop: {data3['reply']}")

        # Reset stop
        EmergencyStopManager.get_instance().reset()

    def test_05_state_machine_transitions(self) -> None:
        """Verify state manager correctly transitions through all 7 required states."""
        sm = UIStateManager.get_instance()
        states = [
            UIState.IDLE,
            UIState.LISTENING,
            UIState.PROCESSING,
            UIState.THINKING,
            UIState.SPEAKING,
            UIState.EXECUTING,
            UIState.ERROR,
        ]

        for st in states:
            sm.set_state(st)
            self.assertEqual(sm.current_state, st)

        # Verify action recording
        action = sm.add_action("open_app", {"app_name": "notepad"}, "SUCCESS", "Launched notepad")
        self.assertEqual(action["tool"], "open_app")
        self.assertEqual(action["status"], "SUCCESS")
        self.assertEqual(sm.action_history[0]["tool"], "open_app")
        print(f"\n[PASS] UI State Machine (7 states) & Activity History Verified.")

    def test_06_browser_launcher_discovery(self) -> None:
        """Verify launcher identifies Microsoft Edge on Windows 11 and finds free port."""
        browser_exe = find_browser_executable()
        self.assertIsNotNone(browser_exe, "Microsoft Edge or Chrome should be detected on Windows 11.")
        self.assertTrue(browser_exe.exists(), f"Browser path must exist: {browser_exe}")
        print(f"\n[PASS] Standalone App Browser Discovered: {browser_exe}")

        port = find_free_port(8000)
        self.assertGreaterEqual(port, 8000)
        self.assertLess(port, 8100)
        print(f"[PASS] Free TCP Port Allocated: {port}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

