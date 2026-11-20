"""Voice Interaction Controller for JARVIS.

Connects Microphone Audio -> Faster-Whisper (STT) -> Claude AI Conversation
-> Edge-TTS Neural Voice -> Speaker Output in a clean push-to-talk conversational loop.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional, Tuple

from rich.console import Console
from rich.panel import Panel

from jarvis.config import JarvisConfig, get_config
from jarvis.conversation import JarvisConversation
from jarvis.voice.audio_io import play_audio, record_until_silence
from jarvis.voice.stt import JarvisSTT
from jarvis.voice.tts import JarvisTTS, detect_language_mode

logger = logging.getLogger(__name__)
console = Console()


class VoiceAssistant:
    """Manages the full voice interaction loop for JARVIS."""

    def __init__(
        self,
        conversation: Optional[JarvisConversation] = None,
        config: Optional[JarvisConfig] = None,
        stt_model_size: str = "base",
    ) -> None:
        self.config = config or get_config()
        # Connect to existing Claude AI conversation engine
        self.conv = conversation or JarvisConversation(config=self.config)
        self.stt = JarvisSTT(model_size=stt_model_size)
        self.tts = JarvisTTS()
        # Connect Desktop Automation Agent
        from jarvis.automation.agent import AutomationAgent
        self.agent = AutomationAgent(conversation=self.conv, config=self.config)

    def process_turn(
        self,
        audio_path: str | Path,
        speak_output: bool = True,
    ) -> Tuple[str, str, str]:
        """Process a single turn from an audio file: STT -> Automation Agent -> TTS.

        Returns (transcribed_prompt, reply_text, detected_language).
        """
        # 1. Speech to Text
        transcribed_text, lang, prob = self.stt.transcribe(audio_path)
        if not transcribed_text.strip():
            raise ValueError("No distinct speech detected in audio recording.")

        # 2. Automation Agent Execution (Tools + Claude AI)
        reply_text, actions = self.agent.execute_user_command(transcribed_text)

        # 3. Text to Speech
        if speak_output and reply_text.strip():
            self.tts.speak(reply_text)

        return transcribed_text, reply_text, lang

    def run_interactive_voice_loop(self) -> None:
        """Run the push-to-talk interactive voice assistant in the console."""
        console.print(
            Panel.fit(
                "[bold cyan]JARVIS VOICE INTERACTION ENGINE (PHASE 4)[/bold cyan]\n"
                "• Mode: [green]Push-to-Talk[/green] (Press [bold white]Enter[/bold white] to Speak)\n"
                "• STT: [yellow]Faster-Whisper (Base Multilingual)[/yellow]\n"
                "• Intelligence: [yellow]Claude AI (3.5 Sonnet)[/yellow]\n"
                "• TTS: [yellow]Neural Voice (English JARVIS / Tamil / Tanglish)[/yellow]\n"
                "• Language: [cyan]Auto-detects English, Tamil, and Tanglish[/cyan]\n"
                "• Controls: [bold]Enter[/bold] = Speak | [bold]t[/bold] = Type | [bold]q[/bold] = Quit",
                title="[bold green]Voice Assistant Online[/bold green]",
                border_style="cyan",
            )
        )

        while True:
            try:
                cmd = console.input(
                    "\n[bold cyan]Voice Control[/bold cyan] [dim]([Enter]=Speak, [t]=Type, [q]=Quit)[/dim]: "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[bold yellow]JARVIS: Voice interface disengaged. Goodbye, Sir.[/bold yellow]")
                break

            if cmd in ("q", "quit", "exit"):
                console.print("[bold yellow]JARVIS: Voice mode deactivated. Goodbye, Sir.[/bold yellow]")
                break

            user_text = ""
            if cmd == "t":
                user_text = console.input("[bold green]You (Type) > [/bold green]").strip()
                if not user_text:
                    continue
            else:
                # Push-to-talk recording
                console.print("[bold red]● Listening...[/bold red] [dim](Speak into your microphone now)[/dim]")
                try:
                    audio_file = record_until_silence(
                        max_seconds=15.0,
                        silence_seconds=1.5,
                        silence_threshold=400,
                        startup_silence_seconds=4.0,
                    )
                except RuntimeError as e:
                    console.print(f"[bold red]Microphone Error:[/bold red] {e}")
                    console.print("[yellow]Tip: You can use 't' to type commands if your microphone is unavailable.[/yellow]")
                    continue

                console.print("[cyan]⏳ Transcribing speech...[/cyan]")
                try:
                    user_text, detected_lang, prob = self.stt.transcribe(audio_file)
                except Exception as e:
                    console.print(f"[bold red]Speech Recognition Error:[/bold red] {e}")
                    continue

                if not user_text.strip():
                    console.print("[yellow]JARVIS: I didn't detect any clear speech. Please try speaking again.[/yellow]")
                    continue

                console.print(f"[bold green]You (Spoken [{detected_lang.upper()}]) > [/bold green] {user_text}")

            # Send to Claude AI & Desktop Automation Agent
            console.print("[cyan]⏳ Processing with JARVIS Engine...[/cyan]")
            try:
                reply, actions = self.agent.execute_user_command(user_text)
                if actions:
                    for act in actions:
                        tool_name = act.get("tool", "Action")
                        tool_msg = act.get("result", {}).get("message", "Completed")
                        console.print(f"[bold green]✓ Action Executed:[/bold green] [yellow]{tool_name}[/yellow] — {tool_msg}")
            except RuntimeError as e:
                console.print(f"[bold red]Service Error:[/bold red] {e}")
                continue
            except Exception as e:
                console.print(f"[bold red]Unexpected Error:[/bold red] {e}")
                continue

            lang_mode = detect_language_mode(reply)
            console.print(f"\n[bold cyan]JARVIS [{lang_mode.upper()}] > [/bold cyan]{reply}\n")

            # Speak aloud
            console.print("[dim]🔊 Speaking response aloud...[/dim]")
            try:
                self.tts.speak(reply)
            except Exception as e:
                console.print(f"[yellow]Speech output warning:[/yellow] Could not speak response: {e}")

