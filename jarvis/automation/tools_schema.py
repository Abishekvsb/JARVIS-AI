"""Anthropic Function Calling Tool Definitions for JARVIS Desktop Automation.

Exposes allowlisted Windows actions to Claude AI with strict JSON schemas.
"""

from __future__ import annotations

AUTOMATION_TOOLS = [
    {
        "name": "open_app",
        "description": "Opens an installed Windows application by name (e.g., 'notepad', 'chrome', 'calculator', 'settings', 'paint').",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name or common alias of the application to launch (e.g., 'chrome', 'notepad').",
                }
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "close_app",
        "description": "Closes a running application by name. Protected system processes cannot be closed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the application to close (e.g., 'notepad', 'calc').",
                }
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "open_browser",
        "description": "Opens a web URL in the default web browser.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Web address to navigate to (e.g., 'https://github.com').",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "search_web",
        "description": "Performs a web search on Google or YouTube.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search keywords or query.",
                },
                "platform": {
                    "type": "string",
                    "enum": ["google", "youtube"],
                    "description": "Search platform ('google' or 'youtube'). Defaults to 'google'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "control_media",
        "description": "Controls active media playback (play/pause toggle, skip next, previous track).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play_pause", "next", "prev"],
                    "description": "Media command: 'play_pause', 'next', or 'prev'.",
                }
            },
            "required": ["action"],
        },
    },
    {
        "name": "search_files",
        "description": "Searches for files in approved user directories (Documents, Downloads, Desktop, Pictures, Videos, D:\JARVIS).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Filename, keyword, or extension to search for (e.g., 'project', '.pdf').",
                },
                "category": {
                    "type": "string",
                    "enum": ["all", "documents", "images", "videos", "audio"],
                    "description": "Filter by file category. Defaults to 'all'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "open_file",
        "description": "Opens a specific file found in approved directories using its default Windows application.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Full absolute path to the file to open.",
                }
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Captures a full-screen desktop screenshot and saves it to D:\JARVIS\screenshots.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prefix": {
                    "type": "string",
                    "description": "Optional filename prefix for the screenshot.",
                }
            },
        },
    },
    {
        "name": "adjust_volume",
        "description": "Increases, decreases, or mutes the system audio volume.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["up", "down", "mute"],
                    "description": "'up' to increase, 'down' to decrease, or 'mute' to toggle mute.",
                },
                "steps": {
                    "type": "integer",
                    "description": "Number of volume step increments (default: 5).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "get_system_info",
        "description": "Queries CPU utilization, RAM usage, battery percentage, and disk free space.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "open_settings",
        "description": "Opens a specific Windows Settings page (e.g., 'display', 'sound', 'wifi', 'bluetooth', 'battery').",
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": "Settings section: 'display', 'sound', 'wifi', 'bluetooth', 'battery', etc.",
                }
            },
            "required": ["page"],
        },
    },
    {
        "name": "type_text",
        "description": "Types or pastes text into the currently active window safely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to type or paste.",
                },
                "press_enter": {
                    "type": "boolean",
                    "description": "Whether to press Enter after typing. Defaults to false.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "write_in_notepad",
        "description": "Launches Notepad and writes dictated content into the new document.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The dictated text or notes to write into Notepad.",
                }
            },
            "required": ["content"],
        },
    },
    {
        "name": "emergency_stop",
        "description": "Immediately halts all automation and disengages active control.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason for stopping.",
                }
            },
        },
    },
]

