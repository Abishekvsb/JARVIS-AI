"""AI Provider Factory for JARVIS.

Selects and instantiates the configured AI provider.
Default provider is LocalOllamaProvider.
"""

from __future__ import annotations

import logging
from typing import Optional

from jarvis.config import JarvisConfig, get_config
from jarvis.providers.anthropic_provider import AnthropicClaudeProvider
from jarvis.providers.base import BaseAIProvider
from jarvis.providers.ollama_provider import LocalOllamaProvider

logger = logging.getLogger(__name__)


def get_ai_provider(config: Optional[JarvisConfig] = None) -> BaseAIProvider:
    """Retrieve the configured AI provider instance.

    Default is Ollama (Local AI).
    Does NOT silently fall back to paid cloud APIs.
    """
    cfg = config or get_config()
    provider_name = getattr(cfg, "ai_provider", "ollama").strip().lower()

    if provider_name == "anthropic":
        logger.info(f"Using Anthropic Claude AI provider with model '{cfg.model}'.")
        return AnthropicClaudeProvider(api_key=cfg.api_key, model=cfg.model)

    # Default to Local Ollama
    base_url = getattr(cfg, "ollama_base_url", "http://127.0.0.1:11434")
    model = getattr(cfg, "ollama_model", "qwen2.5:1.5b")
    logger.info(f"Using Local Ollama AI provider at '{base_url}' with model '{model}'.")
    return LocalOllamaProvider(base_url=base_url, model=model)

