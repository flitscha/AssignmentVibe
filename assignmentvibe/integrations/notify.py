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


def send(headline: str, body: str = "", glyph: str = "🧮") -> str:
    """Returns the channel that was used ('omarchy', 'notify-send', 'stderr')."""
    if shutil.which("omarchy-notification-send"):
        try:
            cmd = ["omarchy-notification-send", glyph, headline]
            if body:
                cmd.append(body)
            subprocess.run(cmd, check=True, timeout=5)
            return "omarchy"
        except Exception:
            pass

    if shutil.which("notify-send"):
        try:
            args = ["notify-send", f"{glyph} {headline}"]
            if body:
                args.append(body)
            subprocess.run(args, check=True, timeout=5)
            return "notify-send"
        except Exception:
            pass

    print(f"[assignmentvibe] {glyph} {headline}" + (f" - {body}" if body else ""), file=sys.stderr)
    return "stderr"
