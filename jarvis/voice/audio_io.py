"""Audio Input and Output Utilities for JARVIS.

Handles microphone recording (push-to-talk, silence detection)
and speaker playback using sounddevice and soundfile.
"""

from __future__ import annotations

import io
import logging
import struct
import tempfile
import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import sounddevice as sd
import soundfile as sf

from jarvis.config import JARVIS_ROOT

logger = logging.getLogger(__name__)

TEMP_DIR = JARVIS_ROOT / ".cache" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
BLOCK_SIZE = 1024


def get_default_devices() -> Tuple[Optional[dict], Optional[dict]]:
    """Return the default input and output device information."""
    try:
        devices = sd.query_devices()
        default_in_idx = sd.default.device[0]
        default_out_idx = sd.default.device[1]

        in_dev = devices[default_in_idx] if default_in_idx is not None and default_in_idx >= 0 else None
        out_dev = devices[default_out_idx] if default_out_idx is not None and default_out_idx >= 0 else None
        return in_dev, out_dev
    except Exception as e:
        logger.warning(f"Could not query audio devices: {e}")
        return None, None


def _calculate_rms(data: bytes) -> float:
    """Calculate the Root Mean Square (RMS) volume level of 16-bit PCM data."""
    count = len(data) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", data[: count * 2])
    return (sum(s * s for s in shorts) / count) ** 0.5


def record_audio(
    duration: float = 5.0,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> Path:
    """Record microphone audio for a fixed duration.

    Returns the path to the saved WAV file.
    """
    in_dev, _ = get_default_devices()
    if in_dev is None or in_dev.get("max_input_channels", 0) <= 0:
        raise RuntimeError("No working microphone input device detected on this system.")

    output_path = TEMP_DIR / "recorded_speech.wav"
    num_frames = int(duration * sample_rate)

    try:
        recording = sd.rec(
            num_frames,
            samplerate=sample_rate,
            channels=DEFAULT_CHANNELS,
            dtype="int16",
        )
        sd.wait()
    except Exception as e:
        raise RuntimeError(f"Microphone recording error: {e}")

    sf.write(str(output_path), recording, sample_rate)
    return output_path


def record_until_silence(
    max_seconds: float = 15.0,
    silence_seconds: float = 1.1,
    silence_threshold: int = 380,
    startup_silence_seconds: float = 4.0,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> Path:
    """Record from default microphone until speech ends or timeout occurs.

    Features dynamic ambient noise floor calibration and zero-clipping trailing trim.
    Returns the path to the saved WAV file.
    """
    in_dev, _ = get_default_devices()
    if in_dev is None or in_dev.get("max_input_channels", 0) <= 0:
        raise RuntimeError("No microphone input device detected. Please connect or enable your microphone.")

    chunks_per_sec = sample_rate / BLOCK_SIZE
    silence_chunks = int(silence_seconds * chunks_per_sec)
    startup_silence_chunks = int(startup_silence_seconds * chunks_per_sec)
    max_chunks = int(max_seconds * chunks_per_sec)

    frames: list[bytes] = []
    silence_count = 0
    has_spoken = False
    calibrated_threshold = silence_threshold
    ambient_samples: list[float] = []

    try:
        with sd.RawInputStream(
            samplerate=sample_rate,
            channels=DEFAULT_CHANNELS,
            dtype="int16",
            blocksize=BLOCK_SIZE,
        ) as stream:
            for i in range(max_chunks):
                raw, overflow = stream.read(BLOCK_SIZE)
                data = bytes(raw)
                frames.append(data)

                amplitude = _calculate_rms(data)

                # Calibrate noise floor in initial 6 blocks (~0.38s)
                if i < 6 and not has_spoken:
                    ambient_samples.append(amplitude)
                    if len(ambient_samples) == 6:
                        avg_ambient = sum(ambient_samples) / 6.0
                        calibrated_threshold = max(silence_threshold, int(avg_ambient * 1.6 + 160))
                        logger.debug(f"[AUDIO] Calibrated noise floor: {avg_ambient:.1f}, threshold: {calibrated_threshold}")

                if amplitude > calibrated_threshold:
                    has_spoken = True
                    silence_count = 0
                elif not has_spoken and len(frames) >= startup_silence_chunks:
                    # User did not speak within startup window
                    break
                elif has_spoken:
                    silence_count += 1
                    if silence_count >= silence_chunks:
                        # User stopped speaking; trim trailing silence to minimize latency
                        keep_chunks = max(1, len(frames) - int(silence_chunks * 0.7))
                        frames = frames[:keep_chunks]
                        break
    except Exception as e:
        raise RuntimeError(f"Microphone streaming error: {e}")

    if not frames:
        raise RuntimeError("No audio captured from microphone.")

    output_path = TEMP_DIR / "voice_prompt.wav"
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(DEFAULT_CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))

    return output_path


def play_audio(file_path: str | Path) -> None:
    """Play any WAV or MP3 audio file through the default speakers."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {p}")

    try:
        data, sr = sf.read(str(p), dtype="float32")
        sd.play(data, sr)
        sd.wait()
    except Exception as e:
        raise RuntimeError(f"Audio playback error: {e}")

