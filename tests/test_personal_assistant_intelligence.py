"""Comprehensive Test Suite for Personal Assistant Intelligence, Multi-Turn Context,
Auto-Reply Engine, Notification Hub, and HUD Endpoints.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from jarvis.automation.agent import AutomationAgent
from jarvis.conversation_brain import ConversationBrain
from jarvis.mobile.auto_reply import AutoReplyConfig, AutoReplyEngine
from jarvis.mobile.notification_hub import NotificationHub, NotificationPriority
from jarvis.ui.server import create_ui_app


class TestPersonalAssistantIntelligence(unittest.TestCase):

    def setUp(self):
        self.brain = ConversationBrain.get_instance(user_name="Abishek")
        self.notif_hub = NotificationHub.get_instance()
        self.auto_reply = AutoReplyEngine.get_instance()
        self.notif_hub.clear()
        self.brain.state.pending_action = None
        self.brain.state.waiting_for_confirmation = False
        self.brain.state.active_contact = None
        self.brain.state.recent_responses.clear()
        self.auto_reply.update_config(enabled=False, greeting_auto_reply_enabled=False)

    def test_01_multi_turn_dialogue_and_pronoun_resolution(self):
        """Me: 'Jarvis, WhatsApp la yaar message pannirukanga?'
           JARVIS: 'Abishek, Arun has sent you a message.'
           Me: 'Enna message?'
           JARVIS: 'Arun sent: "Hi, are you available?"'
           Me: 'Avanukku good morning sollu'
           JARVIS: 'Arun-ku "good morning" message send pannava, Abishek?'
           Me: 'Yes'
           JARVIS: 'Message sent to Arun successfully, Sir.'
        """
        # Ingest notification
        accepted, notif, _ = self.notif_hub.ingest_notification(
            app="WhatsApp",
            sender="Arun",
            content="Hi, are you available?",
        )
        self.assertTrue(accepted)
        self.assertEqual(notif.sender, "Arun")

        agent = AutomationAgent()

        # Step 1: Who messaged?
        reply1, actions1 = agent.execute_user_command("Jarvis, WhatsApp la yaar message pannirukanga?")
        self.assertIn("Arun", reply1)
        self.assertIn("message", reply1)
        self.assertEqual(len(actions1), 0)

        # Step 2: What did he say?
        reply2, actions2 = agent.execute_user_command("Enna message?")
        self.assertIn("Hi, are you available?", reply2)
        self.assertEqual(len(actions2), 0)

        # Step 3: Tell him good morning (Pronoun: 'avanukku' -> Arun)
        reply3, actions3 = agent.execute_user_command("Avanukku good morning sollu")
        self.assertIn("Arun", reply3)
        self.assertIn("good morning", reply3.lower())
        self.assertIn("send pannava", reply3.lower())
        self.assertTrue(self.brain.state.waiting_for_confirmation)
        self.assertIsNotNone(self.brain.state.pending_action)
        self.assertEqual(len(actions3), 0)

        # Step 4: Confirm Yes
        reply4, actions4 = agent.execute_user_command("Yes")
        self.assertIn("Message sent to Arun successfully", reply4)
        self.assertEqual(len(actions4), 1)
        self.assertEqual(actions4[0]["tool"], "send_whatsapp_message")
        self.assertEqual(actions4[0]["input"]["recipient"], "Arun")
        self.assertEqual(actions4[0]["input"]["message"], "good morning")
        self.assertFalse(self.brain.state.waiting_for_confirmation)

    def test_02_dialogue_cancellation(self):
        """User denies confirmation with 'No' / 'vendaam'."""
        self.brain.update_incoming_notification("WhatsApp", "Karthik", "Are you free?")
        agent = AutomationAgent()

        # Ask to reply
        reply1, _ = agent.execute_user_command("Karthik-ku I will call later sollu")
        self.assertTrue(self.brain.state.waiting_for_confirmation)

        # Deny
        reply2, actions = agent.execute_user_command("No, cancel it")
        self.assertIn("Cancelled", reply2)
        self.assertFalse(self.brain.state.waiting_for_confirmation)
        self.assertEqual(len(actions), 0)

    def test_03_anti_repetition_filter(self):
        """Ensure identical or repetitive assistant responses are diversified."""
        r1 = self.brain.filter_response("Good day, Sir. I have completed your request.")
        self.assertNotIn("Good day, Sir.", r1)  # Boilerplate trimmed

        # Duplicate incoming response should be intercepted
        r2 = self.brain.filter_response("I have completed your request.")
        self.assertIn("Standing by for your next instruction", r2)

    def test_04_auto_reply_rules_and_security_blacklist(self):
        """Test auto-reply: OFF by default, greeting auto-reply when enabled, security checks."""
        # Test 1: OFF by default
        self.auto_reply.update_config(enabled=False, greeting_auto_reply_enabled=False)
        _, n1, _ = self.notif_hub.ingest_notification("WhatsApp", "Priya", "Hi")
        self.assertFalse(n1.auto_replied)

        # Test 2: Enabled Greeting Auto-Reply
        self.auto_reply.update_config(enabled=True, greeting_auto_reply_enabled=True)
        _, n2, _ = self.notif_hub.ingest_notification("WhatsApp", "Sanjay", "Good morning")
        self.assertTrue(n2.auto_replied)
        self.assertIn("Good morning! Have a great day.", n2.auto_reply_text)

        # Test 3: Security blacklist (OTP / Bank Alert)
        _, n3, _ = self.notif_hub.ingest_notification("SMS", "HDFC-BANK", "Your OTP is 749210 for credit card transaction.")
        self.assertFalse(n3.auto_replied)

        # Test 4: Question requires manual reply (no auto-reply)
        _, n4, _ = self.notif_hub.ingest_notification("WhatsApp", "Ramesh", "Are you coming to the meeting today?")
        self.assertFalse(n4.auto_replied)

    def test_05_notification_priority_classification(self):
        """Test priority classification: HIGH for emergencies/security, MEDIUM for direct chats."""
        p_high = self.notif_hub.classify_priority("WhatsApp", "Security", "Urgent alert: Login from new device")
        self.assertEqual(p_high, NotificationPriority.HIGH)

        p_med = self.notif_hub.classify_priority("WhatsApp", "Arun", "Hey bro, how are you?")
        self.assertEqual(p_med, NotificationPriority.MEDIUM)

        p_low = self.notif_hub.classify_priority("YouTube", "Channel", "New video uploaded")
        self.assertEqual(p_low, NotificationPriority.LOW)

    def test_06_notification_and_settings_endpoints(self):
        """Test REST API endpoints for notification ingestion and auto-reply settings."""
        app = create_ui_app()
        client = TestClient(app)

        # 1. Ingest notification via API
        resp = client.post(
            "/api/notifications/ingest",
            json={
                "app": "WhatsApp",
                "sender": "Divya",
                "content": "Hello Abishek!",
                "timestamp": time.time(),
            },
            headers={"host": "localhost"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["notification"]["sender"], "Divya")

        # 2. Query notifications
        resp2 = client.get("/api/notifications")
        self.assertEqual(resp2.status_code, 200)
        self.assertGreaterEqual(resp2.json()["unread_count"], 1)

        # 3. Get Auto-reply settings
        resp3 = client.get("/api/settings/auto-reply")
        self.assertEqual(resp3.status_code, 200)
        self.assertIn("greeting_auto_reply_enabled", resp3.json())

        # 4. Update Auto-reply settings
        resp4 = client.post(
            "/api/settings/auto-reply",
            json={
                "enabled": True,
                "greeting_auto_reply_enabled": True,
                "allowed_apps": ["WhatsApp", "Telegram"],
            },
            headers={"host": "localhost"},
        )
        self.assertEqual(resp4.status_code, 200)
        self.assertEqual(resp4.json()["status"], "success")
        self.assertTrue(self.auto_reply.config.enabled)
        self.assertTrue(self.auto_reply.config.greeting_auto_reply_enabled)


if __name__ == "__main__":
    unittest.main()

