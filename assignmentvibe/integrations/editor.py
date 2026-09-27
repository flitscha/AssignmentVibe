"""
Open a file in the user's editor, in its own window, with a fallback chain:
omarchy-launch-config-editor (Omarchy's default editor, in a terminal for nvim
and friends, plus a toast saying which file) -> xdg-terminal-exec with $EDITOR
or nvim -> nothing, and the caller shows the path instead.

Detached: the menu that asked for it closes right after, and the editor must
outlive it.

No dependency on any other module in this project.
"""

import os
import shutil
import subprocess


def _candidates(path: str) -> list[list[str]]:
    cands = []
    if shutil.which("omarchy-launch-config-editor"):
        cands.append(["omarchy-launch-config-editor", path])
    if shutil.which("xdg-terminal-exec"):
        editor = os.environ.get("EDITOR") or "nvim"
        # $EDITOR may carry arguments ("omarchy-launch-editor --inline").
        cands.append(["xdg-terminal-exec", *editor.split(), path])
    return cands


def open_file(path) -> bool:
    """True if an editor was started."""
    for cmd in _candidates(str(path)):
        try:
            subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return False
