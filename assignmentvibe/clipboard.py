"""
Zwischenablage kopieren, mit Fallback-Kette. Warum eine Kette statt eines
festen Tools: Wayland (Hyprland/Omarchy) braucht wl-copy, X11 braucht
xclip/xsel, macOS pbcopy, Windows clip - und selbst auf Omarchy kann
wl-clipboard mal fehlen. Schlaegt alles fehl, wird der Prompt in eine Datei
geschrieben, damit nichts verloren geht.
"""

import os
import platform
import shutil
import subprocess

from . import paths


def _candidates() -> list[list[str]]:
    system = platform.system()
    if system == "Linux":
        cands = []
        if os.environ.get("WAYLAND_DISPLAY"):
            cands.append(["wl-copy"])
        cands.append(["xclip", "-selection", "clipboard"])
        cands.append(["xsel", "--clipboard", "--input"])
        if not os.environ.get("WAYLAND_DISPLAY"):
            cands.append(["wl-copy"])  # notfalls trotzdem versuchen
        return cands
    if system == "Darwin":
        return [["pbcopy"]]
    if system == "Windows":
        return [["clip"]]
    return []


def copy(text: str) -> tuple[bool, str]:
    """Gibt (erfolg, methode_oder_fallback_pfad) zurueck."""
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
