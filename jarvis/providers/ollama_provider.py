"""Local Ollama AI Provider for JARVIS.

Connects to the locally running Ollama AI runtime (http://127.0.0.1:11434).
Zero paid cloud dependencies. Fully offline after model weights are landed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from jarvis.providers.base import BaseAIProvider

logger = logging.getLogger(__name__)


class LocalOllamaProvider(BaseAIProvider):
    """Local intelligence provider powered by Ollama."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:1.5b",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model.strip()
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def check_health(self) -> Tuple[bool, str]:
        """Verify Ollama service is reachable and the configured model is installed."""
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return False, f"Ollama HTTP {resp.status_code}: {resp.text}"

                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]

                # Check if model or variant is installed
                model_base = self._model.split(":")[0]
                installed = any(self._model in m or (model_base in m and "latest" in m) for m in models)
                if not installed:
                    return False, (
                        f"Ollama is running, but model '{self._model}' is not installed yet. "
                        f"Installed models: {models or 'None'}. "
                        f"Download it with: ollama pull {self._model}"
                    )

                return True, f"Ollama local runtime online. Active model: '{self._model}'."

        except httpx.ConnectError:
            return False, (
                f"Ollama is not running on {self._base_url}. "
                "Please start the Ollama daemon (e.g. 'ollama serve')."
            )
        except Exception as e:
            return False, f"Ollama health check failed: {e}"

    def list_installed_models(self) -> List[str]:
        """Retrieve list of all locally installed models."""
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                if resp.status_code == 200:
                    return [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception as e:
            logger.debug(f"Failed to query installed models: {e}")
        return []

    def _convert_tools_to_ollama_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools into the standard OpenAI/Ollama function calling schema."""
        ollama_tools = []
        for t in tools:
            # If already in OpenAI format
            if "function" in t and "type" in t:
                ollama_tools.append(t)
                continue

            # Convert from Anthropic schema {"name": ..., "description": ..., "input_schema": ...}
            name = t.get("name", "")
            desc = t.get("description", "")
            params = t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}}

            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": params,
                },
            })
        return ollama_tools

    def ask(
        self,
        user_message: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Send a conversational prompt to the local Ollama model."""
        clean_msg = user_message.strip()
        if not clean_msg:
            return ""

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({"role": "user", "content": clean_msg})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            },
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/api/chat", json=payload)

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama API returned HTTP {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            message_obj = data.get("message", {})
            reply = message_obj.get("content", "").strip()

            if not reply:
                raise ValueError("Ollama returned an empty response.")

            return reply

        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to local Ollama runtime at {self._base_url}. "
                "Ensure Ollama is started with 'ollama serve'."
            )
        except httpx.TimeoutException:
            raise TimeoutError(
                f"Ollama request timed out after {self._timeout} seconds."
            )

    def ask_tool_calling(
        self,
        user_message: str,
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2048,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute a prompt with allowlisted tools via Ollama.

        Returns (reply_text, list_of_tool_calls).
        """
        clean_msg = user_message.strip()
        if not clean_msg:
            return "", []

        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({"role": "user", "content": clean_msg})

        ollama_tools = self._convert_tools_to_ollama_format(tools)

        payload = {
            "model": self._model,
            "messages": messages,
            "tools": ollama_tools,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.2,  # Lower temperature for deterministic tool calling
            },
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/api/chat", json=payload)

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama API returned HTTP {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            msg = data.get("message", {})
            reply_text = msg.get("content", "").strip()
            tool_calls_raw = msg.get("tool_calls", [])

            tool_calls: List[Dict[str, Any]] = []
            for tc in tool_calls_raw:
                fn = tc.get("function", {})
                t_name = fn.get("name", "")
                t_args = fn.get("arguments", {})
                if isinstance(t_args, str):
                    try:
                        t_args = json.loads(t_args)
                    except Exception:
                        t_args = {}
                if t_name:
                    tool_calls.append({
                        "name": t_name,
                        "input": t_args,
                        "id": tc.get("id", f"call_{len(tool_calls)+1}"),
                    })

            # Structured JSON parsing fallback if model outputted tool call in plain text
            if not tool_calls and "{" in reply_text and "}" in reply_text:
                json_match = re.search(r"```(?:json)?\s*({[\s\S]*?})\s*```", reply_text)
                target_str = json_match.group(1) if json_match else None
                if not target_str and reply_text.startswith("{") and reply_text.endswith("}"):
                    target_str = reply_text

                if target_str:
                    try:
                        parsed = json.loads(target_str)
                        if "name" in parsed or "tool" in parsed:
                            t_name = parsed.get("name") or parsed.get("tool")
                            t_args = parsed.get("parameters") or parsed.get("input") or {}
                            tool_calls.append({"name": t_name, "input": t_args, "id": "call_fallback"})
                    except Exception:
                        pass

            return reply_text, tool_calls

        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to local Ollama runtime at {self._base_url}. "
                "Ensure Ollama is started with 'ollama serve'."
            )
        except httpx.TimeoutException:
            raise TimeoutError(
                f"Ollama tool request timed out after {self._timeout} seconds."
            )

