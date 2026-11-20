"""Configuration module for JARVIS.

Loads environment variables securely from .env on Drive D:,
validates Claude AI settings, and prevents credential exposure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Base project paths
JARVIS_ROOT = Path("D:/JARVIS").resolve()
ENV_FILE = JARVIS_ROOT / ".env"
CACHE_DIR = JARVIS_ROOT / ".cache"

# Ensure environment directories exist on D:
for sub in ("uv", "pip", "temp", "huggingface", "ollama", "models"):
    (CACHE_DIR / sub).mkdir(parents=True, exist_ok=True)

# Point system caches to Drive D:
os.environ.setdefault("OPENJARVIS_HOME", str(JARVIS_ROOT))
os.environ.setdefault("UV_CACHE_DIR", str(CACHE_DIR / "uv"))
os.environ.setdefault("PIP_CACHE_DIR", str(CACHE_DIR / "pip"))
os.environ.setdefault("TEMP", str(CACHE_DIR / "temp"))
os.environ.setdefault("TMP", str(CACHE_DIR / "temp"))
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("OLLAMA_MODELS", str(CACHE_DIR / "ollama"))

# Load .env if present
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=True)


# Currently supported Claude models
SUPPORTED_CLAUDE_MODELS = {
    "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet (Recommended - flag-bearer intelligence)",
    "claude-3-5-haiku-20241022": "Claude 3.5 Haiku (Fast & responsive)",
    "claude-3-opus-20240229": "Claude 3 Opus (Deep reasoning)",
    "claude-3-haiku-20240307": "Claude 3 Haiku (Legacy fast model)",
}

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


def mask_key(key: Optional[str]) -> str:
    """Safely mask an API key for diagnostics without revealing secrets.

    Returns e.g. 'sk-ant-***...4a2b' or '<NOT_SET>'.
    """
    if not key or not isinstance(key, str):
        return "<NOT_SET>"
    stripped = key.strip()
    if len(stripped) < 12:
        return "<CONFIGURED_TOO_SHORT>"
    prefix = stripped[:8]
    suffix = stripped[-4:]
    return f"{prefix}***...***{suffix}"


@dataclass(frozen=True)
class JarvisConfig:
    """Validated JARVIS configuration."""

    api_key: str
    model: str
    security_mode: str
    project_root: Path
    cache_root: Path

    @property
    def is_api_key_valid(self) -> bool:
        """Check if API key appears valid without exposing it."""
        if not self.api_key:
            return False
        k = self.api_key.strip()
        return k.startswith("sk-ant-") and len(k) > 25 and k != "your_anthropic_api_key_here"

    @property
    def masked_api_key(self) -> str:
        return mask_key(self.api_key)


def get_config() -> JarvisConfig:
    """Retrieve and validate the current JARVIS configuration."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL).strip()

    # Fallback to default if model is empty or unrecognized
    if model not in SUPPORTED_CLAUDE_MODELS:
        # Check if model string starts with claude-
        if not model.lower().startswith("claude-"):
            model = DEFAULT_MODEL

    security_mode = os.environ.get("JARVIS_SECURITY_MODE", "strict").strip().lower()

    return JarvisConfig(
        api_key=api_key,
        model=model,
        security_mode=security_mode,
        project_root=JARVIS_ROOT,
        cache_root=CACHE_DIR,
    )

