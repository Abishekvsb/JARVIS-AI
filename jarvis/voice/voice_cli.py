"""CLI Entry point for JARVIS Voice Interaction Mode."""

from __future__ import annotations

import sys
from jarvis.voice.voice_loop import VoiceAssistant


def main() -> None:
    """Launch the JARVIS interactive voice assistant."""
    try:
        assistant = VoiceAssistant()
        assistant.run_interactive_voice_loop()
    except Exception as e:
        print(f"Error launching JARVIS voice mode: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

