"""
User data locations, following the XDG Base Directory spec (standard on
Linux/Omarchy). On Windows/macOS there are no XDG env vars, so the defaults
(~/.local/share etc.) apply - that works there too, but isn't the local
convention. That's intentional: this tool is built for Linux (Omarchy);
Windows/macOS just need to "at least not crash".
"""

import os
from pathlib import Path


def _xdg(env_var: str, default: str) -> Path:
    value = os.environ.get(env_var)
    return Path(value).expanduser() if value else Path(default).expanduser()


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", "~/.config") / "assignmentvibe"
DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share") / "assignmentvibe"
STATE_DIR = _xdg("XDG_STATE_HOME", "~/.local/state") / "assignmentvibe"
CACHE_DIR = _xdg("XDG_CACHE_HOME", "~/.cache") / "assignmentvibe"

KNOWLEDGE_DIR = DATA_DIR / "knowledge"
ASSIGNMENTS_DIR = DATA_DIR / "assignments"
RAW_TEXT_CACHE_DIR = CACHE_DIR / "raw_text"
COURSES_FILE = DATA_DIR / "courses.json"

# The one file the user edits, once per semester. See assignmentvibe/uniconfig.py.
CONFIG_FILE = CONFIG_DIR / "uni.json"

# Generated .desktop entries land here, which is what Walker (Super+Space) reads.
APPLICATIONS_DIR = _xdg("XDG_DATA_HOME", "~/.local/share") / "applications"
CONTEXT_FILE = STATE_DIR / "context.json"
LAST_PROMPT_FILE = STATE_DIR / "last_prompt.txt"

# Default target for the downloads organizer (assignmentvibe/organizer/) -
# deliberately a normal, user-visible location (not the hidden XDG data dir
# above), since these are the user's own PDFs they'll want to browse/back up
# normally. Overridable via --target on the `organize` command.
DEFAULT_LIBRARY_DIR = Path("~/Documents/AssignmentVibe").expanduser()


def ensure_dirs() -> None:
    for d in (KNOWLEDGE_DIR, ASSIGNMENTS_DIR, RAW_TEXT_CACHE_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
