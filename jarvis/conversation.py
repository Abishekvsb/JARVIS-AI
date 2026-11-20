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
from jarvis.system_prompt import get_system_prompt

logger = logging.getLogger(__name__)


@dataclass
class ChatTurn:
    """A single turn in the conversation."""

    role: str
    content: str


class JarvisConversation:
    """Manages an ongoing multi-turn dialogue with Claude AI."""

    def __init__(
        self,
        config: Optional[JarvisConfig] = None,
        system_prompt: Optional[str] = None,
        max_history_turns: int = 40,
    ) -> None:
        self.config = config or get_config()
        self.system_prompt = system_prompt or get_system_prompt()
        self.max_history_turns = max_history_turns
        self.history: List[ChatTurn] = []

        if not self.config.is_api_key_valid:
            raise ValueError(
                "Anthropic API key is not configured or invalid in D:/JARVIS/.env. "
                "Please add a valid key to ANTHROPIC_API_KEY."
            )

        # Initialize the official Anthropic client
        self.client = anthropic.Anthropic(api_key=self.config.api_key)

    @property
    def model(self) -> str:
        return self.config.model

    def _build_anthropic_messages(self) -> List[dict]:
        """Convert internal history into Anthropic API format."""
        # Enforce turn limit to manage context window
        recent = self.history[-self.max_history_turns :]
        messages = []
        for turn in recent:
            messages.append({"role": turn.role, "content": turn.content})
        return messages

    def ask(self, user_message: str, max_tokens: int = 2048) -> str:
        """Send a message to Claude and return the complete response.

        Maintains conversation history automatically.
        """
        user_message_clean = user_message.strip()
        if not user_message_clean:
            return ""

        # Append user turn
        self.history.append(ChatTurn(role="user", content=user_message_clean))

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=self.system_prompt,
                messages=self._build_anthropic_messages(),
            )

            # Extract text response
            reply_text = ""
            for block in response.content:
                if block.type == "text":
                    reply_text += block.text

            # Append assistant turn
            self.history.append(ChatTurn(role="assistant", content=reply_text))
            return reply_text

        except AuthenticationError:
            # Pop the user message so state remains consistent
            if self.history and self.history[-1].role == "user":
                self.history.pop()
            raise RuntimeError(
                "Authentication failed: The provided ANTHROPIC_API_KEY is invalid or unauthorized. "
                "Please verify your key in D:/JARVIS/.env."
            )
        except RateLimitError:
            if self.history and self.history[-1].role == "user":
                self.history.pop()
            raise RuntimeError("Anthropic rate limit reached. Please wait a moment before trying again.")
        except APIConnectionError as e:
            if self.history and self.history[-1].role == "user":
                self.history.pop()
            raise RuntimeError(f"Could not connect to Anthropic API servers. Check internet connection: {e}")
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
