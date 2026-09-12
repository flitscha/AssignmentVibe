"""
Copy text to the system clipboard, with a fallback chain. Why a chain
instead of one fixed tool: Wayland (Hyprland/Omarchy) needs wl-copy, X11
needs xclip/xsel, macOS pbcopy, Windows clip - and even on Omarchy
wl-clipboard might occasionally be missing. If everything fails, the prompt
is written to a file so nothing gets lost.

Depends only on assignmentvibe.paths (for the fallback file location) - no
dependency on any other integration module.
"""

import os
import platform
import shutil
import subprocess

from .. import paths


def _candidates() -> list[list[str]]:
    system = platform.system()
    if system == "Linux":
        cands = []
        if os.environ.get("WAYLAND_DISPLAY"):
            cands.append(["wl-copy"])
        cands.append(["xclip", "-selection", "clipboard"])
        cands.append(["xsel", "--clipboard", "--input"])
        if not os.environ.get("WAYLAND_DISPLAY"):
            cands.append(["wl-copy"])  # try anyway as a last resort
        return cands
    if system == "Darwin":
        return [["pbcopy"]]
    if system == "Windows":
        return [["clip"]]
    return []


def copy(text: str) -> tuple[bool, str]:
    """Returns (success, method_or_fallback_path)."""
    for cmd in _candidates():
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)
            return True, cmd[0]
        except Exception:
            continue

    paths.ensure_dirs()
    paths.LAST_PROMPT_FILE.write_text(text, encoding="utf-8")
    return False, str(paths.LAST_PROMPT_FILE)


def paste() -> str | None:
    """Read the current clipboard contents, if possible (used by `pick` to
    let the user reuse whatever they already copied as their partial
    solution)."""
    for cmd in (["wl-paste"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard"]):
        if shutil.which(cmd[0]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                continue
    return None
