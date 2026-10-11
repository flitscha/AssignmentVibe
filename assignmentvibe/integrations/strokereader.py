"""
Read my handwriting with StrokeReader (github.com/flitscha/StrokeReader): a
small local recogniser trained on my own notes.

StrokeReader is a separate checkout with its own virtualenv (torch). It is run
as a process - `python -m strokereader.work FILE.xopp PAGE:TOP:BOTTOM ...` -
and answers with JSON: every line of those stretches as its main model reads
it. It caches per page, so asking again for a notebook that has not changed
costs well under a second and loads no model.

Where the checkout is: `strokereader_dir` in settings.json, else
$STROKEREADER_DIR, else ~/projects/StrokeReader. Its Python is the checkout's
`.venv/bin/python` when there is one.

Depends on nothing else in this project but settings.
"""

import json
import os
import subprocess
from pathlib import Path

DEFAULT_DIR = Path("~/projects/StrokeReader").expanduser()
# A page is ~1.5 s on the laptop's CPU, and the model takes ~3 s to load; a
# long task is ten pages.
TIMEOUT_S = 300


class StrokeReaderUnavailable(Exception):
    """No checkout, no models, or a reading that failed; the message says why."""


def checkout() -> Path | None:
    from .. import settings

    try:
        configured = settings.load().get("strokereader_dir") or ""
    except settings.SettingsError:
        configured = ""
    for candidate in (configured, os.environ.get("STROKEREADER_DIR", ""), str(DEFAULT_DIR)):
        if candidate:
            path = Path(candidate).expanduser()
            if (path / "strokereader" / "work.py").exists():
                return path
    return None


def available() -> bool:
    return checkout() is not None


def _python(root: Path) -> str:
    venv = root / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else "python3"


def read(notebook: Path, stretches: list[tuple[int, float, float]]) -> list[dict]:
    """The lines written in the (page, top, bottom) stretches of a notebook:
    [{"page", "box", "kind" ("text" or "note": another colour than the
    page's), "text" (StrokeReader's LaTeX)}]."""
    root = checkout()
    if root is None:
        raise StrokeReaderUnavailable(
            f"no StrokeReader checkout (set strokereader_dir in settings.json, "
            f"or clone it to {DEFAULT_DIR})")
    if not stretches:
        return []
    args = [f"{p}:{top:.1f}:{bottom:.1f}" for p, top, bottom in stretches]
    try:
        done = subprocess.run([_python(root), "-m", "strokereader.work", str(notebook), *args],
                              check=False, cwd=root, capture_output=True, text=True,
                              timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as e:
        raise StrokeReaderUnavailable(f"could not run it: {e}") from e
    if done.returncode != 0:
        last = (done.stderr.strip().splitlines() or ["no output"])[-1]
        raise StrokeReaderUnavailable(last[:300])
    try:
        return json.loads(done.stdout)["lines"]
    except (json.JSONDecodeError, KeyError) as e:
        raise StrokeReaderUnavailable("its answer was not the expected JSON") from e
