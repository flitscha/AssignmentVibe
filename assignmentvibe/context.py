"""
"What am I currently working on" - and, per course, what was last set up for it.

Two layers, because they expire differently. `course` is where you are right
now and changes several times a week. What sits UNDER a course - which sheet,
which task, which chapters of the script - stays true for that course for weeks,
and has to survive both a switch to another course and the end of the session.
Keeping it per course is what lets the widget open on the right chapter in
November for a selection made in October:

    {
      "course": "optimierung",
      "courses": {
        "optimierung": {"sheet": "12-Blatt-PS-Optimierung", "task": 4,
                        "sections": ["4"], "proofs": false, "algorithms": false},
        "algebra":     {"sheet": "A07", "task": 2, "sections": ["3", "5.1"]}
      }
    }

The Waybar module reads this to show what's currently active in the top bar,
without having to re-ask everything on every click.

Depends only on assignmentvibe.paths.
"""

import json

from . import paths

# Keys that used to live at the top level, before state was kept per course.
# A context file written by an older version is folded into the new shape on
# first read rather than thrown away - the chapter selection in it is exactly
# the thing that is annoying to redo.
_LEGACY_COURSE_KEYS = ("sheet", "task", "sections", "proofs", "algorithms")


def _read() -> dict:
    if not paths.CONTEXT_FILE.exists():
        return {}
    try:
        return json.loads(paths.CONTEXT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A half-written or hand-edited file should cost the remembered state,
        # not the ability to start the widget.
        return {}


def _write(data: dict) -> dict:
    paths.ensure_dirs()
    paths.CONTEXT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return data


def _migrated(data: dict) -> dict:
    if "courses" in data or not data.get("course"):
        data.setdefault("courses", {})
        return data
    legacy = {k: data.pop(k) for k in _LEGACY_COURSE_KEYS if k in data}
    data.pop("use_case", None)  # there is only one mode now
    data["courses"] = {data["course"]: legacy} if legacy else {}
    return data


def get() -> dict:
    """The whole context, migrated to the current shape (not written back;
    that happens on the next set)."""
    return _migrated(_read())


def current_course() -> str | None:
    return get().get("course")


def course_state(course: str | None = None) -> dict:
    """What was last set up for a course: sheet, task, sections, toggles.
    Empty for a course that has never been opened."""
    data = get()
    course = course or data.get("course")
    if not course:
        return {}
    return dict(data.get("courses", {}).get(course, {}))


def set_course(course: str, **values) -> dict:
    """Make `course` current and merge `values` into what is remembered for it.
    None values are skipped, so a caller can pass through arguments it did not
    get without wiping what is stored; pass an empty list to clear a selection."""
    data = get()
    data["course"] = course
    stored = data.setdefault("courses", {}).setdefault(course, {})
    stored.update({k: v for k, v in values.items() if v is not None})
    return _write(data)


def set(**kwargs) -> dict:
    """Top-level keys only. Course-scoped state goes through set_course."""
    data = get()
    data.update({k: v for k, v in kwargs.items() if v is not None})
    return _write(data)


def forget_course(course: str) -> dict:
    data = get()
    data.get("courses", {}).pop(course, None)
    return _write(data)


def clear() -> None:
    if paths.CONTEXT_FILE.exists():
        paths.CONTEXT_FILE.unlink()
