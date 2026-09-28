"""
The backend of the panel in the Omarchy bar (plugin/ in this repo).

`assignmentvibe serve` runs for as long as the shell does and speaks JSON
lines over stdin/stdout: one request per line in,

    {"id": 7, "cmd": "select_task", "args": {"number": 2}}

one response per line out,

    {"id": 7, "ok": true, "messages": [...], "state": {...}, "context": {...}}

A process that stays up, rather than one `assignmentvibe ...` per click,
because the panel is clicked a lot - every tick in the context list is a
request - and a fresh interpreter costs ~100ms each time, which is a visible
lag on a checkbox. Loaded JSON stays cached between requests (store keys its
cache on mtime, so a re-ingest is still seen).

Every response carries the whole `state` the panel draws from, so one round
trip is one redraw and the panel never has to work out what a change touched.
The statement list behind the context editor is bigger and only wanted while
that tab is open; a request asks for it with "withContext".

Jev and reading in PDFs take seconds, so those run on a worker thread - one
at a time - and the panel keeps answering meanwhile. It greys out what would
race with them.

Also `assignmentvibe api <cmd> [json-args]` for a single request from the
terminal, which is how this is tested.
"""

import json
import re
import sys
import threading
import traceback

from . import context, hub

SLOW_COMMANDS = {"jev", "plan", "ingest"}


class ApiError(Exception):
    """A request that cannot be done as asked; the message is for the user."""


# --- What the panel draws ------------------------------------------------------

def _config():
    from . import uniconfig
    try:
        return uniconfig.load(), None
    except uniconfig.ConfigError as e:
        return None, str(e)


def _current_course(courses: dict[str, str]) -> str | None:
    course = context.current_course()
    if course not in courses:
        course = next(iter(courses), None)
    return course


def state_payload() -> dict:
    """Everything the panel shows outside the context editor."""
    from . import paths, store
    from .core.prompts import FOLLOW_UPS
    from .integrations import jev

    payload = {
        "error": None,
        "courses": [],
        "course": None,
        "sheets": [],
        "sheet": None,
        "tasks": [],
        "task": None,
        "summary": None,
        "jev": {"configured": jev.configured(), "picked": None,
                "usage": jev.usage_summary(compact=True)
                if paths.JEV_USAGE_FILE.exists() else ""},
        "followUps": [{"emoji": e, "label": label, "text": text}
                      for e, label, text in FOLLOW_UPS],
        "configFiles": [{"name": name, "about": about, "path": str(path),
                         "exists": path.exists()}
                        for name, about, path in hub.config_files()],
        "semester": None,
        "limit": hub.settings()["max_context_chars"],
    }

    cfg, error = _config()
    if cfg is None:
        payload["error"] = {"title": "uni.json has a problem", "body": error}
        return payload
    payload["semester"] = cfg.active
    courses = hub.semester_courses(cfg)
    if not courses:
        payload["error"] = {"title": "No courses",
                            "body": f"Semester '{cfg.active}' has no courses in uni.json."}
        return payload

    course = _current_course(courses)
    payload["courses"] = [{"slug": slug, "name": name,
                           "sheets": len(store.list_sheets(slug)),
                           "hasNotes": bool(store.load_knowledge(slug))}
                          for slug, name in courses.items()]
    payload["course"] = {"slug": course, "name": courses[course],
                         "short": courses[course].split()[0]}

    state = hub.resolve_state(course)
    sheet = state["sheet"]
    newest = hub.latest_sheet(state["sheets"])
    payload["sheets"] = [{"id": s["sheet_id"], "label": _sheet_label(s),
                          "tasks": len(s.get("tasks", [])),
                          "newest": bool(newest) and s["sheet_id"] == newest["sheet_id"],
                          "planned": store.load_plan(s["sheet_id"]) is not None}
                         for s in sorted(state["sheets"], key=hub.sheet_order)]
    if sheet:
        payload["sheet"] = _sheet_payload(sheet, state)
        payload["tasks"] = _tasks_payload(sheet, state)
    payload["task"] = state["task"]
    payload["summary"] = _summary(course, state)

    task = hub.task_of(state)
    picked = state.get("jev_pick") or {}
    if task and sheet and picked.get("task") == hub.task_ref(sheet["sheet_id"], task["number"]):
        payload["jev"]["picked"] = "edited" if picked.get("edited") else "jev"
    return payload


