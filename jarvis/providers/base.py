"""Base AI Provider Interface for JARVIS.

Defines the contract for all local and cloud AI providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseAIProvider(ABC):
    """Abstract base class for all JARVIS intelligence providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'ollama', 'anthropic')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the active model."""
        pass

    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        """Check if provider service is available and ready.

        Returns (is_healthy, status_message).
        """
        pass

    @abstractmethod
    def ask(
        self,
        user_message: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Send a conversational prompt and receive the full assistant text reply."""
        pass

    @abstractmethod
    def ask_tool_calling(
        self,
        user_message: str,
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2048,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Process a user prompt with allowlisted tools.

        Returns (assistant_reply_text, list_of_tool_calls).
        Each tool call is a dict: {"name": str, "input": dict, "id": str}.
        """
        pass

