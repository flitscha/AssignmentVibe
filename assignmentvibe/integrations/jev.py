"""
Ask Jev (TypeSafe's decision model, via OpenRouter) which statements of the
lecture notes a task needs, and which of their proofs.

Jev does not write text. It answers typed questions with probabilities, in well
under a second, and bills only the input. Here every statement gets a yes/no
("Noul") question, and every statement with a proof a second one about the
proof - two questions per Satz, answered in parallel. The whole Optimierung
script with its proofs is ~100k characters, so it is split into a few requests
that run side by side; a pick costs a fraction of a cent.

The API key is read from $OPENROUTER_API_KEY, else from
~/.config/assignmentvibe/openrouter.key. Every failure raises JevUnavailable,
so the caller can say so and leave the selection as it was.

Every pick is counted in ~/.local/state/assignmentvibe/jev_usage.json - its
requests and the cost OpenRouter reports in `usage.cost`, both for the last pick
and in total. Where a response lacks the cost it is estimated from its tokens at
the list price and shown as "~$".

Depends only on assignmentvibe.paths - no dependency on core or on any other
integration module. Standard library only: a few POSTs do not justify an SDK.
The network modules are imported where they are used: the bar reads the usage
totals from here every few seconds and needs none of them.
"""

import json
import os

from .. import paths

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"

# Pinned, not "~typesafe/jev-latest": the threshold in core.selection is tuned
# against this version's probabilities, and -latest moves without notice.
MODEL = "typesafe/jev-1.13"

# List price, for estimating a request whose response carries no cost. Output
# is free.
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000

# Jev's context on OpenRouter is 32k tokens for state and questions together.
# Maths notes tokenize badly (∈, ⊂, subscripts), so a request is kept to what
# ~2 characters per token would still fit.
MAX_REQUEST_CHARS = 56_000

TIMEOUT_S = 15
PARALLEL_REQUESTS = 6

STATEMENT_QUESTION = {
    "instructions": "Does a solution to the task need {id} from the lecture notes?",
    "criteria": {
        "true": "The solution uses or cites it, or it is what the task asks about.",
        "false": "The solution can be written without it.",
    },
}
PROOF_QUESTION = {
    "instructions": "Does the proof of {id} from the lecture notes help to solve the task?",
    "criteria": {
        "true": ("The task asks for the same or a similar argument, or the "
                 "solution reuses a technique from this proof."),
        "false": "Knowing the statement is enough; its proof is not needed.",
    },
}


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
    """One Decisions API call. Returns the parsed response ("answers", "usage").
    Does not count it - judge() does, once all its requests are back."""
    import urllib.error
    import urllib.request

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


def _question(template: dict, item_id: str) -> dict:
    return {"type": "noul",
            "instructions": template["instructions"].format(id=item_id),
            "criteria": template["criteria"]}


def _batches(task: str, items: dict[str, dict]) -> list[list[str]]:
    """Item ids split into requests that each stay under MAX_REQUEST_CHARS -
    an item (statement, proof, its questions) is never split across two."""
    question_chars = len(json.dumps(STATEMENT_QUESTION)) + len(json.dumps(PROOF_QUESTION))
    room = MAX_REQUEST_CHARS - len(task) - 200
    batches, current, used = [], [], 0
    for item_id, item in items.items():
        size = len(json.dumps(item, ensure_ascii=False)) + question_chars
        if current and used + size > room:
            batches.append(current)
            current, used = [], 0
        current.append(item_id)
        used += size
    if current:
        batches.append(current)
    return batches


def _ask(task: str, items: dict[str, dict], ids: list[str], model: str) -> dict:
    questions = {}
    for n, item_id in enumerate(ids):
        questions[f"s{n}"] = _question(STATEMENT_QUESTION, item_id)
        if items[item_id].get("proof"):
            questions[f"p{n}"] = _question(PROOF_QUESTION, item_id)
    state = {"task": task, "lecture_notes": {i: items[i] for i in ids}}
    return decide(state, questions, model)


def judge(task: str, items: dict[str, dict],
          model: str = MODEL) -> tuple[dict[str, float], dict[str, float]]:
    """(P(statement needed), P(proof helps)) per item id, in the order given.
    `items` is {id: {"statement": text, "proof": text or absent}} - see
    core.selection.judgement_items."""
    from concurrent.futures import ThreadPoolExecutor

    if not items:
        return {}, {}
    batches = _batches(task, items)
    with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
        responses = list(pool.map(lambda ids: _ask(task, items, ids, model), batches))
    record([response.get("usage") or {} for response in responses])

    statement_p, proof_p = {}, {}
    for ids, response in zip(batches, responses):
        answers = response.get("answers") or {}
        for n, item_id in enumerate(ids):
            statement_p[item_id] = _probability(answers, f"s{n}", item_id)
            if items[item_id].get("proof"):
                proof_p[item_id] = _probability(answers, f"p{n}", item_id)
    return statement_p, proof_p


def _probability(answers: dict, qid: str, item_id: str) -> float:
    value = (answers.get(qid) or {}).get("noul")
    if not isinstance(value, (int, float)):
        raise JevUnavailable(f"no answer for {item_id}")
    return float(value)


# --- Usage counter ------------------------------------------------------------

def usage() -> dict:
    """{"requests", "input_tokens", "cost_usd", "estimated_usd", "last"} since
    the file was started. estimated_usd is the part of cost_usd that was
    estimated; "last" is {"requests", "cost_usd", "estimated"} of the last pick."""
    blank = {"requests": 0, "input_tokens": 0, "cost_usd": 0.0,
             "estimated_usd": 0.0, "last": None}
    try:
        stored = json.loads(paths.JEV_USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return blank
    return {**blank, **stored}


def record(responses: list[dict]) -> dict:
    """Count one pick: the `usage` of each of its responses."""
    total = usage()
    last = {"requests": len(responses), "cost_usd": 0.0, "estimated": False}
    for response_usage in responses:
        tokens = response_usage.get("input_tokens") or 0
        cost = response_usage.get("cost")
        if not isinstance(cost, (int, float)):
            cost = tokens * USD_PER_INPUT_TOKEN
            total["estimated_usd"] += cost
            last["estimated"] = True
        total["input_tokens"] += tokens
        total["cost_usd"] += cost
        last["cost_usd"] += cost
    total["requests"] += len(responses)
    total["last"] = last
    paths.JEV_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.JEV_USAGE_FILE.write_text(json.dumps(total, indent=1), encoding="utf-8")
    return total


def _dollars(amount: float, estimated: bool) -> str:
    return f"{'~' if estimated else ''}${amount:.4f}"


def usage_summary(total: dict | None = None, compact: bool = False) -> str:
    """"last pick $0.0011 (3 requests) · total $0.0042 (12 requests)", or with
    `compact` "last $0.0011 · total $0.0042 · 12 requests" for a menu row. "~$"
    where part of the amount is estimated."""
    total = total or usage()
    if not total["requests"]:
        return "not used yet"
    last = total.get("last")
    if compact:
        parts = [f"last {_dollars(last['cost_usd'], last['estimated'])}"] if last else []
        parts.append(f"total {_dollars(total['cost_usd'], bool(total['estimated_usd']))}")
        parts.append(f"{total['requests']} requests")
        return " · ".join(parts)
    text = (f"total {_dollars(total['cost_usd'], bool(total['estimated_usd']))} "
            f"({total['requests']} requests)")
    if last:
        text = (f"last pick {_dollars(last['cost_usd'], last['estimated'])} "
                f"({last['requests']} requests) · {text}")
    return text
