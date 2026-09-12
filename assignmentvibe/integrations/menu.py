"""
Pick one entry from a list - fallback chain across different pickers:

  omarchy-menu-select   (Omarchy's own convention, uses the Walker launcher,
                          options passed as arguments)
  -> rofi -dmenu         (widely used, also usable via a Wayland fork)
  -> wofi --dmenu         (GTK-based, common on Hyprland setups)
  -> fzf                  (terminal fuzzy-finder, for terminal use)
  -> numbered stdin prompt (guaranteed to work everywhere, even without a
                             graphical session - this is the only path that
                             is truly end-to-end testable in this sandbox,
                             without Wayland/X11)

Important: the GUI pickers (omarchy-menu-select/rofi/wofi) have NOT been
tested live in a real Hyprland session here (see docs/LINUX_PROTOTYPE.md) -
only the stdin fallback has. That's exactly why the fallback chain is built
this way: the tool stays usable even if a picker is missing or behaves
differently than assumed.

No dependency on any other module in this project.
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
    # input() reads fine from a pipe too (EOF -> EOFError, caught below) -
    # no hang risk with closed/empty stdin (e.g. /dev/null). The only
    # theoretical hang risk is an OPEN stdin that never delivers data/EOF
    # (e.g. a process manager attaching stdin to some other, permanently
    # open program) - irrelevant on real Omarchy systems, since Walker
    # (omarchy-menu-select) is tried first there and this fallback is never
    # reached. See docs/LINUX_PROTOTYPE.md for the risk assessment.
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
    # Also allow typing the option text directly (substring match)
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
