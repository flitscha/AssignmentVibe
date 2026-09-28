"""
Ask Jev (TypeSafe's decision model, via OpenRouter) which statements of the
lecture notes a task needs, and which of their proofs.

Jev does not write text. It answers typed questions with probabilities, in well
under a second, and bills only the input. Here every statement gets a yes/no
("Noul") question, and every statement with a proof a second one: would that
proof help? Jev sees the statements only, never the proofs - see
core.selection.judgement_items for why. Earlier tasks of the course get a
question each too. The statements of a script run to ~30k characters, so they
are split into a few requests that run side by side; a pick costs a fraction
of a cent.

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
import threading

from .. import paths

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"

# Pinned, not "~typesafe/jev-latest": the threshold in core.selection is tuned
# against this version's probabilities, and -latest moves without notice.
MODEL = "typesafe/jev-1.13"

# List price, for estimating a request whose response carries no cost. Output
# is free.
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000

# Jev's context on OpenRouter is 32k tokens for state and questions together.
# A request uses at most half of it, even at ~2 characters per token (maths
# notes tokenize badly: ∈, ⊂, subscripts) - answers from a window packed to the
# brim are the ones to distrust, and more, smaller requests run side by side
# anyway.
MAX_REQUEST_CHARS = 32_000

TIMEOUT_S = 15
PARALLEL_REQUESTS = 8

STATEMENT_QUESTION = {
    "instructions": "Does a solution to the task need {id} from the lecture notes?",
    "criteria": {
        "true": "The solution uses or cites it, or it is what the task asks about.",
        "false": "The solution can be written without it.",
    },
}
# Strict on purpose: most proofs share objects with a task without helping it,
# and each one picked also drags its statement into the prompt.
PROOF_QUESTION = {
    "instructions": "Would reading the proof of {id} from the lecture notes help to solve the task?",
    "criteria": {
        "true": ("The task asks for a similar argument: its solution reuses the idea, "
                 "construction or technique of this proof, or proves a similar statement "
                 "the same way. Or the task refers to this proof explicitly."),
        "false": ("Citing the statement is enough; or the proof works differently from what "
                  "the task needs; or it only shares objects or notation with the task."),
    },
}
EARLIER_TASK_QUESTION = {
    "instructions": "Does the task build on {id}, an exercise from an earlier sheet?",
    "criteria": {
        "true": ("The task refers to it, continues it, or its solution uses that "
                 "exercise's result or the same idea."),
        "false": "It is about something else, or only shares general notions.",
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
    an item (statement, its questions) is never split across two."""
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


def _ask_notes(task: str, items: dict[str, dict], ids: list[str],
               proof_ids: set[str], model: str) -> dict:
    questions = {}
    for n, item_id in enumerate(ids):
        questions[f"s{n}"] = _question(STATEMENT_QUESTION, item_id)
        if item_id in proof_ids:
            questions[f"p{n}"] = _question(PROOF_QUESTION, item_id)
    state = {"task": task, "lecture_notes": {i: items[i]["statement"] for i in ids}}
    return decide(state, questions, model)


def _ask_earlier(task: str, earlier: dict[str, str], ids: list[str], model: str) -> dict:
    questions = {f"e{n}": _question(EARLIER_TASK_QUESTION, item_id)
                 for n, item_id in enumerate(ids)}
    state = {"task": task, "earlier_exercises": {i: earlier[i] for i in ids}}
    return decide(state, questions, model)


