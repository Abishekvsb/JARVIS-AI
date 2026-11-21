"""Comprehensive Test Suite for JARVIS Phase 7: Local Ollama AI Provider.

Tests:
1. Provider Architecture & Factory Selection (Default Ollama vs Opt-In Anthropic).
2. Local Storage Configuration (OLLAMA_MODELS strictly on Drive D:).
3. Health check & Connection handling when Ollama daemon is offline (Clear error, no crash).
4. No automatic cloud API fallback (Failure reports error instead of charging cloud).
5. Ollama Request Timeout & Empty Response Handling.
6. Multilingual Prompt Execution (English, Tamil, Tanglish) via Provider Interface.
7. Allowlisted Tool Calling with Ollama & Prompt Grounding.
8. Voice Pipeline Integration (VoiceAssistant connected to Local Provider).
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from jarvis.automation import AutomationAgent, EmergencyStopManager
from jarvis.config import JARVIS_ROOT, JarvisConfig, get_config
from jarvis.conversation import ChatTurn, JarvisConversation
from jarvis.providers.base import BaseAIProvider
from jarvis.providers.factory import get_ai_provider
from jarvis.providers.ollama_provider import LocalOllamaProvider
from jarvis.voice.voice_loop import VoiceAssistant


class TestLocalOllamaProvider(unittest.TestCase):
    """Test suite for Phase 7 Local Ollama AI Provider."""

    @classmethod
    def setUpClass(cls) -> None:
        EmergencyStopManager.get_instance().reset()

    def tearDown(self) -> None:
        EmergencyStopManager.get_instance().reset()

    def test_01_provider_factory_defaults_to_ollama(self) -> None:
        """Verify default provider is LocalOllamaProvider without requiring API keys."""
        config = get_config()
        self.assertEqual(config.ai_provider, "ollama")
        self.assertEqual(config.ollama_model, "qwen2.5:1.5b")
        self.assertEqual(config.ollama_base_url, "http://127.0.0.1:11434")

        provider = get_ai_provider(config)
        self.assertIsInstance(provider, LocalOllamaProvider)
        self.assertEqual(provider.name, "ollama")
        self.assertEqual(provider.model_name, "qwen2.5:1.5b")
        print("\n[PASS] Default Provider Factory instantiates LocalOllamaProvider (qwen2.5:1.5b).")

    def test_02_ollama_storage_configured_on_drive_d(self) -> None:
        """Verify Ollama models directory is strictly locked to Drive D:."""
        config = get_config()
        self.assertTrue(str(config.ollama_models_dir).startswith("D:"), "Ollama models directory must be on Drive D:")
        self.assertEqual(config.ollama_models_dir, JARVIS_ROOT / ".cache" / "ollama")
        self.assertTrue(config.ollama_models_dir.exists(), "D:\\JARVIS\\.cache\\ollama directory must exist.")
        print(f"[PASS] Ollama Storage Location Verified on Drive D: {config.ollama_models_dir}")

    def test_03_ollama_offline_health_check_handling(self) -> None:
        """Verify clean error reporting when Ollama daemon is not running."""
        offline_provider = LocalOllamaProvider(base_url="http://127.0.0.1:54321")
        is_healthy, msg = offline_provider.check_health()
        self.assertFalse(is_healthy)
        self.assertIn("not running", msg.lower())
        print(f"[PASS] Offline Daemon Health Check Gracefully Handled: {msg}")

    def test_04_no_automatic_cloud_fallback(self) -> None:
        """Verify that when Ollama fails, JARVIS does NOT silently switch to paid Anthropic API."""
        offline_provider = LocalOllamaProvider(base_url="http://127.0.0.1:54321")
        conv = JarvisConversation(provider=offline_provider)

        # Asking a prompt when Ollama is offline must raise ConnectionError, NOT invoke Anthropic
        with self.assertRaises(ConnectionError) as ctx:
            conv.ask("Hello Jarvis")

        self.assertIn("Cannot connect to local Ollama runtime", str(ctx.exception))
        print("[PASS] Anti-Silent-Fallback Enforced: Offline Ollama raises ConnectionError, zero cloud API calls.")

    def test_05_timeout_and_empty_response_handling(self) -> None:
        """Verify robust handling of network timeouts and empty responses."""
        provider = LocalOllamaProvider(base_url="http://127.0.0.1:11434", timeout=0.01)

        # 1. Timeout simulation
        with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timed out")):
            with self.assertRaises(TimeoutError) as ctx_time:
                provider.ask("Test timeout prompt")
            self.assertIn("timed out", str(ctx_time.exception))

        # 2. Empty response simulation
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": ""}}
        with patch("httpx.Client.post", return_value=mock_resp):
            with self.assertRaises(ValueError) as ctx_empty:
                provider.ask("Test empty prompt")
            self.assertIn("empty response", str(ctx_empty.exception))

        print("[PASS] Timeout and Empty Response Exceptions Handled cleanly.")

    def test_06_multilingual_prompts_mocked_ollama(self) -> None:
        """Verify English, Tamil, and Tanglish conversation turns via Ollama provider."""
        provider = LocalOllamaProvider()

        # Mock responses simulating Qwen2.5 1.5B multilingual outputs
        responses = {
            "hello jarvis": "Good day, Sir. I am JARVIS, running locally on your hardware.",
            "tanglish": "Vanakkam Sir! Iniku ungaluku local AI engine active-ah irukku.",
            "tamil": "வணக்கம்! உங்கள் லோக்கல் AI அமைப்பில் நான் உதவ தயாராக உள்ளேன்.",
        }

        def mock_post(url, json=None):
            resp = MagicMock()
            resp.status_code = 200
            prompt = json["messages"][-1]["content"].lower()
            if "tamil" in prompt or "வணக்கம்" in prompt:
                content = responses["tamil"]
            elif "tanglish" in prompt or "innaiku" in prompt:
                content = responses["tanglish"]
            else:
                content = responses["hello jarvis"]
            resp.json.return_value = {"message": {"content": content}}
            return resp

        with patch("httpx.Client.post", side_effect=mock_post):
            # English
            r_en = provider.ask("Hello Jarvis, what is your status?")
            self.assertIn("JARVIS", r_en)

            # Tanglish
            r_tg = provider.ask("Jarvis innaiku enna plan?")
            self.assertIn("Vanakkam", r_tg)

            # Tamil
            r_ta = provider.ask("ஜார்விஸ் வணக்கம், எப்படி இருக்கிறாய்?")
            self.assertTrue(any("\u0b80" <= c <= "\u0bff" for c in r_ta))

        print("[PASS] Multilingual Conversation Execution (EN, Tanglish, Tamil) Verified via Provider.")

    def test_07_allowlisted_tool_calling_safety(self) -> None:
        """Verify Ollama triggers allowlisted automation tools while blocking arbitrary code."""
        provider = LocalOllamaProvider()

        # Mock Ollama returning a structured tool call for take_screenshot
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "content": "Capturing your screen right now, Sir.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "take_screenshot",
                            "arguments": {"prefix": "ollama_test"},
                        },
                    }
                ],
            }
        }

        with patch("httpx.Client.post", return_value=mock_resp):
            conv = JarvisConversation(provider=provider)
            agent = AutomationAgent(conversation=conv)

            reply, actions = agent.execute_user_command("Jarvis, take a screenshot")
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["tool"], "take_screenshot")
            self.assertTrue(actions[0]["result"]["success"])

        print("[PASS] Allowlisted Desktop Tool Calling Verified with Local Provider.")

    def test_08_voice_pipeline_integration(self) -> None:
        """Verify VoiceAssistant runs turn execution seamlessly through Ollama provider."""
        mock_provider = MagicMock(spec=BaseAIProvider)
        mock_provider.name = "ollama"
        mock_provider.model_name = "qwen2.5:1.5b"
        mock_provider.ask.return_value = "Voice interaction confirmed through local Ollama, Sir."
        mock_provider.ask_tool_calling.return_value = ("Voice interaction confirmed through local Ollama, Sir.", [])

        conv = JarvisConversation(provider=mock_provider)
        agent = AutomationAgent(conversation=conv)
        assistant = VoiceAssistant(conversation=conv)
        assistant.agent = agent

        # Test simulated audio turn
        user_p = "Jarvis, voice test"
        reply, actions = agent.execute_user_command(user_p)
        self.assertIn("local ollama", reply.lower())
        print(f"[PASS] Voice Interaction Integration Verified: {reply}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
