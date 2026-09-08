"""
Desktop-Benachrichtigung, mit Fallback-Kette:
omarchy-notification-send (Omarchy-Konvention, huebsches Glyph+Format)
-> notify-send (Standard auf so gut wie jedem Linux-Desktop)
-> print auf stderr (funktioniert garantiert ueberall, auch in der Sandbox
   hier ohne Notification-Daemon).
"""

import shutil
import subprocess
import sys


def send(headline: str, body: str = "", glyph: str = "🧮") -> str:
    """Gibt den benutzten Kanal zurueck ('omarchy', 'notify-send', 'stderr')."""
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
