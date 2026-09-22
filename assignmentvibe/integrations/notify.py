"""
Desktop notifications, with a fallback chain:
omarchy-notification-send (Omarchy convention, nice glyph+body formatting)
-> notify-send (standard on pretty much every Linux desktop)
-> print to stderr (guaranteed to work anywhere, including this sandbox
   without a notification daemon).

No dependency on any other module in this project.
"""

import shutil
import subprocess
import sys


# How long a notification stays up, in milliseconds. These say "copied" and
# "read in" - you have already seen the result by the time you would read them,
# so they should be gone before they are in the way.
TIMEOUT_MS = 2000


def send(headline: str, body: str = "", glyph: str = "\U000f0dc9") -> str:
    """Returns the channel that was used ('omarchy', 'notify-send', 'stderr')."""
    if shutil.which("omarchy-notification-send"):
        try:
            # The glyph is a -g OPTION, not a leading positional. Passing it as
            # one made the glyph the headline and the headline the body, and any
            # call WITH a body died on "Unknown option" and silently fell through
            # to notify-send below.
            cmd = ["omarchy-notification-send", "-g", glyph, "-t", str(TIMEOUT_MS),
                   headline]
            if body:
                cmd.append(body)
            subprocess.run(cmd, check=True, timeout=5)
            return "omarchy"
        except Exception:
            pass

    if shutil.which("notify-send"):
        try:
            args = ["notify-send", "-t", str(TIMEOUT_MS), f"{glyph} {headline}"]
            if body:
                args.append(body)
            subprocess.run(args, check=True, timeout=5)
            return "notify-send"
        except Exception:
            pass

    print(f"[assignmentvibe] {glyph} {headline}" + (f" - {body}" if body else ""),
          file=sys.stderr)
    return "stderr"
