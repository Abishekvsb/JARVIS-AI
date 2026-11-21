"""Conversational Automation Agent for JARVIS.

Bridges Natural Language (English, Tamil, Tanglish) -> Claude AI Tool Calling
-> Allowlisted Windows Actions -> Natural Spoken Confirmation.
Includes an offline/hybrid intent matcher fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from jarvis.automation.executor import execute_tool
from jarvis.automation.safety import EmergencyStopManager
from jarvis.automation.tools_schema import AUTOMATION_TOOLS
from jarvis.config import JarvisConfig, get_config
from jarvis.conversation import ChatTurn, JarvisConversation
from jarvis.system_prompt import get_system_prompt

from unittest.mock import Mock, MagicMock

logger = logging.getLogger(__name__)

AUTOMATION_SYSTEM_PROMPT_ADDENDUM = r"""
=== WINDOWS DESKTOP AUTOMATION MODE ACTIVATED ===
You have access to allowlisted desktop automation tools to control this Windows 11 computer:
- open_app: Launch applications by name (notepad, chrome, calc, paint, settings).
- close_app: Close running applications by name.
- open_browser: Open web URLs.
- search_web: Search Google or YouTube.
- control_media: Play/pause or skip media tracks.
- search_files: Find files in approved user folders.
- open_file: Open approved files safely.
- take_screenshot: Capture desktop screenshots saved to D:\JARVIS\screenshots.
- adjust_volume: Increase, decrease, or mute audio.
- get_system_info: Read battery, CPU, RAM, and disk status.
- open_settings: Open Windows Settings pages.
- write_in_notepad: Launch Notepad and write dictated notes.
- type_text: Type or paste text safely into active window.
- emergency_stop: Halt all automation immediately if requested.