def judge(task: str, items: dict[str, dict], proof_ids=(),
          earlier: dict[str, str] | None = None, model: str = MODEL,
          usage_sink: list | None = None
          ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """(P(statement needed), P(its proof helps), P(earlier task built on)).

    `items` is {id: {"statement": text}} - see core.selection.judgement_items;
    `proof_ids` are the ids whose proof to ask about (core.selection.
    proof_candidates); `earlier` is {label: task text} for the tasks of earlier
    sheets. All requests run side by side and count as one pick - or, with
    `usage_sink`, are appended to it for the caller to count as part of a
    bigger one (see plan_sheet)."""
    from concurrent.futures import ThreadPoolExecutor

    proof_ids = set(proof_ids)
    earlier = earlier or {}
    note_batches = _batches(task, items) if items else []
    earlier_batches = _batches(task, {k: {"text": v} for k, v in earlier.items()})
    if not note_batches and not earlier_batches:
        return {}, {}, {}
    calls = ([lambda ids=ids: _ask_notes(task, items, ids, proof_ids, model)
              for ids in note_batches]
             + [lambda ids=ids: _ask_earlier(task, earlier, ids, model)
                for ids in earlier_batches])
    with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
        responses = list(pool.map(lambda call: call(), calls))
    usages = [response.get("usage") or {} for response in responses]
    if usage_sink is None:
        record(usages)
    else:
        usage_sink.extend(usages)

    statement_p, proof_p, earlier_p = {}, {}, {}
    for ids, response in zip(note_batches, responses):
        answers = response.get("answers") or {}
        for n, item_id in enumerate(ids):
            statement_p[item_id] = _probability(answers, f"s{n}", item_id)
            if item_id in proof_ids:
                proof_p[item_id] = _probability(answers, f"p{n}", item_id)
    for ids, response in zip(earlier_batches, responses[len(note_batches):]):
        answers = response.get("answers") or {}
        for n, item_id in enumerate(ids):
            earlier_p[item_id] = _probability(answers, f"e{n}", item_id)
    return statement_p, proof_p, earlier_p


# --- A sheet's plan -------------------------------------------------------------

EFFORT_INSTRUCTIONS = (
    "How much work is a complete written solution of {id}? Results from the "
    "lecture notes may be cited - except a result the task itself asks to "
    "prove: proving that one is the work.")
# Without the last sentence, a task that asks to prove a theorem of the notes
# ("Beweisen Sie: ... erfüllt das erste Abzählbarkeitsaxiom", Satz 4.21 of the
# Analysis 4 notes) was scored routine - Jev saw it in the notes and took
# citing it for the solution.


def _depends_question(a: str, b: str) -> dict:
    return {"type": "noul",
            "instructions": f"Does solving {b} use the result of {a}, or become "
                            f"much shorter once {a} is solved?",
            "criteria": {"true": f"{b} refers to {a}, uses what {a} shows, or reuses "
                                 f"its construction.",
                         "false": f"{b} can be solved without {a}."}}


def plan_sheet(tasks: dict[str, dict], levels: list[str], model: str = MODEL,
               usage_sink: list | None = None
               ) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """(effort score per task, P(b builds on a) per (a, b)) for one sheet, in
    one request. `tasks` is {"Task 1": {"text": ..., "lecture_notes_it_may_cite":
    {id: statement}, "earlier_exercises_it_builds_on": {label: text}}}, the
    context optional; `levels` are the effort scale, easiest first. What does
    not fit into one request is cut from the context, never from a task."""
    names = list(tasks)
    questions = {}
    for i, name in enumerate(names):
        questions[f"e{i}"] = {"type": "score",
                              "instructions": EFFORT_INSTRUCTIONS.format(id=name),
                              "criteria": list(levels)}
        for j, other in enumerate(names):
            if i != j:
                questions[f"d{i}_{j}"] = _depends_question(name, other)
    state = {"tasks": _fit(tasks, MAX_REQUEST_CHARS - len(json.dumps(questions)) - 200)}
    response = decide(state, questions, model)
    usage = [response.get("usage") or {}]
    if usage_sink is None:
        record(usage)
    else:
        usage_sink.extend(usage)

    answers = response.get("answers") or {}
    effort, depends = {}, {}
    for i, name in enumerate(names):
        value = (answers.get(f"e{i}") or {}).get("score")
        if not isinstance(value, (int, float)):
            raise JevUnavailable(f"no effort for {name}")
        effort[name] = float(value)
        for j, other in enumerate(names):
            if i != j:
                depends[(name, other)] = _probability(answers, f"d{i}_{j}", other)
    return effort, depends


def _fit(tasks: dict[str, dict], room: int) -> dict[str, dict]:
    """The tasks with their context shortened until they fit into `room`
    characters: the last statement of the longest context goes first."""
    tasks = {name: {k: (dict(v) if isinstance(v, dict) else v) for k, v in t.items()}
             for name, t in tasks.items()}
    while len(json.dumps(tasks, ensure_ascii=False)) > room:
        longest = max(tasks.values(), key=lambda t: sum(
            len(json.dumps(v, ensure_ascii=False)) for v in t.values() if isinstance(v, dict)))
        contexts = [k for k, v in longest.items() if isinstance(v, dict) and v]
        if not contexts:
            break
        key = max(contexts, key=lambda k: len(json.dumps(longest[k], ensure_ascii=False)))
        longest[key].pop(list(longest[key])[-1])
    return tasks


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


# Several picks can run side by side (a sheet's plan asks about every task at
# once); without the lock they read the same totals and the last write wins.
_RECORD_LOCK = threading.Lock()


def record(responses: list[dict]) -> dict:
    """Count one pick: the `usage` of each of its responses."""
    with _RECORD_LOCK:
        return _record(responses)


def _record(responses: list[dict]) -> dict:
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
