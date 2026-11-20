"""Interactive Command-Line Chat Interface for JARVIS.

Allows direct conversation with Claude AI in English, Tamil, and Tanglish
with real-time streaming and multi-turn context retention.
"""

from __future__ import annotations

import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from jarvis.config import get_config
from jarvis.conversation import JarvisConversation

console = Console()

BANNER = """
   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
   ██║███████║██████╔╝██║   ██║██║███████╗
██ ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
"""


def main() -> None:
    """Run the interactive JARVIS conversational session."""
    try:
        config = get_config()
    except Exception as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        sys.exit(1)

    if not config.is_api_key_valid:
        console.print(
            Panel.fit(
                "[bold red]Anthropic API Key is Missing or Invalid![/bold red]\n\n"
                "Please configure a valid key in [cyan]D:/JARVIS/.env[/cyan]:\n"
                "[yellow]ANTHROPIC_API_KEY=sk-ant-api03-...[/yellow]\n\n"
                "Never share or commit this key to Git.",
                title="[red]JARVIS Setup Error[/red]",
            )
        )
        sys.exit(1)

    try:
        conv = JarvisConversation(config=config)
        from jarvis.automation.agent import AutomationAgent
        agent = AutomationAgent(conversation=conv, config=config)
    except Exception as e:
        console.print(f"[bold red]Initialization Error:[/bold red] {e}")
        sys.exit(1)

    # Welcome Header
    console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    header_text = Text()
    header_text.append("PERSONAL AI ASSISTANT — PHASE 3 INTELLIGENCE LAYER\n", style="bold green")
    header_text.append(f"• Intelligence Engine: {config.model}\n", style="white")
    header_text.append("• Multilingual Modes: English | தமிழ் (Tamil) | Tanglish\n", style="white")
    header_text.append(f"• Credentials: API Key configured ({config.masked_api_key})\n", style="dim white")
    header_text.append("• Commands: /clear (reset memory), /status, /model, /help, /exit\n", style="yellow")
    console.print(Panel(header_text, title="[bold cyan]JARVIS Online[/bold cyan]", border_style="cyan"))

    console.print("[dim]Type your message in English, Tamil, or Tanglish. Press Enter to send.[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold cyan]You > [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold yellow]JARVIS: Standing by. Have a productive day, Sir.[/bold yellow]")
            break

        if not user_input:
            continue

        # Handle Commands
        cmd = user_input.lower()
        if cmd in ("/exit", "/quit", "exit", "quit"):
            console.print("\n[bold cyan]JARVIS:[/bold cyan] [italic]Powering down conversational interface. Goodbye, Sir.[/italic]")
            break

        if cmd == "/clear":
            conv.clear_history()
            console.print("[green]✓ Conversation history cleared. Starting fresh context.[/green]\n")
            continue

        if cmd == "/model":
            console.print(f"[cyan]Active Intelligence Model:[/cyan] [bold]{conv.model}[/bold]\n")
            continue

        if cmd == "/status":
            console.print(
                Panel.fit(
                    f"Model: {conv.model}\n"
                    f"Active History Turns: {conv.get_turn_count()}\n"
                    f"Credential Status: Configured ({config.masked_api_key})\n"
                    f"Security Mode: {config.security_mode.upper()}",
                    title="JARVIS Status",
                )
            )
            continue

        if cmd == "/help":
            console.print(
                "[yellow]Available Commands:[/yellow]\n"
                "  /clear   - Clears multi-turn conversation memory\n"
                "  /status  - Displays current model and history length\n"
                "  /model   - Shows currently configured Claude model\n"
                "  /exit    - Shuts down the chat session\n"
            )
            continue

        # Execute command through Automation Agent
        try:
            reply, actions = agent.execute_user_command(user_input)
            if actions:
                for act in actions:
                    tool_name = act.get("tool", "Action")
                    tool_msg = act.get("result", {}).get("message", "Completed")
                    console.print(f"[bold green]✓ Action Executed:[/bold green] [yellow]{tool_name}[/yellow] — {tool_msg}")
            console.print(f"[bold cyan]JARVIS > [/bold cyan]{reply}\n")
        except Exception as e:
            console.print(f"\n[bold red]Error executing request:[/bold red] {e}\n")


if __name__ == "__main__":
    main()

