"""Speech-to-Text (STT) Engine for JARVIS.

Powered by Faster-Whisper with multilingual support (English, Tamil, Tanglish).
All models and caches reside on Drive D:.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from jarvis.config import JARVIS_ROOT

logger = logging.getLogger(__name__)

# Suppress HuggingFace symlink warning on Windows non-admin
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

HF_CACHE_DIR = JARVIS_ROOT / ".cache" / "huggingface"
HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_INITIAL_PROMPT = (
    "JARVIS personal AI assistant. English, Tamil, and Tanglish mixed conversations. "
    "WhatsApp la yaar message pannirukanga? Arun enna message anupirukan? "
    "Avanukku good morning sollu. Good morning message send pannava? Yes, send. "
    "WhatsApp open pannu, check notifications, message anupu, volume increase pannu, "
    "open notepad, take screenshot, search YouTube, Vanakkam Sir, epdi irukkinga."
)


def normalize_code_switching_phonetics(text: str) -> str:
    """Normalize common acoustic distortions in code-switching Tanglish/Tamil/English."""
    t = text
    # WhatsApp distortions
    t = re.sub(r"\b(?:what['\s]?s?\s*app|watsapp|watsup|வாட்ஸ்அப்|water sap|what sap|whatsup)\b", "WhatsApp", t, flags=re.IGNORECASE)
    # Pronouns
    t = re.sub(r"\b(?:avanukku|avanuku|avanuk)\b", "avanukku", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:avalukku|avaluku)\b", "avalukku", t, flags=re.IGNORECASE)
    # Action verbs
    t = re.sub(r"\b(?:anuppu|anupu|anupunga)\b", "anupu", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:pannu|panu|panunga)\b", "pannu", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:sollu|solu|solunga)\b", "sollu", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:thira|thura|open pannu)\b", "open pannu", t, flags=re.IGNORECASE)
    return t


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
            normalized_text = normalize_code_switching_phonetics(full_text)

            return normalized_text, info.language, info.language_probability

        except Exception as e:
            logger.error(f"Speech transcription error: {e}")
            raise RuntimeError(f"Speech recognition failed: {e}")

