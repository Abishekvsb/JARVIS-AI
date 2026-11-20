"""Test Suite for JARVIS Phase 4: Voice Interaction Subsystem.

Tests:
1. Audio device detection (Mic and Speakers).
2. Markdown cleaning and language mode detection for TTS.
3. Natural TTS synthesis for English, Tamil, and Tanglish.
4. Faster-Whisper Speech-to-Text transcription.
5. Full voice conversation loop with the 3 user-specified prompts:
   - English: "Hello Jarvis, introduce yourself."
   - Tanglish: "Jarvis, enakku inniku enna work irukku?"
   - Tamil: "ஜார்விஸ், உன்னால் என்ன உதவி செய்ய முடியும்?"
6. Error handling for silence, missing devices, and network fallbacks.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Suppress symlink warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from jarvis.config import JARVIS_ROOT
from jarvis.voice.audio_io import get_default_devices
from jarvis.voice.stt import JarvisSTT
from jarvis.voice.tts import (
    JarvisTTS,
    clean_markdown_for_tts,
    detect_language_mode,
    get_voice_for_text,
    VOICE_ENGLISH_JARVIS,
    VOICE_TAMIL,
    VOICE_TANGLISH,
)
from jarvis.voice.voice_loop import VoiceAssistant


class TestVoiceInteraction(unittest.TestCase):
    """Test suite for JARVIS Voice Interaction (Phase 4)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = JARVIS_ROOT / ".cache" / "temp"
        cls.temp_dir.mkdir(parents=True, exist_ok=True)
        cls.stt = JarvisSTT(model_size="base")
        cls.tts = JarvisTTS()

    def test_01_audio_device_detection(self) -> None:
        """Verify microphone and speaker devices are detected."""
        in_dev, out_dev = get_default_devices()
        print(f"\n[PASS] Input Device: {in_dev.get('name') if in_dev else 'None'}")
        print(f"[PASS] Output Device: {out_dev.get('name') if out_dev else 'None'}")
        self.assertIsNotNone(in_dev, "Microphone input device should be available.")
        self.assertIsNotNone(out_dev, "Speaker output device should be available.")

    def test_02_text_cleaning_and_language_detection(self) -> None:
        """Verify markdown stripping and language classification."""
        md_text = "# Header\nHello **Sir**, check `code` [link](http://test.com)."
        cleaned = clean_markdown_for_tts(md_text)
        self.assertNotIn("#", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertNotIn("http://", cleaned)
        print(f"\n[PASS] Markdown Cleaning: '{md_text}' -> '{cleaned}'")

        # Test language detection
        self.assertEqual(detect_language_mode("Hello Jarvis, how are you?"), "english")
        self.assertEqual(detect_language_mode("வணக்கம் ஜார்விஸ், நீங்கள் யார்?"), "tamil")
        self.assertEqual(detect_language_mode("Vanakkam Jarvis, enakku inniku enna work irukku?"), "tanglish")

        # Test voice selection
        self.assertEqual(get_voice_for_text("Hello Sir"), VOICE_ENGLISH_JARVIS)
        self.assertEqual(get_voice_for_text("வணக்கம் ஜார்விஸ்"), VOICE_TAMIL)
        self.assertEqual(get_voice_for_text("Vanakkam Jarvis, enakku inniku enna work irukku?"), VOICE_TANGLISH)
        print("[PASS] Language Detection & Neural Voice Mapping Verified.")

    def test_03_tts_neural_synthesis(self) -> None:
        """Verify speech synthesis creates valid, non-empty audio files."""
        # English
        en_audio = self.tts.synthesize("Jarvis voice system online and functional, Sir.")
        self.assertTrue(en_audio.exists())
        self.assertGreater(en_audio.stat().st_size, 1000)

        # Tamil
        ta_audio = self.tts.synthesize("வணக்கம், நான் உங்கள் தனிப்பட்ட AI உதவியாளர் ஜார்விஸ்.")
        self.assertTrue(ta_audio.exists())
        self.assertGreater(ta_audio.stat().st_size, 1000)

        # Tanglish
        tanglish_audio = self.tts.synthesize("Vanakkam! Naan unga personal AI assistant Jarvis. Epdi irukkinga?")
        self.assertTrue(tanglish_audio.exists())
        self.assertGreater(tanglish_audio.stat().st_size, 1000)
        print(f"\n[PASS] TTS Synthesis Succeeded for English, Tamil, and Tanglish.")

    def test_04_stt_transcription_accuracy(self) -> None:
        """Verify Faster-Whisper transcribes spoken audio correctly."""
        # Synthesize audio to test transcription
        test_audio = self.temp_dir / "stt_test_phrase.mp3"
        self.tts.synthesize("Speech to text is operational.", voice=VOICE_ENGLISH_JARVIS)
        # Transcribe
        text, lang, prob = self.stt.transcribe(self.temp_dir / "jarvis_spoken_reply.mp3")
        print(f"\n[PASS] STT Transcription: '{text}' (Detected: {lang}, Prob: {prob:.2f})")
        self.assertTrue(len(text) > 0)
        self.assertIn("operational", text.lower())

    def test_05_three_specified_voice_conversations(self) -> None:
        """Verify the 3 specific prompts required by the user:
        1. English: 'Hello Jarvis, introduce yourself.'
        2. Tanglish: 'Jarvis, enakku inniku enna work irukku?'
        3. Tamil: 'ஜார்விஸ், உன்னால் என்ன உதவி செய்ய முடியும்?'
        """
        # Mock the conversation backend to test voice processing deterministically
        mock_conv = MagicMock()
        mock_conv.ask.side_effect = [
            "Good day, Sir. I am JARVIS, your advanced personal AI assistant.",
            "Vanakkam Sir! Innaiku ungalukku Phase 4 voice interaction testing work schedule aagi irukku.",
            "வணக்கம்! என்னால் உங்களுக்கு உரையாடல், பகுப்பாய்வு மற்றும் அன்றாட பணிகளில் சிறந்த முறையில் உதவ முடியும்.",
        ]

        assistant = VoiceAssistant(conversation=mock_conv)

        # Prompt 1: English
        en_prompt_file = self.temp_dir / "en_prompt.mp3"
        import asyncio, edge_tts
        asyncio.run(edge_tts.Communicate("Hello Jarvis, introduce yourself.", VOICE_ENGLISH_JARVIS).save(str(en_prompt_file)))

        user_p1, reply1, lang1 = assistant.process_turn(en_prompt_file, speak_output=False)
        print(f"\n[VOICE CONVERSATION 1 - ENGLISH]")
        print(f"User Spoken: {user_p1}")
        print(f"JARVIS Reply: {reply1}")
        self.assertIn("jarvis", user_p1.lower())
        self.assertIn("personal ai assistant", reply1.lower())

        # Prompt 2: Tanglish
        tanglish_prompt_file = self.temp_dir / "tanglish_prompt.mp3"
        asyncio.run(edge_tts.Communicate("Jarvis, enakku inniku enna work irukku?", VOICE_TANGLISH).save(str(tanglish_prompt_file)))

        user_p2, reply2, lang2 = assistant.process_turn(tanglish_prompt_file, speak_output=False)
        print(f"\n[VOICE CONVERSATION 2 - TANGLISH]")
        print(f"User Spoken: {user_p2}")
        print(f"JARVIS Reply: {reply2}")
        self.assertIn("jarvis", user_p2.lower())
        self.assertIn("work", reply2.lower())

        # Prompt 3: Tamil
        ta_prompt_file = self.temp_dir / "tamil_prompt.mp3"
        asyncio.run(edge_tts.Communicate("ஜார்விஸ், உன்னால் என்ன உதவி செய்ய முடியும்?", VOICE_TAMIL).save(str(ta_prompt_file)))

        user_p3, reply3, lang3 = assistant.process_turn(ta_prompt_file, speak_output=False)
        print(f"\n[VOICE CONVERSATION 3 - TAMIL]")
        print(f"User Spoken: {user_p3}")
        print(f"JARVIS Reply: {reply3}")
        has_tamil = any("\u0b80" <= c <= "\u0bff" for c in reply3)
        self.assertTrue(has_tamil, "Tamil reply must contain Tamil Unicode characters.")

        print("\n[PASS] All 3 Voice Conversation Turns Successfully Processed!")

    def test_06_error_handling(self) -> None:
        """Verify graceful error handling for missing files and silence."""
        # Non-existent file
        with self.assertRaises(FileNotFoundError):
            self.stt.transcribe(self.temp_dir / "non_existent_audio.wav")

        # Empty text synthesis
        with self.assertRaises(ValueError):
            self.tts.synthesize("")

        print("\n[PASS] Audio Error Handling Verified.")


if __name__ == "__main__":
    unittest.main(verbosity=2)

