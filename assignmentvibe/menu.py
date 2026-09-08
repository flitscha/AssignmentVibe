"""
Ein Eintrag aus einer Liste auswaehlen - Fallback-Kette ueber verschiedene
Picker:

  omarchy-menu-select   (Omarchy-eigene Konvention, nutzt den Walker-Launcher,
                          Optionen als Argumente)
  -> rofi -dmenu         (weit verbreitet, auch mit Wayland-Fork nutzbar)
  -> wofi --dmenu         (GTK-basiert, oft auf Hyprland-Setups)
  -> fzf                  (Terminal-Fuzzyfinder, falls man's im Terminal nutzt)
  -> nummerierte stdin-Eingabe (funktioniert garantiert ueberall, auch ohne
                                 grafische Oberflaeche - das ist der einzige
                                 Pfad, der in dieser Sandbox ohne Wayland/X11
                                 wirklich end-to-end testbar ist)

Wichtig: die GUI-Picker (omarchy-menu-select/rofi/wofi) sind hier nicht *live*
in einer echten Hyprland-Session getestet worden (siehe docs/LINUX_PROTOTYPE.md),
nur der stdin-Fallback ist es. Das Fallback-Design ist genau deshalb so
aufgebaut: das Tool bleibt benutzbar, falls ein Picker fehlt oder sich anders
verhaelt als erwartet.
"""

import shutil
import subprocess
import sys


def _try_omarchy(prompt: str, options: list[str]) -> str | None:
    if not shutil.which("omarchy-menu-select"):
        return None
    try:
        result = subprocess.run(
            ["omarchy-menu-select", prompt, *options],
            capture_output=True, text=True, timeout=120,
        )
        choice = result.stdout.strip()
        return choice or None
    except Exception:
        return None


def _try_dmenu_style(cmd: list[str], prompt: str, options: list[str]) -> str | None:
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        result = subprocess.run(
            cmd, input="\n".join(options), capture_output=True, text=True, timeout=120,
        )
        choice = result.stdout.strip()
        return choice or None
    except Exception:
        return None


def _stdin_fallback(prompt: str, options: list[str]) -> str | None:
    # input() liest problemlos auch aus einer Pipe (EOF -> EOFError, sofort
    # abgefangen unten) - kein Hang-Risiko bei geschlossenem/leerem stdin
    # (z.B. /dev/null). Das einzige theoretische Hang-Risiko ist ein OFFENES
    # stdin ohne jemals Daten/EOF zu liefern (z.B. wenn ein Prozessmanager
    # stdin an ein anderes, dauerhaft offenes Programm haengt) - auf echten
    # Omarchy-Systemen ist das irrelevant, da dort Walker (omarchy-menu-select)
    # als erstes greift und dieser Fallback nie erreicht wird. Siehe
    # docs/LINUX_PROTOTYPE.md fuer die Einordnung dieses Risikos.
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    try:
        raw = input(f"{prompt} [1-{len(options)}]: ").strip()
    except EOFError:
        return None
    if not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    # Auch direkte Texteingabe erlauben (Teilstring-Match)
    matches = [o for o in options if raw.lower() in o.lower()]
    return matches[0] if len(matches) == 1 else None


def any_picker_available() -> bool:
    return bool(
        shutil.which("omarchy-menu-select")
        or shutil.which("rofi")
        or shutil.which("wofi")
        or shutil.which("fzf")
        or sys.stdin.isatty()
    )


def pick(prompt: str, options: list[str], allow_stdin_fallback: bool = True) -> str | None:
    if not options:
        return None

    choice = _try_omarchy(prompt, options)
    if choice:
        return choice

    choice = _try_dmenu_style(["rofi", "-dmenu", "-p", prompt], prompt, options)
    if choice:
        return choice

    choice = _try_dmenu_style(["wofi", "--dmenu", "-p", prompt], prompt, options)
    if choice:
        return choice

    choice = _try_dmenu_style(["fzf", "--prompt", f"{prompt}> "], prompt, options)
    if choice:
        return choice

    if allow_stdin_fallback:
        return _stdin_fallback(prompt, options)
    return None
