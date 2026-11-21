"""Unit and Integration Tests for JARVIS Phase 8 Mobile Access & PWA.

Tests:
1. MobileAuthManager (PIN generation, verification, token lifecycle, local IP).
2. PWA Asset Delivery (manifest.json, sw.js, app icons).
3. Auth Enforcement on Remote Calls (401 on missing token, 200 on valid token).
4. Mobile Info endpoint.
5. Mobile Voice Upload & Audio Streaming endpoints.
6. Mobile Emergency Stop Trigger.
"""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from jarvis.automation.agent import AutomationAgent
from jarvis.automation.safety import EmergencyStopManager
from jarvis.config import CACHE_DIR, JARVIS_ROOT
from jarvis.ui.auth import MobileAuthManager, get_local_network_ip
from jarvis.ui.server import create_ui_app
from jarvis.voice.stt import JarvisSTT
from jarvis.voice.tts import JarvisTTS


class TestMobileAccess(unittest.TestCase):
    """Test suite for Phase 8 Mobile Access and Authentication."""

    def setUp(self) -> None:
        self.auth_mgr = MobileAuthManager.get_instance()
        self.auth_mgr.regenerate_pin()
        EmergencyStopManager.get_instance().reset()

        # Mock agent, stt, tts for fast deterministic testing
        self.mock_agent = MagicMock(spec=AutomationAgent)
        self.mock_agent.execute_user_command.return_value = (
            "Mobile command processed successfully, Sir.",
            [{"tool": "open_app", "result": {"success": True, "message": "App opened"}}],
        )

        self.mock_stt = MagicMock(spec=JarvisSTT)
        self.mock_stt.transcribe.return_value = ("Jarvis, open notepad", "en", 0.98)

        # Create dummy audio file for TTS
        self.test_audio_file = CACHE_DIR / "temp" / "test_mobile_reply.mp3"
        self.test_audio_file.parent.mkdir(parents=True, exist_ok=True)
        self.test_audio_file.write_bytes(b"\xFF\xFB\x90\x00DummyMP3Bytes")

        self.mock_tts = MagicMock(spec=JarvisTTS)
        self.mock_tts.synthesize.return_value = self.test_audio_file

        self.app = create_ui_app(
            agent=self.mock_agent,
            stt=self.mock_stt,
            tts=self.mock_tts,
        )
        self.client = TestClient(self.app)

    def test_01_auth_manager_lifecycle(self) -> None:
        """Test PIN generation, validation, and token expiration."""
        pin = self.auth_mgr.pairing_pin
        self.assertEqual(len(pin), 6)
        self.assertTrue(pin.isdigit())

        # Invalid PIN must fail
        token_fail = self.auth_mgr.verify_pin("000000", client_ip="192.168.1.100")
        self.assertIsNone(token_fail)

        # Valid PIN must issue a hex token
        token_success = self.auth_mgr.verify_pin(pin, client_ip="192.168.1.100")
        self.assertIsNotNone(token_success)
        self.assertGreater(len(token_success), 20)
        self.assertTrue(self.auth_mgr.is_token_valid(token_success))

        # Revoke token
        self.auth_mgr.revoke_token(token_success)
        self.assertFalse(self.auth_mgr.is_token_valid(token_success))
        print("\n[PASS] MobileAuthManager PIN Lifecycle & Token Verification Succeeded.")

    def test_02_local_network_ip_discovery(self) -> None:
        """Test local network IP discovery."""
        ip = get_local_network_ip()
        self.assertIsInstance(ip, str)
        self.assertGreater(len(ip), 6)
        print(f"\n[PASS] Local Network IPv4 Discovered: {ip}")

    def test_03_pwa_asset_delivery(self) -> None:
        """Test PWA manifest and service worker delivery."""
        res_manifest = self.client.get("/manifest.json")
        self.assertEqual(res_manifest.status_code, 200)
        manifest_data = res_manifest.json()
        self.assertEqual(manifest_data.get("name"), "JARVIS AI Assistant")
        self.assertEqual(manifest_data.get("display"), "standalone")

        res_sw = self.client.get("/sw.js")
        self.assertEqual(res_sw.status_code, 200)
        self.assertIn("jarvis-pwa", res_sw.text)
        print("\n[PASS] PWA Web App Manifest & Service Worker Delivery Verified.")

    def test_04_mobile_info_endpoint(self) -> None:
        """Test /api/mobile/info."""
        res = self.client.get("/api/mobile/info")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("local_ip", data)
        self.assertIn("pairing_pin", data)
        self.assertEqual(data["pairing_pin"], self.auth_mgr.pairing_pin)
        print(f"\n[PASS] Mobile Info Endpoint Verified: IP={data['local_ip']} | PIN={data['pairing_pin']}")

    def test_05_auth_verify_api(self) -> None:
        """Test POST /api/auth/verify endpoint."""
        # Fail attempt
        res_fail = self.client.post("/api/auth/verify", json={"pin": "wrong!"})
        self.assertEqual(res_fail.status_code, 200)
        self.assertEqual(res_fail.json().get("status"), "error")

        # Success attempt
        res_ok = self.client.post("/api/auth/verify", json={"pin": self.auth_mgr.pairing_pin})
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("token", data)
        print("\n[PASS] Mobile PIN Authentication API Verified.")

    def test_06_remote_auth_enforcement(self) -> None:
        """Test that simulated remote client requires authentication."""
        # TestClient defaults client host to "testclient"
        # When request comes from unauthenticated remote IP:
        with patch.object(self.auth_mgr, "is_request_authenticated", return_value=False):
            res_blocked = self.client.post("/api/chat", json={"message": "Open calculator"})
            self.assertEqual(res_blocked.status_code, 401)
            self.assertIn("Pairing Authentication Required", res_blocked.json().get("detail", ""))

        # When valid token is provided:
        valid_token = self.auth_mgr.verify_pin(self.auth_mgr.pairing_pin, "192.168.1.50")
        res_allowed = self.client.post(
            "/api/chat",
            json={"message": "Open calculator"},
            headers={"X-Jarvis-Token": valid_token},
        )
        self.assertEqual(res_allowed.status_code, 200)
        self.assertEqual(res_allowed.json().get("status"), "success")
        print("\n[PASS] Remote Device Auth Enforcement (401 Block / Token Allow) Verified.")

    def test_07_mobile_voice_upload_pipeline(self) -> None:
        """Test receiving recorded audio from mobile phone and returning spoken reply."""
        valid_token = self.auth_mgr.verify_pin(self.auth_mgr.pairing_pin, "192.168.1.50")

        # Create dummy audio payload
        fake_audio_bytes = b"RIFF....WAVEfmt ....data...."
        files = {"audio": ("mobile_rec.wav", io.BytesIO(fake_audio_bytes), "audio/wav")}

        res = self.client.post(
            "/api/voice/mobile-upload",
            files=files,
            data={"speak": "true"},
            headers={"X-Jarvis-Token": valid_token},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("user_text"), "Jarvis, open notepad")
        self.assertIn("Mobile command processed", data.get("reply", ""))
        self.assertIn("/api/voice/audio/", data.get("audio_url", ""))
        print(f"\n[PASS] Mobile Voice Upload & STT->Agent->TTS Loop Verified: {data['audio_url']}")

    def test_08_audio_streaming_endpoint(self) -> None:
        """Test streaming generated audio back to mobile device."""
        filename = self.test_audio_file.name
        res = self.client.get(f"/api/voice/audio/{filename}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("content-type"), "audio/mpeg")
        self.assertEqual(res.content, self.test_audio_file.read_bytes())
        print(f"\n[PASS] Mobile Audio Streaming Endpoint Verified: {len(res.content)} bytes.")

    def test_09_mobile_emergency_stop(self) -> None:
        """Test triggering Emergency Stop from mobile device."""
        esm = EmergencyStopManager.get_instance()
        self.assertFalse(esm.is_stopped())

        res = self.client.post("/api/emergency-stop/trigger")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(esm.is_stopped())

        res_reset = self.client.post("/api/emergency-stop/reset")
        self.assertEqual(res_reset.status_code, 200)
        self.assertFalse(esm.is_stopped())
        print("\n[PASS] Mobile Emergency Stop Killswitch Verified.")


if __name__ == "__main__":
    unittest.main(verbosity=2)

