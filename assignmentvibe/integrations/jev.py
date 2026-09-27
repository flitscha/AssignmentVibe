"""
Ask Jev (TypeSafe's decision model, via OpenRouter) how relevant each section
of the lecture notes is to a task.

Jev does not write text. It answers typed questions - here one Score question
per section, on a four-level rubric - with probabilities, in well under a
second, and bills only the input: the whole Optimierung script (~8k tokens)
costs a small fraction of a cent per task. That makes it a fit for the one
judgement the keyword ranking in core.selection cannot make: a task like
"Bestimmen Sie alle ganzzahligen Lösungen ..." carries no subject vocabulary,
but a model can still tell which chapter it belongs to.

The API key is read from $OPENROUTER_API_KEY, else from
~/.config/assignmentvibe/openrouter.key. Without one, `configured()` is False
and the caller keeps its keyword ranking; every failure after that raises
JevUnavailable, so the caller can fall back the same way.

Depends only on assignmentvibe.paths - no dependency on core or on any other
integration module. Standard library only: one POST does not justify an SDK.
"""

import json
import os
import urllib.error
import urllib.request

from .. import paths

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"

# Pinned, not "~typesafe/jev-latest": the relevance threshold in core.selection
# was tuned against this version's scores, and -latest moves without notice.
MODEL = "typesafe/jev-1.13"

# Jev's context on OpenRouter is 32k tokens for state and questions together.
# Maths notes tokenize badly (∈, ⊂, subscripts), so this assumes ~2 characters
# per token and leaves room for the questions.
MAX_STATE_CHARS = 48_000

TIMEOUT_S = 10

# Ordered from "leave it out" to "this is what the task is about". The middle
# levels are what makes the expected value useful: a section the solution cites
# once should rank above one that only shares the topic.
RUBRIC = [
    "Unrelated to the task.",
    "Same broad topic, but nothing in it would be cited in a solution.",
    "Contains some definitions or theorems a solution would use.",
    "Contains the central definitions or theorems the task is about.",
]


class JevUnavailable(Exception):
    """No key, no connection, or an answer we could not use."""


def api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    try:
        return paths.OPENROUTER_KEY_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def configured() -> bool:
    return api_key() is not None


def decide(state, questions: dict, model: str = MODEL) -> dict:
    """One Decisions API call. Returns the parsed response ("answers", "usage")."""
    key = api_key()
    if not key:
        raise JevUnavailable(f"no API key (set OPENROUTER_API_KEY or write it to "
                             f"{paths.OPENROUTER_KEY_FILE})")
    body = json.dumps({"model": model, "state": state, "questions": questions})
    request = urllib.request.Request(
        ENDPOINT, data=body.encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "X-Title": "AssignmentVibe"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        # The body says why (no credit, bad model id, too many tokens); the
        # status line alone does not.
        detail = e.read().decode("utf-8", "replace")[:300]
        raise JevUnavailable(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise JevUnavailable(f"no connection ({e})") from e
    except json.JSONDecodeError as e:
        raise JevUnavailable("answer was not JSON") from e


def rank(task: str, sections: dict[str, str],
         model: str = MODEL) -> tuple[dict[str, float], float | None]:
    """(relevance per section key in 0..1, cost in USD). All sections go into one
    request as state, with one question each, answered in parallel."""
    if not sections:
        return {}, 0.0
    # Question names are opaque ids: section keys like "3.1.2" are not
    # guaranteed to be valid names, and the mapping back is ours anyway.
    ids = {f"s{i}": key for i, key in enumerate(sections)}
    questions = {
        qid: {
            "type": "score",
            "instructions": (f"How much of what is needed to solve the task is in "
                             f"section {key} of the lecture notes?"),
            "criteria": RUBRIC,
        }
        for qid, key in ids.items()
    }
    response = decide({"task": task, "lecture_note_sections": sections},
                      questions, model)
    answers = response.get("answers") or {}
    relevance = {}
    for qid, key in ids.items():
        score = (answers.get(qid) or {}).get("score")
        if not isinstance(score, (int, float)):
            raise JevUnavailable(f"no score for section {key}")
        relevance[key] = score / (len(RUBRIC) - 1)
    return relevance, (response.get("usage") or {}).get("cost")
