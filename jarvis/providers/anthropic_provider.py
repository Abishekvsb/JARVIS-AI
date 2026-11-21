"""Anthropic Claude Cloud AI Provider for JARVIS (Optional Opt-In).

Wraps the Anthropic Claude API for users who explicitly configure AI_PROVIDER=anthropic.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from jarvis.providers.base import BaseAIProvider

logger = logging.getLogger(__name__)


class AnthropicClaudeProvider(BaseAIProvider):
    """Cloud AI provider powered by Anthropic Claude."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._client = anthropic.Anthropic(api_key=self._api_key) if self._api_key else None

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def check_health(self) -> Tuple[bool, str]:
        if not self._api_key or not self._api_key.startswith("sk-ant-"):
            return False, "Anthropic API key is missing or invalid format."
        return True, f"Anthropic provider configured with model '{self._model}'."

    def ask(
        self,
        user_message: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2048,
    ) -> str:
        if not self._client:
            raise RuntimeError("Anthropic API key is not configured.")

        clean_msg = user_message.strip()
        if not clean_msg:
            return ""

        messages: List[Dict[str, str]] = []
        if history:
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": clean_msg})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )

        reply = "".join(b.text for b in response.content if b.type == "text")
        return reply

    def ask_tool_calling(
        self,
        user_message: str,
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2048,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not self._client:
            raise RuntimeError("Anthropic API key is not configured.")

        clean_msg = user_message.strip()
        if not clean_msg:
            return "", []

        messages: List[Dict[str, Any]] = []
        if history:
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": clean_msg})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        reply_text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls: List[Dict[str, Any]] = []

        if response.stop_reason == "tool_use":
            for b in response.content:
                if b.type == "tool_use":
                    tool_calls.append({
                        "name": b.name,
                        "input": b.input,
                        "id": b.id,
                    })

        return reply_text, tool_calls