def _sheet_label(sheet: dict) -> str:
    return str(sheet.get("sheet_number") or sheet["sheet_id"].split("/")[-1])


def _sheet_payload(sheet: dict, state: dict) -> dict:
    from . import store
    from .core import plan as plan_core

    plan = store.load_plan(sheet["sheet_id"])
    return {
        "id": sheet["sheet_id"],
        "label": _sheet_label(sheet),
        "source": sheet.get("source"),
        "discussion": sheet.get("discussion_date"),
        "plan": {"dependencies": plan_core.dependency_text(
                     [tuple(e) for e in plan["edges"]]),
                 "cost": plan.get("cost_usd")} if plan else None,
    }


def _tasks_payload(sheet: dict, state: dict) -> list[dict]:
    from . import store
    from .core import plan as plan_core
    from .core.prompts import resolve_exercises

    plan = store.load_plan(sheet["sheet_id"])
    edges = [tuple(e) for e in plan["edges"]] if plan else []
    tasks = []
    for t in sheet["tasks"]:
        planned = (plan or {}).get("tasks", {}).get(str(t["number"]))
        found, missing = resolve_exercises(t, state["exercises"])
        text = readable(t["text"])
        if found:
            text += "".join(f"\n\n({e['number']}) {readable(e['text'])}" for e in found)
        tasks.append({
            "number": t["number"],
            "title": hub.task_title(t, state["exercises"]) or "",
            "text": text,
            "effort": round(planned["effort"]) if planned else None,
            "effortWord": plan_core.effort_word(planned["effort"]) if planned else "",
            "after": plan_core.after(t["number"], edges) if planned else [],
            "missing": missing,
        })
    return tasks


# A line that starts a part of a task: "a)", "(b)", "iii)", "2.", "•".
_ITEM_RE = re.compile(r"^(\(?[a-z]\)|\(?[ivx]+\)|\d+[.)]|[•\-–])\s")


def readable(text: str) -> str:
    """A task's text as the panel shows it. The PDF breaks lines where the
    page did, which in a panel half as wide reads as a ragged column; lines
    are joined into paragraphs again, keeping the breaks before "a)", "b)".
    Only for showing - the prompt gets the text as it was read."""
    paragraphs = []
    for block in re.split(r"\n\s*\n", text.strip()):
        joined: list[str] = []
        for line in (l.strip() for l in block.split("\n")):
            if not line:
                continue
            if joined and not _ITEM_RE.match(line):
                if joined[-1].endswith("-") and line[:1].islower():
                    joined[-1] = joined[-1][:-1] + line
                else:
                    joined[-1] += " " + line
            else:
                joined.append(line)
        paragraphs.append("\n".join(joined))
    return "\n\n".join(paragraphs)


def _summary(course: str, state: dict) -> dict:
    """The context in numbers and in words, for the card on the main tab and
    the bar's tooltip."""
    from . import store
    from .core import selection
    from .core.prompts import context_size, proof_wanted

    knowledge = store.load_knowledge(course)
    entries = selection.chosen(knowledge, state["sections"], state["statements"],
                               state["algorithms"])
    with_proof = [e for e in entries if e.get("proof")]
    proofs_on = [e for e in with_proof
                 if proof_wanted(e, state["proofs"], state["proof_of"])]
    earlier = selection.earlier_tasks(state["sheets"], state["earlier"], state["sheet"])
    return {
        "statements": len(entries),
        "proofs": len(proofs_on),
        "earlier": len(earlier),
        "size": context_size(entries, state["proofs"], state["proof_of"]),
        "lines": hub.selection_lines(course, state),
        "hasNotes": bool(knowledge),
        "hasEarlier": bool(selection.earlier_sheets(state["sheets"], state["sheet"])),
        "algorithms": state["algorithms"],
    }