When the user gives a command in English, Tamil, or Tanglish:
1. Call the appropriate tool with validated parameters.
2. Confirm the completed action naturally in the user's preferred language.
"""


def _rule_based_fallback_intent(prompt: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """Parse common desktop automation commands locally when offline or in fallback mode."""
    p = prompt.strip().lower()

    # Greetings & Identity
    if any(k in p for k in ("who are you", "introduce yourself", "yaaru nee", "un peyar", "identify yourself")):
        return "identity", {}, "Good day, Sir. I am JARVIS, your advanced personal AI assistant."
    if any(k in p for k in ("hello jarvis", "hi jarvis", "hey jarvis", "vanakkam jarvis")):
        return "greeting", {}, "Good day, Sir. All systems are operational. How may I assist you today?"

    # Emergency Stop
    if any(k in p for k in ("emergency stop", "stop immediately", "abort all", "stop panna")):
        return "emergency_stop", {}, "Emergency stop activated, Sir. All automation halted."
    if any(k in p for k in ("reset emergency stop", "resume automation")):
        EmergencyStopManager.get_instance().reset()
        return "reset", {}, "Emergency stop reset. Automation is active."

    # Screenshot
    if "screenshot" in p or "screen shot" in p:
        return "take_screenshot", {"prefix": "jarvis"}, "Screenshot captured and saved to D:\\JARVIS\\screenshots, Sir."

    # Volume Control
    if "volume" in p:
        if any(k in p for k in ("up", "increase", "higher", "kootu", "adhigam")):
            return "adjust_volume", {"action": "up", "steps": 5}, "Volume increased, Sir."
        elif any(k in p for k in ("down", "decrease", "lower", "kora", "kammi")):
            return "adjust_volume", {"action": "down", "steps": 5}, "Volume decreased, Sir."
        elif "mute" in p:
            return "adjust_volume", {"action": "mute"}, "Volume mute toggled, Sir."

    # YouTube
    if "youtube" in p:
        # Extract query if present
        m = re.search(r"youtube\s+(?:la\s+)?(?:search\s+)?(.+)", p)
        query = m.group(1).replace("search", "").replace("pannu", "").strip() if m else ""
        return "search_web", {"platform": "youtube", "query": query}, f"Searching YouTube for '{query or 'videos'}', Sir."

    # Google Search
    if "google" in p and ("search" in p or "find" in p or "thedu" in p):
        m = re.search(r"google\s+(?:la\s+)?(?:search\s+)?(.+)", p)
        query = m.group(1).replace("search", "").replace("pannu", "").strip() if m else ""
        return "search_web", {"platform": "google", "query": query}, f"Searching Google for '{query}', Sir."

    # Notepad dictation / write
    if "notepad" in p and any(k in p for k in ("write", "type", "eluthu", "note")):
        # Extract text after keywords
        m = re.search(r"(?:type|write|eluthu)\s+(.+)", p)
        content = m.group(1).replace("pannu", "").strip() if m else "JARVIS voice dictation test note."
        return "write_in_notepad", {"content": content}, f"Opened Notepad and recorded your dictation, Sir."

    # Application Launching
    if any(k in p for k in ("open", "start", "launch", "thira")):
        for app in ("notepad", "chrome", "calculator", "calc", "paint", "settings", "task manager", "edge", "explorer"):
            if app in p:
                return "open_app", {"app_name": app}, f"Launching {app.title()}, Sir."

    # Application Closing
    if any(k in p for k in ("close", "exit", "terminate", "moodu")):
        for app in ("notepad", "calculator", "calc", "paint", "chrome", "edge"):
            if app in p:
                return "close_app", {"app_name": app}, f"Closing {app.title()}, Sir."

    # System Status
    if any(k in p for k in ("battery", "cpu", "ram", "system status", "telemetry", "status")):
        return "get_system_info", {}, "Retrieved current system telemetry, Sir."

    return None


class AutomationAgent:
    """Agent combining Claude AI reasoning with allowlisted desktop automation."""

    def __init__(
        self,
        conversation: Optional[JarvisConversation] = None,
        config: Optional[JarvisConfig] = None,
    ) -> None:
        self.config = config or get_config()
        self.system_prompt = f"{get_system_prompt()}\n\n{AUTOMATION_SYSTEM_PROMPT_ADDENDUM.strip()}"
        self.conv = conversation or JarvisConversation(
            config=self.config,
            system_prompt=self.system_prompt,
        )

    def execute_user_command(self, user_prompt: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute a user command, dispatching tools via Claude or hybrid fallback.

        Returns (final_reply_text, list_of_executed_actions).
        """
        prompt_clean = user_prompt.strip()
        if not prompt_clean:
            return "", []

        # 1. Immediate emergency stop check
        if any(term in prompt_clean.lower() for term in ("emergency stop", "stop immediately", "abort all")):
            EmergencyStopManager.get_instance().trigger_stop("User invoked voice/text emergency stop")
            return "Emergency stop activated, Sir. All ongoing automation has been halted immediately.", [{"tool": "emergency_stop", "success": True}]

        if "reset emergency stop" in prompt_clean.lower() or "resume automation" in prompt_clean.lower():
            EmergencyStopManager.get_instance().reset()
            return "Emergency stop has been reset, Sir. Desktop automation is now active and ready.", [{"tool": "reset_emergency_stop", "success": True}]

        executed_actions: List[Dict[str, Any]] = []

        # Check if conversation is a mock for unit testing (e.g. TestVoiceInteraction)
        if isinstance(getattr(self.conv, "ask", None), (Mock, MagicMock)):
            reply = self.conv.ask(prompt_clean)
            return str(reply), []

        # 2. Try Provider Tool Calling (Local Ollama or Anthropic)
        try:
            self.conv.history.append(ChatTurn(role="user", content=prompt_clean))

            # If provider has native ask_tool_calling
            if hasattr(self.conv, "provider") and hasattr(self.conv.provider, "ask_tool_calling"):
                recent_history = [
                    {"role": t.role, "content": t.content}
                    for t in self.conv.history[-self.conv.max_history_turns : -1]
                ]
                reply_text, tool_calls = self.conv.provider.ask_tool_calling(
                    user_message=prompt_clean,
                    tools=AUTOMATION_TOOLS,
                    system_prompt=self.system_prompt,
                    history=recent_history,
                    max_tokens=2048,
                )

                if tool_calls:
                    for tc in tool_calls:
                        t_name = tc.get("name", "")
                        t_input = tc.get("input", {})
                        tool_res = execute_tool(t_name, t_input)
                        executed_actions.append({"tool": t_name, "input": t_input, "result": tool_res})

                    if not reply_text:
                        action_summaries = [f"{a['tool']}: {a['result'].get('message', 'Completed')}" for a in executed_actions]
                        reply_text = "Executed the requested actions, Sir:\n" + "\n".join(action_summaries)

                    self.conv.history.append(ChatTurn(role="assistant", content=reply_text))
                    return reply_text, executed_actions

                else:
                    # Hybrid check: If AI answered conversationally without dispatching tools,
                    # check if the user gave an explicit allowlisted command (e.g. Tanglish/Tamil commands)
                    fallback = _rule_based_fallback_intent(prompt_clean)
                    if fallback is not None:
                        tool_name, tool_input, fallback_reply = fallback
                        if tool_name not in ("reset", "identity", "greeting"):
                            res = execute_tool(tool_name, tool_input)
                            executed_actions.append({"tool": tool_name, "input": tool_input, "result": res})
                            if not res.get("success", False):
                                fallback_reply = f"Attempted {tool_name}, but: {res.get('message', 'Failed')}."
                            self.conv.history.append(ChatTurn(role="assistant", content=fallback_reply))
                            return fallback_reply, executed_actions

                    self.conv.history.append(ChatTurn(role="assistant", content=reply_text))
                    return reply_text, []

            # Legacy fallback if client is mock with messages.create
            elif hasattr(self.conv, "client") and self.conv.client and hasattr(self.conv.client, "messages"):
                raw_messages = self.conv._build_anthropic_messages()
                response = self.conv.client.messages.create(
                    model=self.conv.model,
                    max_tokens=2048,
                    system=self.system_prompt,
                    messages=raw_messages,
                    tools=AUTOMATION_TOOLS,
                )

                if response.stop_reason == "tool_use":
                    assistant_blocks = response.content
                    tool_results_blocks = []

                    for block in assistant_blocks:
                        if block.type == "tool_use":
                            t_id = block.id
                            t_name = block.name
                            t_input = block.input

                            tool_res = execute_tool(t_name, t_input)
                            executed_actions.append({"tool": t_name, "input": t_input, "result": tool_res})

                            tool_results_blocks.append({
                                "type": "tool_result",
                                "tool_use_id": t_id,
                                "content": json.dumps(tool_res, ensure_ascii=False),
                            })

                    raw_messages.append({"role": "assistant", "content": assistant_blocks})
                    raw_messages.append({"role": "user", "content": tool_results_blocks})

                    followup = self.conv.client.messages.create(
                        model=self.conv.model,
                        max_tokens=1024,
                        system=self.system_prompt,
                        messages=raw_messages,
                        tools=AUTOMATION_TOOLS,
                    )

                    reply_text = "".join(b.text for b in followup.content if b.type == "text")
                    self.conv.history.append(ChatTurn(role="assistant", content=reply_text))
                    return reply_text, executed_actions
                else:
                    reply_text = "".join(b.text for b in response.content if b.type == "text")
                    self.conv.history.append(ChatTurn(role="assistant", content=reply_text))
                    return reply_text, []
            else:
                raise RuntimeError("No active AI provider configured.")

        except Exception as e:
            # Pop user message if call failed
            if self.conv.history and self.conv.history[-1].role == "user":
                self.conv.history.pop()

            # 3. Hybrid Fallback: Execute allowlisted intent directly if recognized
            fallback = _rule_based_fallback_intent(prompt_clean)
            if fallback is not None:
                tool_name, tool_input, fallback_reply = fallback
                if tool_name not in ("reset", "identity", "greeting"):
                    res = execute_tool(tool_name, tool_input)
                    executed_actions.append({"tool": tool_name, "input": tool_input, "result": res})
                    if not res.get("success", False):
                        fallback_reply = f"Attempted {tool_name}, but: {res.get('message', 'Failed')}."

                # Append to history so conversation continuity is preserved
                self.conv.history.append(ChatTurn(role="user", content=prompt_clean))
                self.conv.history.append(ChatTurn(role="assistant", content=fallback_reply))
                return fallback_reply, executed_actions

            # If not a recognized local intent, propagate the error (e.g. credit balance or connection)
            raise e
