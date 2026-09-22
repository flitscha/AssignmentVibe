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

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# Wide enough for a section title next to its counts - "3.1 Konvexe Funktionen
# und deren Minima  (17, 3k)" is about 60 characters, and the hub's rows carry
# an indent on top of that. The menu's own default cut them in half.
MENU_WIDTH = 900

# How often to look for the menu's answer. omarchy-menu-select polls at 50ms,
# which is a fifth of a second of dead time on a bad draw, and it is dead time
# the user sees: the menu has already closed by then and the next one is not up.
POLL_SECONDS = 0.005
MENU_TIMEOUT = 180


def _ipc(call: list[str]) -> bool:
    """One IPC call into the running shell. `qs ipc` is what omarchy-shell ends
    up running anyway, and going straight to it skips its bash and a `timeout`
    fork - about 10ms, on a path that runs once per menu window. The wrapper
    stays as the fallback, since it also knows how to find the Wayland socket
    when WAYLAND_DISPLAY is not set."""
    omarchy = os.environ.get("OMARCHY_PATH")
    if omarchy and shutil.which("qs"):
        try:
            done = subprocess.run(["qs", "ipc", "-n", "-p", f"{omarchy}/shell",
                                   "call", "--", *call],
                                  capture_output=True, text=True, timeout=10)
            if done.returncode == 0:
                return True
        except Exception:
            pass

    if not shutil.which("omarchy-shell"):
        return False
    try:
        done = subprocess.run(["omarchy-shell", *call],
                              capture_output=True, text=True, timeout=10)
        return done.returncode == 0
    except Exception:
        return False


def _summon_menu(prompt: str, options: list[str]) -> str | None | bool:
    """Ask the running Omarchy shell for a menu, without the shell wrapper.

    omarchy-menu-select does exactly this, but spends ~90ms per window getting
    there: its own bash, two mktemps, and TWO perl interpreters loading JSON::PP
    just to build the payload. Python is already running and already has json,
    so the whole preamble collapses into the summon itself. That matters more
    than it sounds, because the hub is a sequence of menus - between any two,
    the old window is gone and the new one has not arrived, and every
    millisecond of that preamble is a millisecond of empty screen.

    Returns the choice, None when the user cancelled, or False when the shell
    could not be reached at all - which is the caller's cue to try the wrapper
    and the other pickers instead."""

    selection = Path(tempfile.mkdtemp(prefix="assignmentvibe-menu-"))
    selection_file = selection / "selection"
    done_file = selection / "done"
    try:
        selection_file.write_text("", encoding="utf-8")
        payload = json.dumps({
            "mode": "select",
            "prompt": prompt,
            "options": options,
            "selectionFile": str(selection_file),
            "doneFile": str(done_file),
            "width": MENU_WIDTH,
        }, ensure_ascii=False)

        if not _ipc(["shell", "summon", "omarchy.menu", payload]):
            return False

        deadline = time.monotonic() + MENU_TIMEOUT
        while not done_file.exists():
            if time.monotonic() > deadline:
                return None
            time.sleep(POLL_SECONDS)

        choice = selection_file.read_text(encoding="utf-8").strip()
        return choice or None
    except Exception:
        return False
    finally:
        shutil.rmtree(selection, ignore_errors=True)


def _try_omarchy(prompt: str, options: list[str]) -> str | None | bool:
    """False means "this picker is not available", so the caller keeps looking.
    None means the user cancelled, which must NOT fall through to another
    picker - pressing Escape should close the menu, not open the next one."""
    choice = _summon_menu(prompt, options)
    if choice is not False:
        return choice

    if not shutil.which("omarchy-menu-select"):
        return False
    try:
        result = subprocess.run(
            ["omarchy-menu-select", prompt, *options, "--", "--width", str(MENU_WIDTH)],
            capture_output=True, text=True, timeout=MENU_TIMEOUT,
        )
        return result.stdout.strip() or None
    except Exception:
        return False


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
    if choice is not False:
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