def context_payload() -> dict | None:
    """The context editor: the script's outline, every statement in it, what
    is chosen, and the tasks of earlier sheets. Sizes come per statement, with
    and without its proof, so the editor adds them up itself while ticking."""
    from . import store
    from .core import selection
    from .core.prompts import entry_id, format_knowledge_entry

    cfg, _ = _config()
    if cfg is None:
        return None
    courses = hub.semester_courses(cfg)
    course = _current_course(courses)
    if course is None:
        return None
    state = hub.resolve_state(course)
    knowledge = store.load_knowledge(course)
    algorithms = state["algorithms"]

    statements = []
    for e in sorted(selection.statements(knowledge, include_algorithms=True),
                    key=selection.script_order):
        proof = e.get("proof") or ""
        statements.append({
            "id": entry_id(e),
            "type": e.get("type", ""),
            "name": e.get("name") or "",
            "text": " ".join(e.get("text", "").split())[:400],
            "section": selection.section_of(e) or "",
            "algorithm": e.get("type") in selection.ALGORITHM_TYPES,
            "size": len(format_knowledge_entry(e, include_proof=False)) + 1,
            "proofSize": (len(format_knowledge_entry(e, include_proof=True))
                          - len(format_knowledge_entry(e, include_proof=False))) if proof else 0,
            "referral": bool(proof) and selection.is_referral_proof(proof),
        })

    # Only the outline nodes something lives under; a bibliography or a
    # foreword is not something to hand to the model.
    keys = {s["section"] for s in statements if s["section"]}
    nodes = [{"key": n["key"], "title": n.get("title") or "", "level": n["level"]}
             for n in store.load_sections(course)
             if any(selection.covers(n["key"], k) for k in keys)]

    chosen = selection.chosen(knowledge, state["sections"], state["statements"], algorithms)
    earlier = []
    for sheet in selection.earlier_sheets(state["sheets"], state["sheet"]):
        for t in sheet.get("tasks", []):
            earlier.append({"ref": selection.earlier_task_ref(sheet, t),
                            "sheet": _sheet_label(sheet),
                            "task": t["number"],
                            "title": hub.task_title(t, state["exercises"]) or "",
                            "text": " ".join(t["text"].split())[:300]})
    return {
        "course": course,
        "nodes": nodes,
        "statements": statements,
        "selected": [entry_id(e) for e in chosen],
        "proofOf": state["proof_of"],
        "allProofs": state["proofs"],
        "algorithms": algorithms,
        "hasAlgorithms": any(s["algorithm"] for s in statements),
        "earlier": earlier,
        "earlierSelected": [r for r in state["earlier"]
                            if r in {e["ref"] for e in earlier}],
        "limit": hub.settings()["max_context_chars"],
    }


# --- Requests ---------------------------------------------------------------------

def _course_or_fail() -> tuple[str, str, object]:
    cfg, error = _config()
    if cfg is None:
        raise ApiError(error)
    courses = hub.semester_courses(cfg)
    course = _current_course(courses)
    if course is None:
        raise ApiError(f"Semester '{cfg.active}' has no courses in uni.json.")
    return course, courses[course], cfg


def handle(cmd: str, args: dict):
    """Do one request. Returns its result (often nothing: the new state is
    the answer)."""
    if cmd in ("state", "context"):
        return None

    if cmd == "select_course":
        cfg, error = _config()
        if cfg is None:
            raise ApiError(error)
        if args["slug"] not in hub.semester_courses(cfg):
            raise ApiError(f"No course '{args['slug']}' this semester.")
        context.set(course=args["slug"])
        return None

    course, course_name, cfg = _course_or_fail()
    state = hub.resolve_state(course)

    if cmd == "select_sheet":
        sheet = next((s for s in state["sheets"] if s["sheet_id"] == args["id"]), None)
        if sheet is None:
            raise ApiError(f"No sheet '{args['id']}'.")
        hub.select_sheet(course, sheet)
    elif cmd == "select_task":
        if not state["sheet"]:
            raise ApiError("No sheet read in yet.")
        if not any(t["number"] == args["number"] for t in state["sheet"]["tasks"]):
            raise ApiError(f"No task {args['number']} on this sheet.")
        hub.select_task(course, state["sheet"]["sheet_id"], args["number"])
    elif cmd == "set_selection":
        hub.set_selection(course, set(args.get("ids", [])), args.get("proofOf", []),
                          bool(args.get("allProofs")), args.get("earlier", []))
    elif cmd == "set_algorithms":
        hub.set_algorithms(course, bool(args["on"]))
    elif cmd == "clear_selection":
        hub.clear_selection(course)
    elif cmd == "jev":
        hub.jev_into_state(course, state)
    elif cmd == "plan":
        hub.plan_sheet(course, state)
    elif cmd == "ingest":
        hub.ingest(cfg)
    elif cmd == "copy_prompt":
        return {"chars": hub.copy_prompt(course, course_name, state)}
    elif cmd == "prompt":
        if hub.task_of(state) is None:
            raise ApiError("No task chosen yet.")
        return {"text": hub.build_current_prompt(course, course_name, state)}
    elif cmd == "copy_text":
        return {"copied": hub.copy_text(args["text"], args.get("label") or "Copied")}
    elif cmd == "open_sheet":
        if not state["sheet"]:
            raise ApiError("No sheet read in yet.")
        return {"opened": hub.open_sheet(state["sheet"])}
    elif cmd == "open_chat":
        return {"opened": hub.open_chat(args.get("provider"))}
    elif cmd == "open_config":
        return {"opened": hub.open_config_file(args["name"])}
    else:
        raise ApiError(f"Unknown request '{cmd}'.")
    return None


