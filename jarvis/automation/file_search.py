"""Sandboxed File Search and Inspection for JARVIS.

Searches only user-approved directories (Documents, Downloads, Desktop, D:\JARVIS)
and blocks access to sensitive system directories or credentials.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from jarvis.automation.safety import EmergencyStopManager
from jarvis.config import JARVIS_ROOT

logger = logging.getLogger(__name__)

# Approved directory roots for file search
APPROVED_ROOTS = [
    JARVIS_ROOT,
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Pictures",
    Path.home() / "Videos",
]

# Sensitive patterns that must NEVER be searched or returned
BLOCKED_PATH_PATTERNS = [
    "appdata",
    "windows",
    "system32",
    "program files",
    "local settings",
    ".ssh",
    ".aws",
    ".azure",
    ".git",
    ".venv",
    "credentials",
    "passwords",
    "token",
]

EXTENSIONS_BY_CATEGORY = {
    "documents": {".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".md", ".csv"},
    "images": {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"},
    "videos": {".mp4", ".mkv", ".avi", ".mov", ".webm"},
    "audio": {".mp3", ".wav", ".m4a", ".flac", ".aac"},
}


def _is_path_approved(path: Path) -> bool:
    """Verify that a path resides within approved directories and contains no blocked patterns."""
    try:
        resolved = path.resolve()
        # Check blocked patterns
        path_str = str(resolved).lower()
        for pattern in BLOCKED_PATH_PATTERNS:
            if pattern in path_str:
                return False

        # Check approved roots
        for root in APPROVED_ROOTS:
            if root.exists():
                try:
                    resolved.relative_to(root.resolve())
                    return True
                except ValueError:
                    continue
        return False
    except Exception:
        return False


def find_files(
    query: str,
    category: str = "all",
    max_results: int = 5,
    max_depth: int = 3,
) -> Tuple[bool, str, List[Dict[str, str]]]:
    """Search for files by name/extension within approved user directories.

    Returns (success, message, results_list).
    """
    EmergencyStopManager.get_instance().assert_can_proceed()

    q_clean = query.strip().lower()
    allowed_exts = EXTENSIONS_BY_CATEGORY.get(category.lower())

    results: List[Dict[str, str]] = []

    for root in APPROVED_ROOTS:
        if not root.exists() or len(results) >= max_results:
            continue

        try:
            for dirpath, dirnames, filenames in os.walk(root):
                current_dir = Path(dirpath)

                # Skip blocked directories
                dirnames[:] = [d for d in dirnames if not any(b in d.lower() for b in BLOCKED_PATH_PATTERNS)]

                # Enforce depth limit
                try:
                    depth = len(current_dir.relative_to(root).parts)
                    if depth > max_depth:
                        dirnames.clear()
                        continue
                except ValueError:
                    continue

                for fn in filenames:
                    p = current_dir / fn
                    if not _is_path_approved(p):
                        continue

                    # Filter by category extension if specified
                    if allowed_exts and p.suffix.lower() not in allowed_exts:
                        continue

                    # Match query against filename
                    if not q_clean or q_clean in fn.lower():
                        results.append({
                            "name": fn,
                            "path": str(p),
                            "size_kb": f"{p.stat().st_size / 1024:.1f}",
                        })
                        if len(results) >= max_results:
                            break
        except Exception as e:
            logger.warning(f"Error walking directory {root}: {e}")

    if not results:
        return True, f"No matching files found for '{query}' in approved directories.", []

    msg = f"Found {len(results)} matching file(s):"
    return True, msg, results


def open_file_safely(file_path: str) -> Tuple[bool, str]:
    """Open an existing file safely using Windows default application."""
    EmergencyStopManager.get_instance().assert_can_proceed()

    p = Path(file_path).resolve()
    if not p.exists():
        return False, f"File not found: {file_path}"

    if not _is_path_approved(p):
        return False, f"Security Warning: Access to '{file_path}' is restricted."

    try:
        os.startfile(str(p))
        return True, f"Successfully opened '{p.name}' from {p.parent}."
    except Exception as e:
        return False, f"Could not open file: {e}"

