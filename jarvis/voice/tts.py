"""Text-to-Speech (TTS) Engine for JARVIS.

Supports Microsoft Edge Neural Voices for natural speech:
- English: en-GB-RyanNeural (Classic articulate JARVIS voice)
- Tamil (தமிழ்): ta-IN-ValluvarNeural
- Tanglish: en-IN-PrabhatNeural / ta-IN-ValluvarNeural
- Offline Fallback: Windows SAPI System.Speech.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from jarvis.config import JARVIS_ROOT
from jarvis.voice.audio_io import play_audio

logger = logging.getLogger(__name__)

TEMP_DIR = JARVIS_ROOT / ".cache" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Neural Voice Profiles
VOICE_ENGLISH_JARVIS = "en-GB-RyanNeural"
VOICE_TAMIL = "ta-IN-ValluvarNeural"
VOICE_TANGLISH = "en-IN-PrabhatNeural"

TANGLISH_KEYWORDS = {
    "vanakkam", "ungala", "enna", "irukku", "epdi", "nalla", "pandren",
    "theriyum", "solleenga", "romba", "innaiku", "paathutu", "kandippa",
    "panna", "mudiyum", "pannunga", "puriyala", "aachu", "illai", "irukken"
}


def clean_markdown_for_tts(text: str) -> str:
    """Strip markdown formatting, URLs, and code blocks for spoken output."""
    if not text:
        return ""
    # Remove code blocks
    cleaned = re.sub(r"```[\s\S]*?```", " Code snippet omitted. ", text)
    # Remove inline code
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Remove markdown links [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Remove headers (#)
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    # Remove bold/italic (* or _)
    cleaned = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", cleaned)
    # Remove bullet points and numbers
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)
    # Remove excessive newlines
    cleaned = re.sub(r"\n+", ". ", cleaned)
    return cleaned.strip()


def detect_language_mode(text: str) -> str:
    """Detect whether text is Tamil script, Tanglish, or English.

    Returns: 'tamil' | 'tanglish' | 'english'.
    """
    # Check for Tamil Unicode characters (U+0B80 to U+0BFF)
    if any("\u0b80" <= c <= "\u0bff" for c in text):
        return "tamil"

    # Check for Tanglish keywords
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    tanglish_matches = sum(1 for w in words if w in TANGLISH_KEYWORDS)
    if tanglish_matches >= 2 or (len(words) > 0 and (tanglish_matches / len(words)) >= 0.2):
        return "tanglish"

    return "english"


def get_voice_for_text(text: str) -> str:
    """Select the optimal neural voice for the text content."""
    mode = detect_language_mode(text)
    if mode == "tamil":
        return VOICE_TAMIL
    elif mode == "tanglish":
        return VOICE_TANGLISH
    else:
        return VOICE_ENGLISH_JARVIS


class JarvisTTS:
    """High-fidelity text-to-speech engine with offline SAPI fallback."""

    def __init__(self, default_voice: str = VOICE_ENGLISH_JARVIS) -> None:
        self.default_voice = default_voice

    async def _generate_edge_tts(self, text: str, voice: str, output_path: Path) -> Path:
        """Synthesize speech using Microsoft Edge Neural TTS."""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return output_path

    def _fallback_sapi_speak(self, text: str) -> None:
        """Fallback to Windows built-in SAPI speech synthesizer when offline."""
        logger.warning("Using Windows SAPI SpeechSynthesizer offline fallback.")
        escaped = text.replace("'", "''").replace('"', '`"')
        ps_cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$synth.Speak('{escaped}')"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True, timeout=30)
        except Exception as e:
            logger.error(f"Windows SAPI fallback failed: {e}")

    def synthesize(self, text: str, voice: Optional[str] = None) -> Path:
        """Synthesize text to an MP3 audio file.

        Returns the path to the generated audio file.
        """
        cleaned_text = clean_markdown_for_tts(text)
        if not cleaned_text:
            raise ValueError("No speakable text provided.")

        selected_voice = voice or get_voice_for_text(cleaned_text)
        output_file = TEMP_DIR / "jarvis_spoken_reply.mp3"

        try:
            asyncio.run(self._generate_edge_tts(cleaned_text, selected_voice, output_file))
            return output_file
        except Exception as e:
            logger.warning(f"Edge-TTS synthesis error: {e}. Attempting fallback.")
            raise RuntimeError(f"Edge-TTS failed: {e}")

    def speak(self, text: str, voice: Optional[str] = None) -> None:
        """Synthesize text and play it aloud through the default output speakers."""
        cleaned_text = clean_markdown_for_tts(text)
        if not cleaned_text:
            return

        try:
            audio_path = self.synthesize(cleaned_text, voice=voice)
            play_audio(audio_path)
        except Exception as e:
            logger.warning(f"Audio playback via Edge-TTS failed: {e}. Switching to Windows offline SAPI.")
            self._fallback_sapi_speak(cleaned_text)

