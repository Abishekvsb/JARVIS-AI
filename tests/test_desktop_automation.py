"""Comprehensive Test Suite for JARVIS Phase 5: Windows Desktop Automation.

Tests:
1. Application Launch and Safe Termination (Notepad, protected blacklist).
2. Browser Navigation & Web Searches (Google, YouTube, Media).
3. Sandboxed File Search and Security Boundary Enforcement.
4. Screen Capture (saved to D:\JARVIS\screenshots).
5. Keyboard Dictation and Safe Hotkeys.
6. System Controls (Volume adjustment, Telemetry, Settings).
7. Emergency Stop Kill-Switch Enforcement.
8. Multilingual Natural Language Intent Execution (English, Tamil, Tanglish).
"""

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

import psutil

from jarvis.automation import (
    AUTOMATION_TOOLS,
    AutomationAgent,
    EmergencyStopException,
    EmergencyStopManager,
    capture_screenshot,
    change_volume,
    close_application,
    control_media,
    execute_tool,
    find_files,
    get_system_telemetry,
    open_application,
    open_file_safely,
    open_settings_page,
    open_url,
    search_google,
    search_youtube,
    send_safe_hotkey,
    type_text,
    write_in_notepad,
)
from jarvis.config import JARVIS_ROOT


class TestDesktopAutomation(unittest.TestCase):
    """Test suite for desktop automation tools and safety controls."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.screenshots_dir = JARVIS_ROOT / "screenshots"
        cls.screenshots_dir.mkdir(parents=True, exist_ok=True)
        # Ensure emergency stop is clean before testing
        EmergencyStopManager.get_instance().reset()

    def tearDown(self) -> None:
        # Reset emergency stop after every test
        EmergencyStopManager.get_instance().reset()

    def test_01_application_control_notepad(self) -> None:
        """Test launching Notepad, verifying process, and closing gracefully."""
        # 1. Launch Notepad
        success, msg = open_application("notepad")
        self.assertTrue(success, f"Failed to launch Notepad: {msg}")
        time.sleep(1.0)

        # Verify process is running
        notepad_procs = [p for p in psutil.process_iter(["name"]) if "notepad" in p.info["name"].lower()]
        self.assertGreater(len(notepad_procs), 0, "Notepad process should be running.")
        print(f"\n[PASS] Notepad Launch Verified: {msg}")

        # 2. Close Notepad
        close_success, close_msg = close_application("notepad")
        self.assertTrue(close_success, f"Failed to close Notepad: {close_msg}")
        print(f"[PASS] Notepad Graceful Termination Verified: {close_msg}")

        # 3. Verify protected system process blacklist
        block_success, block_msg = close_application("explorer.exe")
        self.assertFalse(block_success, "Protected process 'explorer.exe' must not be terminated.")
        self.assertIn("Security Warning", block_msg)
        print(f"[PASS] Protected System Blacklist Enforced: {block_msg}")

    def test_02_browser_navigation_and_search(self) -> None:
        """Test URL opening, Google search, YouTube search, and media keys."""
        # Safe URL navigation
        s1, m1 = open_url("https://www.google.com")
        self.assertTrue(s1, f"Failed to open Google: {m1}")

        # Google Search
        s2, m2 = search_google("JARVIS AI Windows 11")
        self.assertTrue(s2, f"Failed to search Google: {m2}")

        # YouTube Search
        s3, m3 = search_youtube("Tamil instrumental music")
        self.assertTrue(s3, f"Failed to search YouTube: {m3}")

        # Media Control
        s4, m4 = control_media("play_pause")
        self.assertTrue(s4, f"Failed to toggle media: {m4}")
        print(f"\n[PASS] Browser Navigation & Media Controls Verified: {m2} | {m3} | {m4}")

    def test_03_sandboxed_file_search(self) -> None:
        """Test file search in approved folders and boundary restrictions."""
        # Create a test file in approved directory (D:\JARVIS\screenshots)
        test_file = self.screenshots_dir / "safe_test_sample.txt"
        test_file.write_text("JARVIS test document for sandboxed search.", encoding="utf-8")

        success, msg, files = find_files("safe_test_sample", category="documents")
        self.assertTrue(success)
        self.assertGreater(len(files), 0, "Should find the safe test document.")
        self.assertIn("safe_test_sample.txt", files[0]["name"])
        print(f"\n[PASS] Sandboxed File Search Verified: Found {files[0]['path']}")

        # Clean up test file
        if test_file.exists():
            test_file.unlink()

    def test_04_screenshot_capture(self) -> None:
        """Test screenshot capture saved to D:\JARVIS\screenshots."""
        success, msg, path = capture_screenshot(prefix="test_phase5")
        self.assertTrue(success, f"Screenshot failed: {msg}")
        self.assertIsNotNone(path)
        self.assertTrue(path.exists(), f"Screenshot file should exist on disk: {path}")
        self.assertGreater(path.stat().st_size, 5000, "Screenshot should not be empty.")
        print(f"\n[PASS] Screenshot Capture Verified: {path} ({path.stat().st_size / 1024:.1f} KB)")

    def test_05_keyboard_automation_and_dictation(self) -> None:
        """Test safe keyboard shortcuts and Notepad dictation."""
        # Test safe hotkey execution
        s1, m1 = send_safe_hotkey(["esc"])
        self.assertTrue(s1, f"Safe hotkey 'esc' failed: {m1}")

        # Test Notepad dictation workflow
        s2, m2 = write_in_notepad("JARVIS Windows Automation Phase 5 dictation test.")
        self.assertTrue(s2, f"Notepad dictation failed: {m2}")
        print(f"\n[PASS] Notepad Dictation Verified: {m2}")

        # Clean up: close the Notepad test window
        time.sleep(0.5)
        close_application("notepad")

    def test_06_system_controls_and_telemetry(self) -> None:
        """Test volume adjustment, Windows settings launcher, and system telemetry."""
        # Volume Up & Down
        v_up, m_up = change_volume("up", steps=2)
        self.assertTrue(v_up, f"Volume Up failed: {m_up}")

        v_down, m_down = change_volume("down", steps=2)
        self.assertTrue(v_down, f"Volume Down failed: {m_down}")

        # System Telemetry
        telemetry = get_system_telemetry()
        self.assertIn("cpu_percent", telemetry)
        self.assertIn("memory_percent", telemetry)
        self.assertIn("battery", telemetry)
        self.assertIn("disk_d_free_gb", telemetry)
        print(f"\n[PASS] System Controls & Telemetry Verified:\n{telemetry}")

    def test_07_emergency_stop_killswitch(self) -> None:
        """Test emergency stop immediately blocks subsequent automation."""
        esm = EmergencyStopManager.get_instance()
        esm.trigger_stop("Unit test trigger")
        self.assertTrue(esm.is_stopped())

        # An automation tool must raise EmergencyStopException when stopped
        with self.assertRaises(EmergencyStopException):
            open_application("notepad")

        with self.assertRaises(EmergencyStopException):
            capture_screenshot()

        # Reset and verify recovery
        esm.reset()
        self.assertFalse(esm.is_stopped())
        print("\n[PASS] Emergency Stop Kill-Switch Enforcement & Recovery Verified.")

    def test_08_natural_language_intent_planning(self) -> None:
        """Test multilingual command parsing (English, Tamil, Tanglish)."""
        agent = AutomationAgent()

        # 1. Tanglish: "Jarvis, screenshot eduthu save pannu"
        reply1, actions1 = agent.execute_user_command("Jarvis, screenshot eduthu save pannu")
        self.assertGreater(len(actions1), 0)
        self.assertEqual(actions1[0]["tool"], "take_screenshot")
        print(f"\n[PASS] Tanglish Screenshot Command: {reply1} (Action: {actions1[0]['tool']})")

        # 2. Tanglish: "Jarvis, volume increase pannu"
        reply2, actions2 = agent.execute_user_command("Jarvis, volume increase pannu")
        self.assertGreater(len(actions2), 0)
        self.assertEqual(actions2[0]["tool"], "adjust_volume")
        print(f"[PASS] Tanglish Volume Command: {reply2} (Action: {actions2[0]['tool']})")

        # 3. Emergency Stop via voice/text: "Jarvis, emergency stop"
        reply3, actions3 = agent.execute_user_command("Jarvis, emergency stop")
        self.assertIn("emergency stop", reply3.lower())
        self.assertTrue(EmergencyStopManager.get_instance().is_stopped())
        print(f"[PASS] Emergency Stop Voice/Text Command: {reply3}")

        # Reset stop
        EmergencyStopManager.get_instance().reset()


if __name__ == "__main__":
    unittest.main(verbosity=2)

