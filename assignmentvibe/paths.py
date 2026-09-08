"""
Speicherorte fuer Nutzerdaten, nach XDG Base Directory Spec (Standard unter
Linux/Omarchy). Unter Windows/macOS gibt es keine XDG-Env-Vars, dann greifen
die Defaults (~/.local/share etc.) - funktioniert dort zwar auch, ist aber
nicht die dortige Konvention. Das ist bewusst so: das Tool ist fuer Linux
(Omarchy) gebaut, Windows/macOS sind nur "es startet wenigstens nicht ab".
"""

import os
from pathlib import Path


def _xdg(env_var: str, default: str) -> Path:
    value = os.environ.get(env_var)
    return Path(value).expanduser() if value else Path(default).expanduser()


DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share") / "assignmentvibe"
STATE_DIR = _xdg("XDG_STATE_HOME", "~/.local/state") / "assignmentvibe"
CACHE_DIR = _xdg("XDG_CACHE_HOME", "~/.cache") / "assignmentvibe"

KNOWLEDGE_DIR = DATA_DIR / "knowledge"
ASSIGNMENTS_DIR = DATA_DIR / "assignments"
RAW_TEXT_CACHE_DIR = CACHE_DIR / "raw_text"
COURSES_FILE = DATA_DIR / "courses.json"
CONTEXT_FILE = STATE_DIR / "context.json"
LAST_PROMPT_FILE = STATE_DIR / "last_prompt.txt"


def ensure_dirs() -> None:
    for d in (KNOWLEDGE_DIR, ASSIGNMENTS_DIR, RAW_TEXT_CACHE_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
