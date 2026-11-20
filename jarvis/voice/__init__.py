"""JARVIS Voice Interaction Subsystem.

Provides microphone input, faster-whisper STT, Claude AI bridge,
and Edge-TTS neural voice synthesis in English, Tamil, and Tanglish.
"""

from jarvis.voice.audio_io import get_default_devices, play_audio, record_audio, record_until_silence
from jarvis.voice.stt import JarvisSTT
from jarvis.voice.tts import JarvisTTS, clean_markdown_for_tts, detect_language_mode
from jarvis.voice.voice_loop import VoiceAssistant

__all__ = [
    "JarvisSTT",
    "JarvisTTS",
    "VoiceAssistant",
    "clean_markdown_for_tts",
    "detect_language_mode",
    "get_default_devices",
    "play_audio",
    "record_audio",
    "record_until_silence",
]

