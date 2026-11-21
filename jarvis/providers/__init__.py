"""JARVIS AI Providers Package.

Supports Local Ollama (default) and Optional Anthropic Claude.
"""

from jarvis.providers.anthropic_provider import AnthropicClaudeProvider
from jarvis.providers.base import BaseAIProvider
from jarvis.providers.factory import get_ai_provider
from jarvis.providers.ollama_provider import LocalOllamaProvider

__all__ = [
    "BaseAIProvider",
    "LocalOllamaProvider",
    "AnthropicClaudeProvider",
    "get_ai_provider",
]