def respond(request: dict) -> dict:
    """One request in, one response out - never an exception."""
    cmd = request.get("cmd", "")
    args = request.get("args") or {}
    response = {"id": request.get("id"), "cmd": cmd, "ok": True, "result": None}
    with hub.collect_messages() as messages:
        try:
            response["result"] = handle(cmd, args)
        except ApiError as e:
            response["ok"] = False
            hub.say("Not possible", str(e), glyph="⚠")
        except Exception as e:  # the panel must keep working after any bug
            response["ok"] = False
            traceback.print_exc(file=sys.stderr)
            hub.say("Something went wrong", f"{type(e).__name__}: {e}", glyph="⚠")
        try:
            response["state"] = state_payload()
            if cmd == "context" or args.get("withContext"):
                response["context"] = context_payload()
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            response["ok"] = False
            hub.say("Could not read the state", f"{type(e).__name__}: {e}", glyph="⚠")
    # "Asking Jev …" is what the panel's spinner already says.
    response["messages"] = [m for m in messages if m["level"] != "progress"]
    return response


# --- The loop ------------------------------------------------------------------------

def serve() -> None:
    """Answer requests from stdin until it closes. Slow requests go to a worker
    thread, one at a time; a second one while it runs is turned down."""
    out_lock = threading.Lock()
    slow: list[threading.Thread] = []
    # stdout is the protocol. Anything else that prints - the PDF readers
    # report progress with print() - goes to stderr, which the panel logs.
    out = sys.stdout
    out.reconfigure(encoding="utf-8")
    sys.stdout = sys.stderr

    def send(response: dict) -> None:
        line = json.dumps(response, ensure_ascii=False)
        with out_lock:
            out.write(line + "\n")
            out.flush()

    send({"id": None, "cmd": "hello", "ok": True, "messages": [],
          "state": state_payload()})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if request.get("cmd") in SLOW_COMMANDS:
            if slow and slow[0].is_alive():
                # Not under its own cmd: the panel takes a response to a slow
                # cmd as the end of the job that is still running.
                send({"id": request.get("id"), "cmd": "busy", "ok": False,
                      "messages": [{"title": "Busy", "level": "warn",
                                    "body": "Jev or the reader is still working."}]})
                continue
            thread = threading.Thread(target=lambda r=request: send(respond(r)),
                                      daemon=True)
            slow[:] = [thread]
            thread.start()
        else:
            send(respond(request))


def main(argv: list[str]) -> None:
    """`assignmentvibe api <cmd> [json-args]` - one request, pretty-printed."""
    if not argv:
        print("usage: assignmentvibe api <cmd> [json-args]", file=sys.stderr)
        sys.exit(2)
    args = json.loads(argv[1]) if len(argv) > 1 else {}
    response = respond({"id": 0, "cmd": argv[0], "args": args})
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(response, ensure_ascii=False, indent=1))
    if not response["ok"]:
        sys.exit(1)
