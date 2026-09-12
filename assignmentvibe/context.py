"""
"What am I currently working on" - course/sheet/task that were last picked.
The Waybar module reads this to show what's currently active in the top bar,
without having to re-ask everything on every click.

Depends only on assignmentvibe.paths.
"""

import json

from . import paths


def get() -> dict:
    if not paths.CONTEXT_FILE.exists():
        return {}
    return json.loads(paths.CONTEXT_FILE.read_text(encoding="utf-8"))


def set(**kwargs) -> dict:
    paths.ensure_dirs()
    current = get()
    current.update({k: v for k, v in kwargs.items() if v is not None})
    paths.CONTEXT_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")
    return current


def clear() -> None:
    if paths.CONTEXT_FILE.exists():
        paths.CONTEXT_FILE.unlink()
