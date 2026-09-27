"""
~/.config/assignmentvibe/settings.json - how the tool behaves, as opposed to
uni.json, which says what the semester looks like.

Every key is optional; a missing file or key means the default below. JSON has
no comments, so - as in uni.json - keys starting with "_" are notes and ignored.
The template written on first open carries one note per setting.
"""

import json

from . import paths

DEFAULTS = {
    # Characters of lecture notes a prompt may carry before Jev's least certain
    # proofs are dropped. ~15k characters is ~4-5k tokens: past that, context
    # stops helping a chat model focus and starts burying the task.
    "max_context_chars": 15_000,
    # Jev answers "is this needed?" with a probability; at or above the
    # threshold it counts as yes. Raise the proof one if Jev takes too many.
    "jev_statement_threshold": 0.5,
    "jev_proof_threshold": 0.5,
    # Whether algorithms count as statements in a course not yet set otherwise.
    "algorithms_by_default": True,
}

TEMPLATE = """{
  "_max_context_chars": "Characters of lecture notes a prompt may carry. When Jev's pick is longer, its least certain proofs are dropped until it fits. The context picker shows the size against this limit.",
  "max_context_chars": 15000,

  "_jev_thresholds": "From 0 to 1: how sure Jev must be that a statement (or a proof) is needed before it is picked. Higher picks fewer.",
  "jev_statement_threshold": 0.5,
  "jev_proof_threshold": 0.5,

  "_algorithms_by_default": "Whether algorithms (Algorithmus 4.1.7) count as statements, for courses where it has not been switched in the context picker.",
  "algorithms_by_default": true
}
"""


class SettingsError(Exception):
    """The file exists but cannot be used; the message says why."""


def load() -> dict:
    """DEFAULTS, overridden by what the file sets. Raises SettingsError on a
    broken file - the caller decides whether to go on with the defaults."""
    try:
        raw = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(DEFAULTS)
    except (OSError, json.JSONDecodeError) as e:
        raise SettingsError(f"{paths.SETTINGS_FILE}: {e}") from e
    if not isinstance(raw, dict):
        raise SettingsError(f"{paths.SETTINGS_FILE}: expected a JSON object")
    unknown = sorted(k for k in raw if not k.startswith("_") and k not in DEFAULTS)
    if unknown:
        raise SettingsError(f"{paths.SETTINGS_FILE}: unknown settings {unknown}. "
                            f"Known: {', '.join(DEFAULTS)}")
    values = {k: v for k, v in raw.items() if k in DEFAULTS}
    for key, value in values.items():
        default = DEFAULTS[key]
        # bool is an int to Python, and a threshold of 1 is a fine float.
        ok = (isinstance(value, bool) if isinstance(default, bool)
              else isinstance(value, (int, float)) and not isinstance(value, bool))
        if not ok:
            raise SettingsError(f"{paths.SETTINGS_FILE}: {key} should be "
                                f"{'true or false' if isinstance(default, bool) else 'a number'}"
                                f", not {json.dumps(value)}")
    return {**DEFAULTS, **values}


def ensure_file() -> None:
    """Write the annotated template if there is no file yet, so opening it
    shows every setting rather than an empty buffer."""
    if not paths.SETTINGS_FILE.exists():
        paths.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        paths.SETTINGS_FILE.write_text(TEMPLATE, encoding="utf-8")
