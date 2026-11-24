"""Unit Tests for JARVIS 24/7 Cloud Backend Server."""

from __future__ import annotations

import time
import unittest
from fastapi.testclient import TestClient

from jarvis.cloud_server import app
from jarvis.conversation_brain import ConversationBrain
from jarvis.mobile.auto_reply import AutoReplyEngine
from jarvis.mobile.notification_hub import NotificationHub


class TestCloudServer(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.notif_hub = NotificationHub.get_instance()
        self.auto_reply = AutoReplyEngine.get_instance()
        self.brain = ConversationBrain.get_instance("Abishek")
        self.notif_hub.clear()
        self.auto_reply.update_config(enabled=False, greeting_auto_reply_enabled=False)

    def test_01_health_and_telemetry(self):
        """Test cloud health check and telemetry endpoints."""
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("24/7", data["mode"])

        r2 = self.client.get("/api/telemetry")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("telemetry", r2.json())

    def test_02_auth_enforcement(self):
        """Test authentication barrier on cloud endpoints."""
        # Unauthenticated request from non-localhost (simulate remote host)
        r = self.client.post(
            "/api/notifications/ingest",
            json={"app": "WhatsApp", "sender": "Arun", "content": "Hi"},
            headers={"host": "api.jarvis.cloud"},  # Non-localhost
        )
        self.assertEqual(r.status_code, 401)

        # Authenticated request with pairing PIN
        r2 = self.client.post(
            "/api/notifications/ingest",
            json={"app": "WhatsApp", "sender": "Arun", "content": "Hi"},
            headers={"host": "api.jarvis.cloud", "X-Jarvis-PIN": "280506"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["status"], "success")

    def test_03_automatic_greeting_replies_cloud_pipeline(self):
        """Test that cloud backend correctly returns auto-reply instructions to Android."""
        self.auto_reply.update_config(enabled=True, greeting_auto_reply_enabled=True)

        greetings_to_test = [
            ("Hi", "Hi!"),
            ("Hello", "Hello!"),
            ("Good morning", "Good morning! Have a great day."),
            ("Good evening", "Good evening! Hope you had a great day."),
            ("Good night", "Good night! Take care."),
            ("How are you?", "I'm good, thank you! How are you?"),
        ]

        for idx, (incoming, expected_reply) in enumerate(greetings_to_test):
            sender = f"Contact_{idx}"
            resp = self.client.post(
                "/api/notifications/ingest",
                json={"app": "WhatsApp", "sender": sender, "content": incoming},
                headers={"X-Jarvis-PIN": "280506"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            notif = data.get("notification", {})
            self.assertTrue(notif.get("auto_replied"), f"Failed to auto-reply for '{incoming}'")
            self.assertEqual(notif.get("auto_reply_text"), expected_reply)

    def test_04_security_blacklist_on_cloud(self):
        """Verify that bank alerts and OTPs are blocked from auto-reply on cloud."""
        self.auto_reply.update_config(enabled=True, greeting_auto_reply_enabled=True)

        resp = self.client.post(
            "/api/notifications/ingest",
            json={"app": "SMS", "sender": "SBI-BANK", "content": "Your OTP is 921021 for Rs. 5000 transaction."},
            headers={"X-Jarvis-PIN": "280506"},
        )
        self.assertEqual(resp.status_code, 200)
        notif = resp.json().get("notification", {})
        self.assertFalse(notif.get("auto_replied"))
        self.assertIsNone(notif.get("auto_reply_text"))

    def test_05_settings_persistence(self):
        """Test updating auto-reply settings via cloud API."""
        resp = self.client.post(
            "/api/settings/auto-reply",
            json={
                "enabled": True,
                "greeting_auto_reply_enabled": True,
                "allowed_apps": ["WhatsApp", "Telegram"],
                "cooldown_seconds": 180,
            },
            headers={"X-Jarvis-PIN": "280506"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.auto_reply.config.enabled)
        self.assertEqual(self.auto_reply.config.cooldown_seconds, 180)


if __name__ == "__main__":
    unittest.main()

