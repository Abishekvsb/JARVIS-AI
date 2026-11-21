"""Speech-to-Text (STT) Engine for JARVIS.

Powered by Faster-Whisper with multilingual support (English, Tamil, Tanglish).
All models and caches reside on Drive D:.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from jarvis.config import JARVIS_ROOT

logger = logging.getLogger(__name__)

# Suppress HuggingFace symlink warning on Windows non-admin
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

HF_CACHE_DIR = JARVIS_ROOT / ".cache" / "huggingface"
HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_INITIAL_PROMPT = (
    "JARVIS personal AI assistant. English, Tamil, and Tanglish conversations. "
    "Commands: WhatsApp, open WhatsApp, send WhatsApp message, message anupu, "
    "screenshot eduthu, volume increase pannu, open notepad, Chrome, YouTube, "
    "Vanakkam Sir, epdi irukkinga, innaiku enna plan, enakku enna work irukku."
)


class JarvisSTT:
    """Multilingual Speech-to-Text transcriber using Faster-Whisper."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        initial_prompt: str = DEFAULT_INITIAL_PROMPT,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.initial_prompt = initial_prompt
        self._model = None

    def _ensure_model(self):
        """Lazy load the Whisper model on first use."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise RuntimeError(
                    "faster-whisper is not installed. Please run: pip install faster-whisper"
                )

            logger.info(f"Loading Faster-Whisper ({self.model_size}) from {HF_CACHE_DIR}...")
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(HF_CACHE_DIR),
            )
        return self._model

    def transcribe(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        beam_size: int = 5,
        initial_prompt: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        """Transcribe an audio file into text.

        Returns (transcribed_text, detected_language, probability).
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        model = self._ensure_model()
        prompt_hint = initial_prompt if initial_prompt is not None else self.initial_prompt

        try:
            segments, info = model.transcribe(
                str(path),
                language=language,
                beam_size=beam_size,
                initial_prompt=prompt_hint,
                vad_filter=True,  # Filter out background noise & silence
            )

            texts = [segment.text.strip() for segment in segments]
            full_text = " ".join(texts).strip()

            return full_text, info.language, info.language_probability

        except Exception as e:
            logger.error(f"Speech transcription error: {e}")
            raise RuntimeError(f"Speech recognition failed: {e}")

