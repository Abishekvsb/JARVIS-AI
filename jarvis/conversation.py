"""Multi-turn Conversation Manager for JARVIS powered by Anthropic Claude.

Maintains multi-turn context, enforces system prompt instructions,
and handles streaming and non-streaming interactions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Generator, List, Optional

import anthropic
from anthropic import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

from jarvis.config import JarvisConfig, get_config
from jarvis.providers.base import BaseAIProvider
from jarvis.providers.factory import get_ai_provider
from jarvis.system_prompt import get_system_prompt

logger = logging.getLogger(__name__)


@dataclass
class ChatTurn:
    """A single turn in the conversation."""

    role: str
    content: str


class JarvisConversation:
    """Manages an ongoing multi-turn dialogue with JARVIS AI (Ollama Local or Anthropic)."""

    def __init__(
        self,
        config: Optional[JarvisConfig] = None,
        system_prompt: Optional[str] = None,
        provider: Optional[BaseAIProvider] = None,
        max_history_turns: int = 40,
    ) -> None:
        self.config = config or get_config()
        self.system_prompt = system_prompt or get_system_prompt()
        self.max_history_turns = max_history_turns
        self.history: List[ChatTurn] = []

        # Connect AI provider (Default is Local Ollama)
        self.provider: BaseAIProvider = provider or get_ai_provider(self.config)

        if self.provider.name == "anthropic" and not self.config.is_api_key_valid:
            raise ValueError(
                "Anthropic API key is not configured or invalid in D:/JARVIS/.env. "
                "Please add a valid key to ANTHROPIC_API_KEY or set AI_PROVIDER=ollama."
            )

    @property
    def client(self):
        return getattr(self.provider, "_client", None)

    @client.setter
    def client(self, value):
        if hasattr(self.provider, "_client"):
            self.provider._client = value

    @property
    def model(self) -> str:
        return self.provider.model_name

    def _build_anthropic_messages(self) -> List[dict]:
        """Convert internal history into message format."""
        recent = self.history[-self.max_history_turns :]
        messages = []
        for turn in recent:
            messages.append({"role": turn.role, "content": turn.content})
        return messages

    def ask(self, user_message: str, max_tokens: int = 2048) -> str:
        """Send a message to the AI provider and return the complete response.

        Maintains conversation history automatically.
        """
        user_message_clean = user_message.strip()
        if not user_message_clean:
            return ""

        # Append user turn
        self.history.append(ChatTurn(role="user", content=user_message_clean))

        recent_history = [
            {"role": t.role, "content": t.content}
            for t in self.history[-self.max_history_turns : -1]
        ]

        try:
            reply_text = self.provider.ask(
                user_message=user_message_clean,
                system_prompt=self.system_prompt,
                history=recent_history,
                max_tokens=max_tokens,
            )

            # Append assistant turn
            self.history.append(ChatTurn(role="assistant", content=reply_text))
            return reply_text

        except Exception as e:
            # Pop the user message on failure so history remains consistent
            if self.history and self.history[-1].role == "user":
                self.history.pop()

            # Format user-friendly errors
            err_msg = str(e)
            if "credit balance is too low" in err_msg.lower():
                raise RuntimeError(
                    "Anthropic API Error: Your credit balance is too low ($0.00). "
                    "Please add prepaid credits at https://console.anthropic.com/settings/billing, "
                    "or switch to local AI with AI_PROVIDER=ollama."
                )
            raise e

    def ask_stream(
        self, user_message: str, max_tokens: int = 2048
    ) -> Generator[str, None, None]:
        """Stream response tokens in real-time while updating conversation history."""
        user_message_clean = user_message.strip()
        if not user_message_clean:
            return

        self.history.append(ChatTurn(role="user", content=user_message_clean))
        full_reply = []

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=self.system_prompt,
                messages=self._build_anthropic_messages(),
            ) as stream:
                for text in stream.text_stream:
                    full_reply.append(text)
                    yield text

            # Append assistant turn after stream finishes
            reply_text = "".join(full_reply)
            self.history.append(ChatTurn(role="assistant", content=reply_text))

        except APIStatusError as e:
            if self.history and self.history[-1].role == "user":
                self.history.pop()
            err_msg = str(e)
            if "credit balance is too low" in err_msg.lower():
                raise RuntimeError(
                    "Anthropic API Error: Your credit balance is too low ($0.00). "
                    "Please add prepaid credits to your Anthropic Console account at "
                    "https://console.anthropic.com/settings/billing to enable Claude responses."
                )
            raise RuntimeError(f"Anthropic API returned status {e.status_code}: {e.message}")
        except Exception as e:
            if self.history and self.history[-1].role == "user":
                self.history.pop()
            raise e

    def clear_history(self) -> None:
        """Clear the conversation context history."""
        self.history.clear()

    def get_turn_count(self) -> int:
        """Return the number of turns currently in history."""
        return len(self.history)
