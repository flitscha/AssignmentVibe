"""
`assignmentvibe` CLI - entry point for the terminal, the Waybar module, and
the hub menu (the one behind a top-bar click on Omarchy).

Subcommands:
  config show|init|path                   the per-semester config (uniconfig.py)
  sort [--apply]                          move matching downloads into ~/Uni/<semester>/<course>/
  launcher                                (re)generate the Super+Space .desktop entries
  organize <dir>                          older heuristic sorter, superseded by `sort`
  ingest-script <pdf> --course NAME       ingest a script -> knowledge base
  ingest-sheet  <pdf> --course NAME       ingest an assignment sheet
  courses                                  list ingested courses
  sheets [--course SLUG]                   list ingested assignment sheets
  sections [--course SLUG] [--all]          the chapters a script chunks into
  tasks <sheet_id>                          list the tasks on a sheet
  context show|clear                        current working context
  build   ...                                build a prompt, print to stdout
  copy    ...                                 build a prompt + copy to clipboard
  jev [--usage]                                 let Jev pick statements + proofs for the task
  plan [--sheet ID] [--show]                    let Jev estimate each task's work and an order
  followup                                     copy a canned reply for the chat
  pick                                           the hub menu (top-bar click)
  waybar-status                                   JSON status for the Waybar module
  open-browser [--provider ...]                   open the chat website

There is one prompt mode: solve the task. The seven it replaces ("hint",
"explain the concept", "what next", ...) asked the reader to decide how much
of an answer they wanted BEFORE seeing one, which is the wrong moment - you
read the first step, get the idea, and stop. What those modes were for now
lives in `followup` as canned replies, one click at the moment it is needed.

Note on language: this file (like the rest of the codebase) is commented in
English, but user-facing strings passed to notify.send()/print() are
deliberately kept in German - this is a personal tool for a German-speaking
user working through German course material, so the product's own UI text
stays German while the source code stays English.
"""

import json
import os
import sys
from pathlib import Path

from . import context, paths

# Nothing heavier than json is imported up here. argparse, uniconfig, the
# prompt builder, the clipboard, the menu and the notifier are each imported by
# the commands that use them. The bar re-runs `waybar-status` every few seconds
# for the whole session and needs none of them - it prints one line of JSON -
# and that was a third of its run time, spent on argument parsers, subprocess
# and clipboard backends it never touched.


class _LazyModule:
    """Imports a submodule the first time something is read off it.

    `menu` and `notify` are used by nearly every interactive command and by
    none of the ones the bar polls, and between them they pull in subprocess,
    shutil and tempfile. A plain lazy import inside each function would work but
    would have to be repeated at forty call sites; this keeps `menu.pick(...)`
    reading the same everywhere, and keeps the module attribute patchable in
    tests."""

    def __init__(self, name: str):
        self._name = name
        self._module = None

    def __getattr__(self, attr: str):
        if self._module is None:
            from importlib import import_module
            self._module = import_module(f".integrations.{self._name}", __package__)
        return getattr(self._module, attr)


menu = _LazyModule("menu")
notify = _LazyModule("notify")

def _print(*args):
    print(*args)


def cmd_ingest_script(args):
    from . import store
    result = store.ingest_script(Path(args.pdf), args.course)
    _print(f"'{result['course']}' read in: {result['entries']} knowledge entries "
           f"-> {result['knowledge_path']}")


def cmd_ingest_sheet(args):
    from . import store
    result = store.ingest_sheet(Path(args.pdf), args.course)
    _print(f"'{result['sheet_id']}' ({result['course']}): {result['num_tasks']} tasks read in.")


def cmd_courses(args):
    from . import store
    courses = store.list_courses()
    if not courses:
        _print("No courses read in yet. Start with 'ingest-script'.")
        return
    for slug, name in courses.items():
        _print(f"{slug}\t{name}")


def cmd_sheets(args):
    from . import store
    sheets = store.list_sheets(args.course)
    if not sheets:
        _print("No assignment sheets found.")
        return
    for s in sheets:
        _print(f"{s['sheet_id']}\t{s.get('course_slug', '?')}\t"
               f"{s.get('num_tasks', '?')} tasks\t"
               f"sheet {s.get('sheet_number', '?')}")


def cmd_tasks(args):
    from . import store
    sheet = store.load_sheet(args.sheet_id)
    for t in sheet["tasks"]:
        from .core.assignments import title_of
        title = title_of(t)
        _print(f"{t['number']}{f': {title}' if title else ''}")


def cmd_context(args):
    if args.action == "show":
        ctx = context.get()
        _print(json.dumps(ctx, ensure_ascii=False, indent=1) if ctx else "(no context set)")
    elif args.action == "clear":
        context.clear()
        _print("Context cleared.")


def _resolve_solution(args) -> str | None:
    from .integrations import ocr

    if args.solution:
        return args.solution
    if args.solution_file:
        return Path(args.solution_file).read_text(encoding="utf-8")
    if args.solution_image:
        try:
            return ocr.image_to_text(args.solution_image)
        except ocr.OcrUnavailable as e:
            print(f"OCR fehlgeschlagen: {e}", file=sys.stderr)
            sys.exit(1)
    return None


_loaded_settings: dict | None = None


def _settings() -> dict:
    """settings.json, or its defaults when it is broken - a typo there should
    not take the whole menu down. Read once per run: the hub redraws after every
    click, and a broken file would otherwise say so after every click."""
    global _loaded_settings
    if _loaded_settings is None:
        _loaded_settings = _read_settings()
    return _loaded_settings


def _read_settings() -> dict:
    from . import settings

    try:
        return settings.load()
    except settings.SettingsError as e:
        notify.send("settings.json ignored", str(e), glyph="⚠")
        return dict(settings.DEFAULTS)


def _earlier_rows(state: dict) -> list[tuple[str, str]]:
    """(ref, label) for the context picker: every task of the earlier sheets,
    labelled with what it is about."""
    rows = []
    for label, (ref, text) in _earlier_candidates(state["sheets"], state["sheet"],
                                                  state["exercises"]).items():
        about = " ".join(text.split())
        rows.append((ref, f"{label}  {about[:50] + '…' if len(about) > 50 else about}"))
    return rows


def _earlier_candidates(sheets: list[dict], sheet: dict | None,
                        exercises: list[dict]) -> dict[str, tuple[str, str]]:
    """label -> (ref, task text) for every task of the sheets before `sheet`,
    as Jev is asked about them. A second version of a sheet under the same
    number ("Blatt4_english_version") has the same labels and is skipped."""
    from .core import selection
    from .core.prompts import task_query

    found = {}
    for earlier in selection.earlier_sheets(sheets, sheet):
        for t in earlier.get("tasks", []):
            label = selection.earlier_task_label(earlier, t)
            found.setdefault(label, (selection.earlier_task_ref(earlier, t),
                                     task_query(t, exercises)))
    return found


def _jev_pick(task: dict, knowledge: list[dict], exercises: list[dict],
              include_algorithms: bool = False, sheets: list[dict] | None = None,
              sheet: dict | None = None
              ) -> tuple[list[str], list[str], list[str], list[str]] | None:
    """(statement ids, proof ids, proofs dropped for length, earlier task refs)
    Jev judges the task to need, or None when it could not be asked - said in
    a notification, since the user pressed for it. Earlier tasks are those of
    the course's sheets before `sheet`."""
    from .integrations import jev

    candidates = _earlier_candidates(sheets or [], sheet, exercises)
    try:
        judged = _judge_task(task, knowledge, exercises, include_algorithms, candidates)
    except jev.JevUnavailable as e:
        notify.send("Jev unavailable", f"The selection is unchanged. {e}", glyph="⚠")
        return None
    return _from_judgement(judged, knowledge, include_algorithms, candidates)


def _judge_task(task: dict, knowledge: list[dict], exercises: list[dict],
                include_algorithms: bool, candidates: dict[str, tuple[str, str]],
                usage_sink: list | None = None) -> tuple[dict, dict, dict]:
    """Jev's raw answers for one task: (statement_p, proof_p, earlier_p).
    Raises jev.JevUnavailable."""
    from .core import selection
    from .core.prompts import task_query
    from .integrations import jev

    return jev.judge(task_query(task, exercises),
                     selection.judgement_items(knowledge, include_algorithms),
                     selection.proof_candidates(knowledge, include_algorithms),
                     {label: text for label, (_, text) in candidates.items()},
                     usage_sink=usage_sink)


def _from_judgement(judged: tuple[dict, dict, dict], knowledge: list[dict],
                    include_algorithms: bool, candidates: dict[str, tuple[str, str]]
                    ) -> tuple[list[str], list[str], list[str], list[str]]:
    """Jev's answers made a selection: (statement ids, proof ids, proofs
    dropped for length, earlier task refs). Over settings' max_context_chars,
    the least certain proofs go first; the statements stay, since those are
    what the solution has to cite."""
    from .core import selection

    statement_p, proof_p, earlier_p = judged
    config = _settings()
    statements, proofs = selection.pick_from_judgement(
        statement_p, proof_p, config["jev_statement_threshold"],
        config["jev_proof_threshold"])
    entries = selection.chosen(knowledge, [], statements, include_algorithms)
    proofs, dropped = selection.trim_proofs(entries, proofs, proof_p,
                                            config["max_context_chars"])
    earlier = [candidates[label][0] for label, p in earlier_p.items()
               if p >= config["jev_statement_threshold"]]
    return statements, proofs, dropped, earlier


def _build_from_args(args) -> str:
    """The command-line path to the same prompt the hub builds. Arguments win
    over what is remembered for the course, so a one-off `build --sections 3.1`
    does not overwrite the setup the widget is standing on."""
    from . import store
    from .core.prompts import build_prompt

    sheet_id = args.sheet or context.course_state().get("sheet")
    if not sheet_id:
        print("No sheet given (--sheet) and no current context set.",
              file=sys.stderr)
        sys.exit(1)
    sheet = store.load_sheet(sheet_id)

    course_slug = sheet.get("course_slug")
    saved = context.course_state(course_slug)

    task_num = args.task or saved.get("task")
    if not task_num:
        print("No task given (--task).", file=sys.stderr)
        sys.exit(1)
    task = next((t for t in sheet["tasks"] if t["number"] == int(task_num)), None)
    if task is None:
        print(f"Task {task_num} is not on sheet {sheet_id}.", file=sys.stderr)
        sys.exit(1)

    knowledge = store.load_knowledge(course_slug) if course_slug else []
    exercises = store.load_exercises(course_slug) if course_slug else []
    course_name = store.list_courses().get(course_slug, course_slug or "")
    solution = _resolve_solution(args)

    # Another task than the remembered one brings its planned selection along,
    # as in the hub.
    if (sheet["sheet_id"], int(task_num)) != (saved.get("sheet"), saved.get("task")):
        _select_task(course_slug, sheet["sheet_id"], int(task_num))
        saved = context.course_state(course_slug)

    sections = getattr(args, "sections", None) or saved.get("sections")
    proofs = getattr(args, "proofs", None)
    if proofs is None:
        proofs = saved.get("proofs")
    proof_of = getattr(args, "proof_of", None)
    if proof_of is None:
        proof_of = saved.get("proof_of")
    algorithms = getattr(args, "algorithms", None)
    if algorithms is None:
        algorithms = bool(saved.get("algorithms", _settings()["algorithms_by_default"]))

    statements = getattr(args, "statements", None)
    if statements is None and not getattr(args, "sections", None):
        statements = saved.get("statements")
    sheets = store.list_sheets(course_slug) if course_slug else []
    earlier = saved.get("earlier_tasks") or []
    if getattr(args, "jev", False):
        picked = _jev_pick(task, knowledge, exercises, algorithms, sheets, sheet)
        if picked is None:
            print("Jev could not be asked - see the notification.", file=sys.stderr)
            sys.exit(1)
        sections, (statements, proof_of, _, earlier), proofs = [], picked, False

    from .core import selection
    return build_prompt(task, sheet, knowledge, solution, course_name,
                        sections=sections, include_proofs=proofs,
                        include_algorithms=algorithms,
                        section_titles=store.load_section_titles(course_slug)
                        if course_slug else {},
                        exercises=exercises, proof_of=proof_of,
                        statements=statements,
                        earlier_tasks=selection.earlier_tasks(sheets, earlier, sheet))


def cmd_build(args):
    sys.stdout.reconfigure(encoding="utf-8")
    print(_build_from_args(args))


def cmd_copy(args):
    from .integrations import clipboard

    prompt = _build_from_args(args)
    ok, method = clipboard.copy(prompt)
    if ok:
        notify.send("Prompt kopiert", f"{len(prompt)} Zeichen (via {method})", glyph="📋")
        _print(f"Copied to clipboard ({method}).")
    else:
        notify.send("No clipboard available", f"Prompt saved to: {method}", glyph="⚠")
        _print(f"No clipboard tool found. Prompt saved to: {method}")


# The bar glyph. A Nerd Font codepoint (nf-md-school), not an emoji: the bar
# renders in the shell's monospace font, where a colour emoji is a different
# size than everything beside it. Overridable for a bar without a Nerd Font.
BAR_ICON = os.environ.get("ASSIGNMENTVIBE_BAR_ICON", "\U000f0dc9")


def cmd_waybar_status(args):
    """What the top bar shows. Course and task, because those are the two things
    you check without clicking: am I still pointed at the right course, and
    which task is loaded.

    Waybar-style JSON, which Omarchy's Quickshell bar reads as-is for a widget
    of `"type": "command"`. No "active" class: that one turns the widget the
    theme's urgent colour, which has to keep meaning something is wrong."""
    from . import store

    course = context.current_course()
    state = context.course_state(course) if course else {}
    if not course or not state.get("task"):
        print(json.dumps({"text": BAR_ICON,
                          "tooltip": "AssignmentVibe - no task selected"},
                         ensure_ascii=False))
        return

    name = store.list_courses().get(course, course)
    # The first word is the course ("Parallele Programmierung" -> "Parallele");
    # the bar is shared with everything else running, so it gets one word.
    short = name.split()[0]

    sheet_id = state.get("sheet")
    sheet_text = sheet_id or "?"
    if sheet_id:
        try:
            sheet_text = f"Sheet {store.load_sheet(sheet_id).get('sheet_number') or sheet_id}"
        except (FileNotFoundError, OSError):
            sheet_text = sheet_id

    # The exact selection, since this is where it can be read without opening
    # anything. Only loads the knowledge base when there is something to name.
    chosen = (_selection_lines(course, state, limit=15)
              if state.get("sections") or state.get("statements")
              or state.get("earlier_tasks") else [])
    notes = "\n".join(f"  {line}" for line in chosen) or "  none"
    tooltip = (f"Course: {name}\n{sheet_text}, task {state['task']}\n\n"
               f"Lecture notes in the prompt:\n{notes}\n")
    if paths.JEV_USAGE_FILE.exists():
        from .integrations import jev
        tooltip += f"\nJev: {jev.usage_summary()}\n"
    print(json.dumps({
        "text": f"{BAR_ICON} {short} A{state['task']}",
        "tooltip": tooltip + "\nLeft: menu · Right: follow-ups · Middle: reset",
    }, ensure_ascii=False))


def cmd_open_browser(args):
    import shutil
    import subprocess

    urls = {
        "claude": "https://claude.ai/new",
        "chatgpt": "https://chatgpt.com",
        "gemini": "https://gemini.google.com/app",
    }
    url = urls.get(getattr(args, "provider", None) or "claude", urls["claude"])

    if shutil.which("omarchy-launch-webapp"):
        subprocess.run(["omarchy-launch-webapp", url])
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", url])
    else:
        print(f"No browser launcher found. Open it yourself: {url}", file=sys.stderr)
        sys.exit(1)


def cmd_organize(args):
    from . import store
    from .organizer import organize as organizer_module
    source_dir = Path(args.source)
    library_dir = Path(args.target) if args.target else paths.DEFAULT_LIBRARY_DIR

    moves = organizer_module.plan(source_dir, library_dir, store.list_courses())
    _print(organizer_module.format_plan(moves))

    if not args.apply:
        _print(f"\n(Dry run - nothing changed. Use --apply to do it, "
                f"target library: {library_dir})")
        return

    log = organizer_module.apply(moves, mode=args.mode)
    for line in log:
        _print(line)

    if args.ingest:
        for m in moves:
            if m.conflict or m.course_display_name is None:
                continue
            # Important: ingest under the RESOLVED course (course_display_name,
            # whose slug is m.course_slug), not classification.course_guess -
            # otherwise a script and its sheets can be folded into the same
            # target folder here but still end up registered as two separate
            # courses with two separate (half-empty) knowledge bases.
            if m.classification.doc_type == "script":
                store.ingest_script(m.target_path, m.course_display_name)
            elif m.classification.doc_type == "sheet":
                store.ingest_sheet(m.target_path, m.course_display_name)
        _print("Read in automatically (--ingest).")


# --- The hub -----------------------------------------------------------------
#
# One window that shows where you are and lets you change one thing at a time,
# rather than a chain of questions asked in a fixed order. The chain it replaces
# asked six of them (sheet, task, use-case, chapters, partial solution, browser)
# on every single prompt, which is tolerable with a keyboard and not at all with
# a mouse - and five of those six answers are the same as last time.
#
# So: the top row does the thing, the ARROW rows change one part of the setup
# and come straight back here. Everything below the first separator is state
# that persists per course (see assignmentvibe.context), which is why the
# common case is a single click on the top row.

def _chosen(choice: str | None, rows: list[tuple[str, object]]):
    """Map a picker's answer back to the row it came from.

    Exact match first, then ignoring surrounding whitespace: the rows are
    indented to show the tree, and a picker is free to hand the label back
    trimmed. Getting this wrong is silent - the click just does nothing - so it
    is worth the second pass."""
    for label, value in rows:
        if label == choice:
            return value, True
    for label, value in rows:
        if choice is not None and label.strip() == choice.strip():
            return value, True
    return None, False


ARROW = "▸"
COPY_ROW = "▶  Copy prompt"
FOLLOWUP_ROW = "💬 Copy a follow-up …"
BROWSER_ROW = "🌐 Open chat"
INGEST_ROW = "⟳  Read in new sheets"
JEV_ROW = "   ✨ Let Jev pick the context"
JEV_DONE_ROW = "   ✨ Context picked by Jev · ask again"
JEV_EDITED_ROW = "   ✨ Context picked by Jev, changed by hand · ask again"
PLAN_ROW = "✨ Let Jev plan this sheet  ·  effort, and the context of every task"
REPLAN_ROW = "✨ Plan again"
OPEN_SHEET_ROW = "📄 Open the sheet"
CONFIG_ROW = "⚙  Config files …"
SOLUTION_ROW = "📋 Partial solution from clipboard"
SEPARATOR = "───────────────────────────────"


def _semester_courses(cfg) -> dict[str, str]:
    """slug -> display name for the active semester's courses, in config order.

    The config is the authority on what is current; the knowledge base only
    knows what has ever been ingested, which includes last year's courses."""
    from . import store
    return {store.slug_for(c.name): c.name for c in cfg.active_courses()}


def _latest_sheet(sheets: list[dict]) -> dict | None:
    """The newest sheet of a course - by sheet number, falling back to the id.
    This is the one you are working on; older ones are rarely wanted again."""
    if not sheets:
        return None
    return max(sheets, key=lambda s: (s.get("sheet_number") or 0, s["sheet_id"]))


def _resolve_state(course: str) -> dict:
    """What the hub currently stands on: the remembered sheet and task for this
    course, repaired where it no longer exists (a sheet can be re-ingested under
    a different name, or the remembered task number can be off the end of a
    freshly replaced sheet)."""
    from . import store

    saved = context.course_state(course)
    sheets = store.list_sheets(course)
    by_id = {s["sheet_id"]: s for s in sheets}

    # "A07" is what was remembered before sheet ids carried the course.
    sheet = (by_id.get(saved.get("sheet")) or by_id.get(f"{course}/{saved.get('sheet')}")
             or _latest_sheet(sheets))
    task_num = saved.get("task")
    if sheet and not any(t["number"] == task_num for t in sheet["tasks"]):
        task_num = sheet["tasks"][0]["number"] if sheet["tasks"] else None

    return {
        "sheet": sheet,
        "task": task_num,
        "sections": saved.get("sections") or [],
        "statements": list(saved.get("statements") or []),
        "proofs": bool(saved.get("proofs")),
        "proof_of": list(saved.get("proof_of") or []),
        "earlier": list(saved.get("earlier_tasks") or []),
        "jev_pick": saved.get("jev_pick"),
        "algorithms": bool(saved.get("algorithms", _settings()["algorithms_by_default"])),
        "sheets": sheets,
        "exercises": store.load_exercises(course),
    }


def _task_of(state: dict) -> dict | None:
    sheet = state.get("sheet")
    if not sheet or state.get("task") is None:
        return None
    return next((t for t in sheet["tasks"] if t["number"] == state["task"]), None)


def _task_title(task: dict, exercises: list[dict]) -> str | None:
    """What a task is about. A task that only points into the script ("Lösen
    Sie Aufgabe (1.1) vom Skriptum") has no title of its own - the exercise it
    points at does."""
    from .core.prompts import resolve_exercises

    found, _ = resolve_exercises(task, exercises)
    if len(found) == 1:
        title = f" {found[0]['title']}" if found[0].get("title") else ""
        return f"({found[0]['number']}){title}"
    from .core.assignments import title_of
    return title_of(task)


def _context_summary(course: str, state: dict) -> str:
    from . import store
    from .core import selection, toc
    from .core.prompts import context_size

    earlier = (f" · {_count(state['earlier'], 'earlier task')}"
               if state.get("earlier") else "")
    if not state["sections"] and not state["statements"]:
        if earlier:
            return f"no lecture notes{earlier}"
        return "none - the prompt carries no lecture notes"

    titles = store.load_section_titles(course)
    entries = selection.chosen(store.load_knowledge(course), state["sections"],
                               state["statements"], state["algorithms"])
    size = context_size(entries, state["proofs"], state["proof_of"])
    names = ", ".join([toc.label(titles, k) for k in state["sections"]]
                      + state["statements"])
    if len(names) > 44:
        names = names[:41] + "…"
    # Proofs are set inside the context picker, so this row is where the hub
    # says they are on - and only then; none is the default and not news.
    from .core.prompts import proof_wanted

    with_proof = [e for e in entries if e.get("proof")]
    on = [e for e in with_proof if proof_wanted(e, state["proofs"], state["proof_of"])]
    proofs = f" · {len(on)} of {_count(with_proof, 'proof')}" if on else ""
    return f"{names}  ({len(entries)}, {size // 1000}k){proofs}{earlier}"


def _hub_rows(course: str, course_name: str, state: dict) -> list[tuple[str, str]]:
    """(label, action) for the hub, top to bottom."""
    task = _task_of(state)
    sheet = state["sheet"]

    task_text = "none"
    if task:
        from . import store
        from .core import plan as plan_core

        title = _task_title(task, state["exercises"])
        plan = store.load_plan(sheet["sheet_id"])
        planned = (plan or {}).get("tasks", {}).get(str(task["number"]))
        effort = f"  {plan_core.effort_bars(planned['effort'])}" if planned else ""
        task_text = f"{task['number']}{effort}{f'  {title}' if title else ''}"
    sheet_text = "none read in yet"
    if sheet:
        newest = _latest_sheet(state["sheets"])
        suffix = "  (newest)" if newest and newest["sheet_id"] == sheet["sheet_id"] else ""
        sheet_text = f"{sheet.get('sheet_number') or sheet['sheet_id']}{suffix}"

    rows = []
    if task:
        rows.append((COPY_ROW, "copy"))
    rows.append((FOLLOWUP_ROW, "followup"))
    rows.append((BROWSER_ROW, "browser"))
    rows.append((SEPARATOR, None))
    rows += [
        (f"   Task      {ARROW}  {task_text}", "task"),
        (f"   Sheet     {ARROW}  {sheet_text}", "sheet"),
        (f"   Course    {ARROW}  {course_name}", "course"),
        (f"   Context   {ARROW}  {_context_summary(course, state)}", "context"),
    ]
    from .integrations import jev
    # Under the row it changes, so the result shows right above the next click.
    # Only with a key and a task - without either it could only fail.
    if task and jev.configured():
        jev_pick = state.get("jev_pick") or {}
        label = JEV_ROW
        if jev_pick.get("task") == _task_ref(sheet["sheet_id"], task["number"]):
            label = JEV_EDITED_ROW if jev_pick.get("edited") else JEV_DONE_ROW
        rows.append((f"{label}  ·  {jev.usage_summary(compact=True)}", "jev"))
    # No separator before these two, though they are a group of their own: the
    # Omarchy menu caps its height at 70% of the screen, which on a 900px-high
    # (logical) screen is 630px - and a row is 50px plus 3px spacing, a
    # separator included. Twelve rows need 633px and scroll; eleven fit. The
    # glyphs and the missing indent set these two apart well enough.
    rows.append((INGEST_ROW, "ingest"))
    rows.append((CONFIG_ROW, "config"))
    return rows


def _pick_course(cfg, current: str | None) -> str | None:
    from . import store

    courses = _semester_courses(cfg)
    if not courses:
        notify.send("No courses", f"Semester '{cfg.active}' has no courses in the config.",
                    glyph="⚠")
        return None
    counts = {slug: len(store.list_sheets(slug)) for slug in courses}
    labels = {f"{'●' if slug == current else '○'} {name}  "
              f"({counts[slug]} sheets)": slug
              for slug, name in courses.items()}
    choice = menu.pick("Course", list(labels))
    return labels.get(choice) if choice else None


def _pick_sheet(state: dict, current_id: str | None) -> dict | None:
    sheets = sorted(state["sheets"], key=lambda s: (s.get("sheet_number") or 0),
                    reverse=True)
    labels = {f"{'●' if s['sheet_id'] == current_id else '○'} Sheet "
              f"{s.get('sheet_number') or s['sheet_id']}  "
              f"({s.get('num_tasks', '?')} tasks)": s
              for s in sheets}
    choice = menu.pick("Sheet", list(labels))
    return labels.get(choice) if choice else None


def _pick_task(sheet: dict, current: int | None, exercises: list[dict]):
    """The task list, with the sheet's plan where there is one: each task's
    effort and what it builds on. On top the rows that open the sheet and
    make or remake the plan. Returns a task number, "plan", "open", or None."""
    from . import store
    from .core import plan as plan_core
    from .integrations import jev

    plan = store.load_plan(sheet["sheet_id"])
    edges = [tuple(e) for e in plan["edges"]] if plan else []
    rows = [(OPEN_SHEET_ROW, "open")]
    if jev.configured():
        if plan:
            rows.append((f"{REPLAN_ROW}  ·  {plan_core.dependency_text(edges)}", "plan"))
        else:
            rows.append((PLAN_ROW, "plan"))
    for t in sheet["tasks"]:
        title = _task_title(t, exercises)
        effort = after = ""
        planned = (plan or {}).get("tasks", {}).get(str(t["number"]))
        if planned:
            effort = f"  {plan_core.effort_bars(planned['effort'])}"
            needs = plan_core.after(t["number"], edges)
            after = f"  · after {', '.join(map(str, needs))}" if needs else ""
        # The bars stand where the colon would, so the titles stay aligned.
        title = f"{'  ' if effort else ': '}{title}" if title else ""
        mark = "●" if t["number"] == current else "○"
        rows.append((f"{mark} Task {t['number']}{effort}{title}{after}", t["number"]))
    choice = menu.pick("Task", [label for label, _ in rows])
    if choice is None:
        return None
    action, found = _chosen(choice, rows)
    return action if found else None


def _select_task(course: str, sheet_id: str, task: int | None) -> None:
    """Stand on a task - and, where the sheet has a plan, on the context
    selection kept for that task: what Jev picked for it, or what was made of
    that by hand since (see _remember_selection)."""
    from . import store

    context.set_course(course, sheet=sheet_id, task=task)
    plan = store.load_plan(sheet_id)
    planned = (plan or {}).get("tasks", {}).get(str(task))
    if planned and planned.get("selection"):
        context.set_course(course, **planned["selection"])


# What a task's selection is made of, as context.set_course stores it, with
# what goes in when a key was never set. "jev_pick" says which task Jev picked
# the selection for, and whether it was changed by hand since.
SELECTION_KEYS = {"sections": [], "statements": [], "proof_of": [], "proofs": False,
                  "earlier_tasks": [], "jev_pick": None}


def _selection_key(entries: list[dict], state: dict) -> tuple:
    """What a selection amounts to, to tell whether the picker changed it -
    the same statements count as the same, however they were grouped."""
    from .core import selection
    from .core.prompts import entry_id

    ids = {entry_id(e) for e in selection.chosen(entries, state["sections"],
                                                 state["statements"], True)}
    return (frozenset(ids), frozenset(state["proof_of"]), state["proofs"],
            frozenset(state["earlier"]))


def _task_ref(sheet_id: str | None, task: int | None) -> str | None:
    return f"{sheet_id}#{task}" if sheet_id and task is not None else None


def _remember_selection(course: str) -> None:
    """Keep the course's current selection as the one of its current task, if
    the sheet has a plan - so a selection changed by hand is still there after
    going to another task and back."""
    from . import store

    saved = context.course_state(course)
    sheet_id, task = saved.get("sheet"), saved.get("task")
    plan = store.load_plan(sheet_id) if sheet_id else None
    planned = (plan or {}).get("tasks", {}).get(str(task))
    if not planned:
        return
    planned["selection"] = {k: saved.get(k, default) for k, default in SELECTION_KEYS.items()}
    store.save_plan(plan)


def _sheet_pdf(sheet: dict) -> Path | None:
    """Where a sheet's PDF lies: as read in, or - for a sheet read in before
    the path was kept - found by name in its course's folder."""
    from . import store, uniconfig

    if sheet.get("path") and Path(sheet["path"]).exists():
        return Path(sheet["path"])
    try:
        cfg = uniconfig.load()
    except Exception:
        return None
    for course in cfg.courses:
        if store.slug_for(course.name) != sheet.get("course_slug"):
            continue
        folder = cfg.category_dir(course, "blaetter")
        found = [folder / sheet["source"]] + sorted(folder.rglob(sheet["source"]))
        for path in found:
            if path.exists():
                return path
    return None


def _open_sheet(sheet: dict) -> bool:
    """Open the sheet's PDF in the configured viewer (Firefox by default)."""
    import shlex
    import subprocess

    from . import uniconfig

    path = _sheet_pdf(sheet)
    if path is None:
        notify.send("Sheet not found", f"{sheet.get('source')} is not in the course folder "
                    "any more.", glyph="⚠")
        return False
    try:
        viewer = uniconfig.load().pdf_viewer
    except Exception:
        viewer = "firefox"
    try:
        subprocess.Popen(shlex.split(viewer) + [str(path)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        notify.send("Could not open the sheet", f"{viewer}: {e}", glyph="⚠")
        return False
    return True


def _plan_sheet(course: str, state: dict) -> dict | None:
    """Ask Jev once about the whole current sheet, save it, and say what it is.

    Two steps. First, per task and side by side, the same pick as the Jev row
    - statements, proofs, earlier tasks - which becomes that task's context
    selection: going to a task later sets it without asking again. Then one
    request with every task and its statements, asking how much work each is
    and which builds on which. The context matters there: without it Jev
    rated "Beweise Teil a) des Satzes 1.26" a few lines; seeing what Satz 1.26
    says, it rated it a page. None if Jev could not be asked."""
    from concurrent.futures import ThreadPoolExecutor

    from . import store
    from .core import plan as plan_core
    from .core import selection
    from .core.prompts import task_query
    from .integrations import jev

    sheet, exercises = state["sheet"], state["exercises"]
    if not sheet or not sheet["tasks"]:
        notify.send("No sheet", "Read a sheet in first ('Read in new sheets').", glyph="⚠")
        return None
    name = sheet.get("sheet_number") or sheet["sheet_id"]
    notify.send("Asking Jev", f"The context of every task of sheet {name}, how much "
                "work each is, and what builds on what.", glyph="⟳")
    knowledge = store.load_knowledge(course)
    algorithms = state["algorithms"]
    items = selection.judgement_items(knowledge, algorithms)
    candidates = _earlier_candidates(state["sheets"], sheet, exercises)
    usages: list = []

    def pick(task):
        judged = _judge_task(task, knowledge, exercises, algorithms, candidates, usages)
        return judged, _from_judgement(judged, knowledge, algorithms, candidates)

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            picks = list(pool.map(pick, sheet["tasks"]))
        asked = {}
        for task, ((statement_p, _, earlier_p), (statements, _, _, earlier)) in zip(
                sheet["tasks"], picks):
            entry = {"text": task_query(task, exercises)}
            if statements:
                entry["lecture_notes_it_may_cite"] = {
                    i: items[i]["statement"]
                    for i in sorted(statements, key=lambda i: -statement_p.get(i, 0))}
            labels = [l for l, (ref, _) in candidates.items() if ref in earlier]
            if labels:
                entry["earlier_exercises_it_builds_on"] = {l: candidates[l][1] for l in labels}
            asked[f"Task {task['number']}"] = entry
        effort, depends = jev.plan_sheet(
            asked, [text for _, text in plan_core.EFFORT_LEVELS], usage_sink=usages)
    except jev.JevUnavailable as e:
        if usages:
            jev.record(usages)
        notify.send("Jev unavailable", f"No plan made. {e}", glyph="⚠")
        return None
    total = jev.record(usages)

    num = {f"Task {t['number']}": t["number"] for t in sheet["tasks"]}
    edges = plan_core.edges_from({(num[a], num[b]): p for (a, b), p in depends.items()})
    tasks = {}
    for task, (_, (statements, proofs, dropped, earlier)) in zip(sheet["tasks"], picks):
        sections, singles = selection.compress(knowledge, set(statements), algorithms)
        tasks[str(task["number"])] = {
            "effort": effort[f"Task {task['number']}"],
            "selection": {"sections": sections, "statements": singles, "proof_of": proofs,
                          "proofs": False, "earlier_tasks": earlier,
                          "jev_pick": {"task": _task_ref(sheet["sheet_id"], task["number"]),
                                       "edited": False}},
            "dropped": dropped,
        }
    plan = {"format": store.PLAN_FORMAT, "sheet_id": sheet["sheet_id"],
            "tasks_key": store.tasks_key(sheet), "tasks": tasks,
            "edges": [list(e) for e in edges], "cost_usd": total["last"]["cost_usd"]}
    store.save_plan(plan)
    _select_task(course, sheet["sheet_id"], state["task"])
    notify.send(f"Sheet {name} planned",
                "\n".join(_plan_lines(plan, course) + ["", jev.usage_summary(total)]), glyph="✓")
    return plan


def _plan_lines(plan: dict, course: str) -> list[str]:
    """One line per task in the sheet's order - its effort and what its
    context holds - then the dependencies."""
    from . import store
    from .core import plan as plan_core
    from .core import selection

    knowledge = store.load_knowledge(course)
    edges = [tuple(e) for e in plan["edges"]]
    lines = []
    for n, planned in sorted(plan["tasks"].items(), key=lambda kv: int(kv[0])):
        chosen = planned.get("selection") or {}
        statements = selection.chosen(knowledge, chosen.get("sections"),
                                      chosen.get("statements"), True)
        parts = [_count(statements, "statement")] if statements else []
        if chosen.get("proof_of"):
            parts.append(_count(chosen["proof_of"], "proof"))
        if chosen.get("earlier_tasks"):
            parts.append(_count(chosen["earlier_tasks"], "earlier task"))
        what = f" · {', '.join(parts)}" if parts else ""
        lines.append(f"Task {n}  {plan_core.effort_bars(planned['effort'])} "
                     f"{plan_core.effort_word(planned['effort'])}{what}")
    lines.append(f"Dependencies: {plan_core.dependency_text(edges)}")
    return lines


def cmd_followup(args):
    """The canned replies, as their own entry point so the Waybar module can put
    them on the right mouse button - mid-conversation you want them without
    walking through the hub."""
    from .core.prompts import FOLLOW_UPS
    from .integrations import clipboard

    labels = {f"{emoji} {label}": text for emoji, label, text in FOLLOW_UPS}
    choice = menu.pick("Follow-up", list(labels))
    if not choice:
        return
    ok, method = clipboard.copy(labels[choice])
    if ok:
        notify.send(choice, "Copied to clipboard.", glyph="")
    else:
        notify.send("Follow-up", f"No clipboard available: {method}", glyph="⚠")


def _do_ingest(cfg) -> None:
    from . import store

    notify.send("Reading in", "Processing new lecture notes and sheets.", glyph="⟳")
    result = store.ingest_missing(cfg)
    parts = []
    if result["scripts"]:
        parts.append(f"{len(result['scripts'])} lecture note(s)")
    if result["sheets"]:
        parts.append(f"{len(result['sheets'])} sheet(s)")
    if result["errors"]:
        notify.send("Read in with errors", "\n".join(result["errors"][:3]), glyph="⚠")
    elif parts:
        notify.send("Read in", ", ".join(parts), glyph="✓")
    else:
        notify.send("Nothing new", "Every sheet this semester has already been read in.")


def _copy_prompt(course: str, course_name: str, state: dict, solution: str | None) -> None:
    from . import store
    from .core.prompts import build_prompt
    from .integrations import clipboard

    from .core import selection
    from .core.prompts import resolve_exercises

    task = _task_of(state)
    prompt = build_prompt(
        task, state["sheet"], store.load_knowledge(course), solution, course_name,
        sections=state["sections"],
        statements=state["statements"],
        include_proofs=state["proofs"],
        include_algorithms=state["algorithms"],
        section_titles=store.load_section_titles(course),
        exercises=state["exercises"],
        proof_of=state["proof_of"],
        earlier_tasks=selection.earlier_tasks(state["sheets"], state["earlier"],
                                              state["sheet"]),
    )
    ok, method = clipboard.copy(prompt)
    _, missing = resolve_exercises(task, state["exercises"])
    if missing:
        # The prompt still goes out - the reference is in it - but without the
        # exercise the model has nothing to solve, and that must not be silent.
        notify.send("Exercise not found",
                    f"Aufgabe {', '.join(missing)} is not in the read-in lecture notes. "
                    "Paste it into the chat yourself, or read the notes in again.",
                    glyph="⚠")
    if ok:
        notify.send(f"Task {state['task']} copied",
                    f"{len(prompt)} characters - paste it into the chat.", glyph="")
    else:
        notify.send("Prompt built",
                    f"No clipboard available, saved to: {method}", glyph="⚠")


def _selection_lines(course: str, state: dict, limit: int = 0) -> list[str]:
    """One line per chosen section and per single statement, "+ proof" where
    its proof goes in too - the exact list, for the tooltip and notifications.
    `limit` cuts it with an "… and N more" line."""
    from . import store
    from .core import selection, toc
    from .core.prompts import entry_id

    knowledge = store.load_knowledge(course)
    titles = store.load_section_titles(course)
    lines = [f"Section {toc.label(titles, k)}" for k in state.get("sections") or []]
    by_id = {entry_id(e): e for e in selection.statements(knowledge, True)}
    proofs = set(state.get("proof_of") or ())
    singles = state.get("statements") or []
    for i in singles:
        label = _statement_label(by_id[i]) if i in by_id else i
        lines.append(label + ("  + proof" if i in proofs else ""))
    # Proofs of statements inside a whole section have no line of their own.
    if state.get("proofs"):
        lines.append("+ all their proofs")
    else:
        inside = selection.entries_in(knowledge, state.get("sections") or [], True)
        lines += [f"+ proof of {entry_id(e)}" for e in inside
                  if entry_id(e) in proofs and entry_id(e) not in singles]
    earlier = state.get("earlier") or state.get("earlier_tasks") or []
    if earlier:
        found = selection.earlier_tasks(store.list_sheets(course), earlier)
        lines += [f"Earlier: {label}" for label, _ in found]
    if limit and len(lines) > limit:
        lines = lines[:limit - 1] + [f"… and {len(lines) - limit + 1} more"]
    return lines


def _count(items: list, noun: str) -> str:
    return f"{len(items)} {noun}{'' if len(items) == 1 else 's'}"


def _jev_into_state(course: str, state: dict) -> bool:
    """Let Jev pick for the current task, and make that the course's selection.
    It replaces what was chosen before, chapters included: Jev looks at the
    whole script, so keeping the old chapters would add back what it left out."""
    from . import store
    from .integrations import jev

    from .core import selection

    knowledge = store.load_knowledge(course)
    # Without lecture notes there are still the earlier sheets to look at -
    # Numerik and Statistik hand out sheets but no script.
    if not knowledge and not selection.earlier_sheets(state["sheets"], state["sheet"]):
        notify.send("No knowledge base", "Read the lecture notes in first.", glyph="⚠")
        return False
    notify.send("Asking Jev", "Which statements, proofs and earlier tasks does "
                "this task need?", glyph="⟳")
    picked = _jev_pick(_task_of(state), knowledge, state["exercises"],
                       state["algorithms"], state["sheets"], state["sheet"])
    if picked is None:
        return False
    from .core.prompts import context_size

    statements, proofs, dropped, earlier = picked
    sections, singles = selection.compress(knowledge, set(statements),
                                           state["algorithms"])
    sheet_id = state["sheet"]["sheet_id"] if state.get("sheet") else None
    context.set_course(course, sections=sections, statements=singles,
                       proof_of=proofs, proofs=False, earlier_tasks=earlier,
                       jev_pick={"task": _task_ref(sheet_id, state.get("task")),
                                 "edited": False})
    _remember_selection(course)
    state = {"sections": sections, "statements": singles, "proof_of": proofs,
             "earlier": earlier}
    lines = _selection_lines(course, state, limit=12)
    if dropped:
        limit = _settings()["max_context_chars"]
        shown = ", ".join(dropped[:4]) + (f" +{len(dropped) - 4} more"
                                          if len(dropped) > 4 else "")
        lines.append(f"{_count(dropped, 'proof')} left out to stay under "
                     f"{limit // 1000}k characters, least certain first: {shown}")
        size = context_size(selection.chosen(knowledge, [], statements, True),
                            False, proofs)
        if size > limit:
            lines.append(f"⚠ Still {size // 1000}k characters without any proof")
    title = f"Jev picked {_count(statements, 'statement')}, {_count(proofs, 'proof')}"
    if earlier:
        title += f", {_count(earlier, 'earlier task')}"
    notify.send(title,
                "\n".join(lines + ["", jev.usage_summary()]), glyph="✓")
    return True


def cmd_jev(args):
    """The hub's Jev row from the terminal: pick for the current task and
    remember it, then print what was picked and the running totals."""
    from .integrations import jev

    if not args.usage:
        course = context.current_course()
        if not course:
            print("No current course - open the hub once first.", file=sys.stderr)
            sys.exit(1)
        state = _resolve_state(course)
        if _task_of(state) is None:
            print("No current task.", file=sys.stderr)
            sys.exit(1)
        if not _jev_into_state(course, state):
            sys.exit(1)
        for line in _selection_lines(course, _resolve_state(course)):
            _print(line)
    _print(f"Jev: {jev.usage_summary()}")


def cmd_plan(args):
    """The task picker's plan row from the terminal: plan the current sheet
    (or --sheet), or with --show print the plan made earlier."""
    from . import store

    course = context.current_course()
    if args.sheet:
        course = store.load_sheet(args.sheet).get("course_slug")
        context.set_course(course, sheet=args.sheet)
    if not course:
        print("No current course - open the hub once first.", file=sys.stderr)
        sys.exit(1)
    state = _resolve_state(course)
    plan = (store.load_plan(state["sheet"]["sheet_id"]) if args.show and state["sheet"]
            else _plan_sheet(course, state))
    if not plan:
        sys.exit(1)
    for line in _plan_lines(plan, course):
        _print(line)


def _config_files() -> list[tuple[str, str, object]]:
    """(name, what it is for, path) for the config page, in the order they
    matter. Files that are made on demand say so."""
    key = paths.OPENROUTER_KEY_FILE
    files = [
        ("uni.json", "semester, courses, where their PDFs are", paths.CONFIG_FILE),
        ("settings.json", "context length, Jev thresholds, algorithms",
         paths.SETTINGS_FILE),
        ("openrouter.key", "API key for Jev" + ("" if key.exists() else
                                               " - not there yet, opens a new one"), key),
    ]
    if paths.JEV_USAGE_FILE.exists():
        files.append(("jev_usage.json", "Jev's cost counter - empty it to start at $0",
                      paths.JEV_USAGE_FILE))
    return files


def _pick_config_file() -> bool:
    """The config page: every file the tool reads that is meant to be edited,
    one click from the editor. True if one was opened."""
    from . import settings
    from .integrations import editor

    files = _config_files()
    options = [(f"   {name:<15}{ARROW}  {about}", path) for name, about, path in files]
    choice = menu.pick("Config files", [label for label, _ in options])
    path, found = _chosen(choice, options)
    if not found:
        return False

    # Nothing to open would be an empty buffer that says nothing; each file
    # starts out as a template that explains itself.
    if path == paths.CONFIG_FILE and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STARTER_CONFIG, encoding="utf-8")
    elif path == paths.SETTINGS_FILE:
        settings.ensure_file()
    elif path == paths.OPENROUTER_KEY_FILE and not path.exists():
        # Created here rather than by the editor, so it is private from the
        # first byte instead of world-readable until someone runs chmod.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)

    if not editor.open_file(path):
        notify.send("No editor found", f"Open it yourself: {path}", glyph="⚠")
        return False
    return True


def cmd_pick(args):
    """The hub behind the top-bar click."""
    from . import store

    if not menu.any_picker_available():
        # Only a warning, not a hard abort: the stdin fallback also works
        # without a TTY (e.g. in tests via a pipe), as long as data actually
        # arrives - see integrations/menu.py.
        notify.send("No graphical picker found",
                    "None of Walker/rofi/wofi/fzf is available - with no terminal "
                    "open, nothing may happen now.", glyph="⚠")

    cfg = _load_config_or_exit(args)
    courses = _semester_courses(cfg)
    if not courses:
        notify.send("No courses", f"Semester '{cfg.active}' has no courses in the config.",
                    glyph="⚠")
        return

    course = context.current_course()
    if course not in courses:
        course = next(iter(courses))

    solution = None
    while True:
        state = _resolve_state(course)
        rows = _hub_rows(course, courses[course], state)
        where = f"task {state['task']}" if state["task"] is not None else "no task"
        header = f"{courses[course]} · {where}"
        choice = menu.pick(header, [label for label, _ in rows])
        if choice is None:
            return
        action, found = _chosen(choice, rows)
        if not found or action is None:
            continue

        if action == "copy":
            _copy_prompt(course, courses[course], state, solution)
            return
        if action == "followup":
            cmd_followup(args)
            return
        if action == "browser":
            cmd_open_browser(args)
            return
        if action == "ingest":
            _do_ingest(cfg)
            continue
        if action == "config":
            # The editor opens in its own window; the menu would only sit
            # behind it, stale once the file is saved.
            if _pick_config_file():
                return
            continue
        if action == "course":
            picked = _pick_course(cfg, course)
            if picked:
                course = picked
                context.set(course=course)
            continue
        if action == "sheet":
            picked = _pick_sheet(state, state["sheet"] and state["sheet"]["sheet_id"])
            if picked:
                # A different sheet invalidates the task number, not the chapters.
                first = picked["tasks"][0]["number"] if picked["tasks"] else None
                _select_task(course, picked["sheet_id"], first)
            continue
        if action == "task":
            if not state["sheet"]:
                notify.send("No sheet",
                            "Read a sheet in first ('Read in new sheets').",
                            glyph="⚠")
                continue
            # The list stays open after planning, so the plan is seen where
            # it shows.
            while True:
                picked = _pick_task(state["sheet"], state["task"], state["exercises"])
                if picked != "plan":
                    break
                _plan_sheet(course, state)
                state = _resolve_state(course)
            if picked == "open":
                if _open_sheet(state["sheet"]):
                    return
            elif picked is not None:
                _select_task(course, state["sheet"]["sheet_id"], picked)
            continue
        if action == "context":
            entries = store.load_knowledge(course)
            earlier = _earlier_rows(state)
            if not entries and not earlier:
                notify.send("No knowledge base",
                            f"No lecture notes have been read in for '{courses[course]}' yet.",
                            glyph="⚠")
                continue
            picked = _pick_context(entries, store.load_sections(course),
                                    state["sections"], state["proofs"],
                                    state["algorithms"], state["proof_of"],
                                    state["statements"], state["earlier"], earlier)
            if picked is not None:
                sections, proofs, algorithms, proof_of, statements, chosen = picked
                before = _selection_key(entries, state)
                context.set_course(course, sections=sections, proofs=proofs,
                                   algorithms=algorithms, proof_of=proof_of,
                                   statements=statements, earlier_tasks=chosen)
                jev_pick = state.get("jev_pick")
                if jev_pick and before != _selection_key(entries, _resolve_state(course)):
                    context.set_course(course, jev_pick={**jev_pick, "edited": True})
                _remember_selection(course)
            continue
        if action == "jev":
            _jev_into_state(course, state)
            continue


# --- Semester config, sorting and launcher entries -------------------------
# These three are the "everyday" commands and deliberately work without pymupdf
# installed (see the lazy imports above), so a fresh clone is usable right away.

STARTER_CONFIG = """{
  "active": "m1",
  "uni_root": "~/Uni",
  "downloads": "~/Downloads",

  "semesters": {
    "m1": {
      "beispielkurs": {
        "name": "Beispielkurs",
        "skript": ["VO*_Beispielkurs*.pdf"],
        "folien": ["*Folien*.pdf"],
        "blaetter": ["*Blatt*Beispielkurs*.pdf"]
      }
    }
  }
}
"""


# Exit code of `sort` (preview) when no file matches - not an error.
NOTHING_TO_DO = 10


def _load_config_or_exit(args):
    from . import uniconfig

    try:
        return uniconfig.load(getattr(args, "config", None))
    except uniconfig.ConfigError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_config(args):
    if args.action == "init":
        target = Path(args.config).expanduser() if args.config else paths.CONFIG_FILE
        if target.exists() and not args.force:
            print(f"{target} already exists. Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(STARTER_CONFIG, encoding="utf-8")
        _print(f"Template written: {target}")
        _print("Now fill in your courses and filenames, then: assignmentvibe sort")
        return

    if args.action == "path":
        _print(str(Path(args.config).expanduser() if args.config else paths.CONFIG_FILE))
        return

    cfg = _load_config_or_exit(args)
    _print(f"Config:   {cfg.path}")
    _print(f"Semester: {cfg.active}")
    _print(f"Uni:      {cfg.uni_root}")
    _print(f"Downloads:{cfg.downloads}")
    _print("")
    from . import uniconfig

    for course in cfg.active_courses():
        _print(f"{course.name}  ({cfg.course_dir(course)})")
        for category in uniconfig.CATEGORIES:
            patterns = course.patterns.get(category, [])
            if patterns:
                _print(f"    {category:9} {', '.join(patterns)}")


def cmd_sort(args):
    from .organizer import sort as sorter

    cfg = _load_config_or_exit(args)
    if not cfg.downloads.is_dir():
        print(f"Downloads folder not found: {cfg.downloads}", file=sys.stderr)
        sys.exit(1)

    items, ignored = sorter.plan(cfg)
    _print(sorter.format_plan(cfg, items, ignored))

    if not args.apply:
        if not any(i.status in (sorter.NEW, sorter.REPLACE) for i in items):
            # Distinct exit code so bin/uni-sort can skip the "move it?" prompt
            # when there is nothing to move.
            sys.exit(NOTHING_TO_DO)
        _print("\n(Preview - nothing changed. Use --apply to actually move them.)")
        return

    _print("")
    for line in sorter.apply(items, mode=args.mode):
        _print(line)

    if not args.no_launcher:
        cmd_launcher(args, cfg=cfg, quiet=True)


def cmd_launcher(args, cfg=None, quiet=False):
    from .integrations import launcher

    cfg = cfg or _load_config_or_exit(args)
    written, removed = launcher.sync(cfg)

    if quiet:
        _print(f"Launcher updated: {len(written)} entries.")
        return
    for name in written:
        _print(f"  {name}")
    for name in removed:
        _print(f"  removed: {name}")
    if not written:
        _print("No entries written - do the filenames in the config match what is "
               "actually in the course folders? (assignmentvibe config show)")
    else:
        _print(f"\n{len(written)} entries in {paths.APPLICATIONS_DIR}, "
               f"searchable with Super+Space.")


# --- Script context: which sections of the script go into the prompt --------

# The rows above the outline in the context picker. A menu row is exactly one
# action - the Omarchy menu has no second button per row - so every setting that
# is more than on/off opens its own list, and says on the row what it is now.
STATEMENTS_ROW = "   Statements  ▸  {state} …"
PROOFS_ROW = "   Proofs      ▸  {state} …"
ALGORITHMS_ROW = "   Algorithms  ▸  {state}"
EARLIER_ROW = "   Earlier     ▸  {state} …"
CLEAR_ROW = "   ✕ Clear all"
# The first rows of the Statements and Proofs lists.
SELECT_ALL_ROW = "   ✓ Select all"
DESELECT_ALL_ROW = "   ✕ Deselect all"


# How many rows the picker may show. The list is walked with arrow keys and
# every row is a decision, so depth is spent where it buys something: a script
# whose chapters fit is offered by chapter, and only one that would otherwise
# hand over unusably large pieces is opened up further. Nothing is lost by the
# coarser view - a parent key selects everything nested under it either way.
MAX_PICKER_ROWS = 10

# ...except that row count alone picks the wrong level for a script whose
# outline starts above the chapters. Stochastik's top level is three PARTS of a
# two-semester course, so the row budget alone stops there and offers three
# chunks of 46k-72k characters - a whole semester dumped in as "context". Its
# chapters are one level further down. The chunk budget is what notices that:
# roughly four thousand tokens, past which a section has stopped being context
# for a task and started being a book.
MAX_CHUNK_CHARS = 15_000


def _median(values: list[int]) -> int:
    return sorted(values)[len(values) // 2] if values else 0


def _display_depth(rows: list[tuple[int, int]],
                   max_rows: int = MAX_PICKER_ROWS,
                   max_chunk: int = MAX_CHUNK_CHARS) -> int:
    """The outline level to cut the picker off at, given (level, characters) for
    every node that has statements in it.

    Go one level deeper while either the rows still fit in the budget, or the
    level reached so far is still handing over chunks too big to be context.
    The typical chunk decides that, not the largest: a whole chapter stays
    selectable in one keystroke and is supposed to be big."""
    deepest = max((level for level, _ in rows), default=1)
    depth = 1
    for candidate in range(2, deepest + 1):
        fits = sum(1 for level, _ in rows if level <= candidate) <= max_rows
        too_coarse = _median([c for level, c in rows if level <= depth]) > max_chunk
        if not (fits or too_coarse):
            break
        depth = candidate
    return depth


def _section_tree(entries: list[dict], nodes: list[dict], chosen: set[str],
                  include_algorithms: bool = False,
                  max_rows: int = MAX_PICKER_ROWS,
                  include_proofs: bool = False,
                  proof_of: list[str] | None = None) -> list[tuple[str, str]]:
    """(menu label, section key) for the nodes of the script's outline that have
    statements beneath them, indented by depth and cut off at the depth that
    fits the row and chunk budgets (max_rows=0 shows all of them).

    Parents are offered alongside their children, so "give me all of chapter 3"
    is one keystroke rather than four. Nodes with nothing in them are left out;
    a bibliography or a foreword is not something to hand to the model.

    The box says how much of a node's statements are among `chosen` (ids):
    "✓" all, "◐" some - Jev's picks, or a chapter with one statement unticked."""
    from .core import selection, toc
    from .core.prompts import context_size
    from .core.prompts import entry_id

    grouped = selection.group_by_section(entries, include_algorithms)
    titles = {n["key"]: n["title"] for n in nodes if n.get("title")}

    filled = []
    for node in nodes:
        inside = [e for k, v in grouped.items() if selection.covers(node["key"], k)
                  for e in v]
        if inside:
            # The depth is measured on statements alone, so toggling proofs
            # changes the numbers on the rows but never which rows there are.
            filled.append((node, inside, context_size(inside, False)))

    depth = (_display_depth([(n["level"], size) for n, _, size in filled], max_rows)
             if max_rows else None)

    rows = []
    for node, inside, size in filled:
        if depth is not None and node["level"] > depth:
            continue
        key = node["key"]
        ticked = sum(1 for e in inside if entry_id(e) in chosen)
        mark = "✓" if ticked == len(inside) else "◐" if ticked else " "
        indent = "   " * (node["level"] - 1)
        # Without an outline there are no titles, only numbers - and then the
        # row has to say what the number counts.
        if titles:
            name = toc.label(titles, key)
        else:
            name = f"{'Kapitel' if node['level'] == 1 else 'Abschnitt'} {key}"
        if include_proofs or proof_of:
            size = context_size(inside, include_proofs, proof_of)
        rows.append((f"[{mark}] {indent}{name}  ({len(inside)}, {size // 1000}k)", key))
    return rows


def _pick_context(entries: list[dict], nodes: list[dict], sections: list[str],
                  include_proofs: bool = False,
                  include_algorithms: bool = False,
                  proof_of: list[str] | None = None,
                  statements: list[str] | None = None,
                  earlier: list[str] | None = None,
                  earlier_rows: list[tuple[str, str]] | None = None,
                  ) -> tuple[list[str], bool, bool, list[str], list[str], list[str]] | None:
    """The context picker. Returns (sections, include_proofs, include_algorithms,
    proof_of, single statements, earlier task refs), or None if the user
    aborted. `earlier_rows` are (ref, label) of the tasks on earlier sheets,
    see _earlier_rows. A loop rather
    than a multi-select widget because the picker chain (Walker, wofi, fzf,
    stdin) only ever returns ONE choice - see integrations/menu.py.

    Inside, the selection is a set of statement ids and nothing else; a chapter
    row ticks or unticks all of its statements. That is what lets one statement
    be unticked out of a whole chapter, and what makes a chapter Jev partly
    picked show as such. selection.compress turns it back into sections plus
    single statements on the way out."""
    from .core import selection
    from .core.prompts import context_size
    from .core.prompts import entry_id

    ids = {entry_id(e) for e in selection.chosen(entries, sections, statements,
                                                 include_algorithms)}
    proof_of = list(proof_of or [])
    earlier_rows = earlier_rows or []
    earlier = [r for r in earlier or [] if r in {ref for ref, _ in earlier_rows}]
    limit = _settings()["max_context_chars"]
    # A row that could not change anything is left out.
    has_algorithms = any(e.get("type") in selection.ALGORITHM_TYPES for e in entries)

    while True:
        chosen_entries = selection.chosen(entries, [], sorted(ids), include_algorithms)
        with_proof = [e for e in chosen_entries if e.get("proof")]
        proofs_on = [e for e in with_proof
                     if include_proofs or entry_id(e) in proof_of]
        size = context_size(chosen_entries, include_proofs, proof_of)
        over = "  ⚠ over the limit" if size > limit else ""
        done_label = (f"── ✓ Done · {_count(chosen_entries, 'statement')}, "
                      f"{_count(proofs_on, 'proof')} · {size / 1000:.1f}k of "
                      f"{limit // 1000}k characters{over} ──"
                      if ids else "── ✓ Done · nothing chosen ──")
        statements_label = STATEMENTS_ROW.format(
            state=f"{len(ids)} chosen" if ids else "none - tick a chapter below")
        proofs_label = PROOFS_ROW.format(
            state=_proofs_state(include_proofs, proof_of, with_proof))
        algorithms_label = ALGORITHMS_ROW.format(state="on" if include_algorithms else "off")
        rows = _section_tree(entries, nodes, ids, include_algorithms,
                             include_proofs=include_proofs, proof_of=proof_of)

        # Every answer goes through _chosen: the Omarchy menu hands a row back
        # without its leading spaces, so comparing with == silently misses the
        # indented rows.
        top = [(done_label, "done"), (statements_label, "statements"),
               (proofs_label, "proofs")]
        if has_algorithms:
            top.append((algorithms_label, "algorithms"))
        if earlier_rows:
            top.append((EARLIER_ROW.format(
                state=f"{len(earlier)} of {len(earlier_rows)} tasks"), "earlier"))
        if ids or proof_of or include_proofs or earlier:
            top.append((CLEAR_ROW, "clear"))
        options = top + [(SEPARATOR, None)] + [(label, ("section", key))
                                               for label, key in rows]
        choice = menu.pick("Context", [label for label, _ in options])
        if choice is None:
            return None
        action, found = _chosen(choice, options)
        if not found or action is None:
            continue

        if action == "done":
            sections, singles = selection.compress(entries, ids, include_algorithms)
            return sections, include_proofs, include_algorithms, proof_of, singles, earlier
        if action == "statements":
            if not ids:
                notify.send("Nothing chosen yet",
                            "Tick a chapter below, or let Jev pick from the main menu.",
                            glyph="⚠")
                continue
            # Every statement of the sections something was picked from - so
            # what Jev left out next to its picks can be ticked right here.
            touched = {selection.section_of(e) for e in chosen_entries}
            candidates = [e for e in selection.statements(entries, include_algorithms)
                          if selection.section_of(e) in touched]
            candidates += [e for e in chosen_entries if e not in candidates]
            candidates.sort(key=selection.script_order)
            picked = _pick_statements(candidates, ids)
            if picked is not None:
                ids = (ids - {entry_id(e) for e in candidates}) | picked
            continue
        if action == "proofs":
            if not with_proof:
                notify.send("No proofs", "None of the chosen statements has a proof.",
                            glyph="⚠")
                continue
            picked = _pick_proofs(with_proof, include_proofs, proof_of)
            if picked is not None:
                include_proofs, proof_of = picked
            continue
        if action == "algorithms":
            # Through sections, so a whole chapter gains or loses its
            # algorithms, while one picked by name stays.
            sections, singles = selection.compress(entries, ids, include_algorithms)
            include_algorithms = not include_algorithms
            ids = {entry_id(e) for e in selection.chosen(entries, sections, singles,
                                                         include_algorithms)}
            continue
        if action == "earlier":
            picked = _pick_list("Earlier tasks", earlier_rows, set(earlier),
                                lambda row, on: f"[{'✓' if on else ' '}] {row[1]}",
                                "tasks", key=lambda row: row[0])
            if picked is not None:
                earlier = [ref for ref, _ in earlier_rows if ref in picked]
            continue
        if action == "clear":
            ids, proof_of, include_proofs, earlier = set(), [], False, []
            continue

        _, key = action
        inside = {entry_id(e) for e in selection.entries_in(entries, [key],
                                                            include_algorithms)}
        ids = ids - inside if inside <= ids else ids | inside


def _proofs_state(include_all: bool, proof_of: list[str],
                  with_proof: list[dict]) -> str:
    """What the Proofs row says: "all 7", "none of 7", or the ones picked."""
    from .core.prompts import entry_id

    total = len(with_proof)
    if not total:
        return "none"
    if include_all:
        return f"all {total}"
    on = [entry_id(e) for e in with_proof if entry_id(e) in proof_of]
    if not on:
        return f"none of {total}"
    names = ", ".join(on)
    if len(names) > 40:
        names = names[:39] + "…"
    return f"{names}  ({len(on)} of {total})"


def _pick_list(header: str, candidates: list, on: set[str],
               row, noun: str, key=None) -> set[str] | None:
    """A tick list with Select all / Deselect all on top. Returns the ticked ids
    among `candidates`, or None if the user aborted. `key` gives a candidate's
    id; statements by default."""
    from .core.prompts import entry_id

    key = key or entry_id
    ids = [key(e) for e in candidates]
    on = {i for i in ids if i in on}
    while True:
        done_label = f"── ✓ Done · {len(on)} of {len(ids)} {noun} ──"
        # Actions and ids share one list for _chosen (see _pick_context); a
        # tuple cannot collide with an id string.
        options = ([(done_label, ("done",)), (SELECT_ALL_ROW, ("all",)),
                    (DESELECT_ALL_ROW, ("none",))]
                   + [(row(e, key(e) in on), key(e)) for e in candidates])
        choice = menu.pick(header, [label for label, _ in options])
        if choice is None:
            return None
        action, found = _chosen(choice, options)
        if not found:
            continue
        if action == ("done",):
            return on
        if action == ("all",):
            on = set(ids)
        elif action == ("none",):
            on = set()
        else:
            on ^= {action}


def _pick_statements(candidates: list[dict], chosen: set[str]) -> set[str] | None:
    return _pick_list("Statements", candidates, chosen, _statement_row, "statements")


def _statement_label(e: dict) -> str:
    from .core.prompts import entry_id

    # The number alone says nothing ("Satz 3.1.5"), so the label carries what
    # the statement is about: its name if it has one, else how it begins.
    about = e.get("name") or " ".join(e["text"].split())
    if len(about) > 48:
        about = about[:47] + "…"
    return f"{entry_id(e)}  {about}"


def _statement_row(e: dict, on: bool) -> str:
    return f"[{'✓' if on else ' '}] {_statement_label(e)}"


def _proof_row(e: dict, on: bool) -> str:
    # A proof of a few words ("Übung (Aufgabe (1.3)).") is worth seeing as such.
    n = len(e["proof"])
    size = f"{n / 1000:.1f}k" if n >= 100 else "<0.1k"
    return f"{_statement_row(e, on)}  ({size})"


def _pick_proofs(candidates: list[dict], include_all: bool,
                 chosen: list[str]) -> tuple[bool, list[str]] | None:
    """Which proofs of the chosen statements go into the prompt. Returns
    (include_all, chosen ids), or None if the user aborted.

    All ticked means all, also for statements chosen later - the state the
    CLI's --proofs sets. Picks outside the current selection are kept, so
    unticking a chapter and ticking it again does not lose them."""
    from .core.prompts import entry_id

    ids = [entry_id(e) for e in candidates]
    on = set(ids) if include_all else set(chosen) & set(ids)
    picked = _pick_list("Proofs", candidates, on, _proof_row, "proofs")
    if picked is None:
        return None
    kept = [c for c in chosen if c not in ids]
    if picked == set(ids):
        return True, kept
    return False, kept + [i for i in ids if i in picked]


def cmd_sections(args):
    from . import store
    from .core import selection

    course = args.course or context.get().get("course")
    if not course:
        print("No course given (--course) and no context set.", file=sys.stderr)
        sys.exit(1)

    entries = store.load_knowledge(course)
    if not entries:
        print(f"No knowledge base for '{course}'. Run 'ingest-script' first.",
              file=sys.stderr)
        sys.exit(1)

    nodes = store.load_sections(course)
    for label, _key in _section_tree(entries, nodes, set(), args.algorithms,
                                     max_rows=0 if args.all else MAX_PICKER_ROWS):
        _print(label.replace("[ ] ", "  ", 1))
    total = len(selection.statements(entries, args.algorithms))
    kinds = "definitions/theorems" + "/algorithms" * args.algorithms
    _print(f"\n{total} statements ({kinds}) out of {len(entries)} entries, "
           f"{len(nodes)} sections.")


def build_arg_parser():
    import argparse

    p = argparse.ArgumentParser(prog="assignmentvibe")
    sub = p.add_subparsers(dest="command", required=True)

    p_cfg = sub.add_parser("config", help="per-semester configuration")
    p_cfg.add_argument("action", choices=["show", "init", "path"], nargs="?", default="show")
    p_cfg.add_argument("--config", default=None, help="use a different config file")
    p_cfg.add_argument("--force", action="store_true", help="overwrite on 'init'")
    p_cfg.set_defaults(func=cmd_config)

    p_sort = sub.add_parser("sort", help="file downloads into ~/Uni as the config says")
    p_sort.add_argument("--apply", action="store_true", help="actually move them (otherwise preview only)")
    p_sort.add_argument("--mode", choices=["move", "copy"], default="move")
    p_sort.add_argument("--config", default=None)
    p_sort.add_argument("--no-launcher", action="store_true",
                        help="do not refresh the launcher entries after --apply")
    p_sort.set_defaults(func=cmd_sort)

    p_launch = sub.add_parser("launcher", help="put the courses into the Super+Space search")
    p_launch.add_argument("--config", default=None)
    p_launch.set_defaults(func=cmd_launcher)

    p_org = sub.add_parser("organize", help="older heuristic sorter for a downloads folder")
    p_org.add_argument("source", help="folder to scan (e.g. ~/Downloads)")
    p_org.add_argument("--target", default=None,
                        help=f"Ziel-Bibliothek (default: {paths.DEFAULT_LIBRARY_DIR})")
    p_org.add_argument("--apply", action="store_true", help="actually move/copy (otherwise preview only)")
    p_org.add_argument("--mode", choices=["copy", "move"], default="copy")
    p_org.add_argument("--ingest", action="store_true",
                        help="read into the knowledge base after --apply")
    p_org.set_defaults(func=cmd_organize)

    p_is = sub.add_parser("ingest-script", help="lecture notes PDF -> knowledge base")
    p_is.add_argument("pdf")
    p_is.add_argument("--course", required=True)
    p_is.set_defaults(func=cmd_ingest_script)

    p_ish = sub.add_parser("ingest-sheet", help="read in an assignment sheet PDF")
    p_ish.add_argument("pdf")
    p_ish.add_argument("--course", required=True)
    p_ish.set_defaults(func=cmd_ingest_sheet)

    p_courses = sub.add_parser("courses", help="list the courses")
    p_courses.set_defaults(func=cmd_courses)

    p_sheets = sub.add_parser("sheets", help="list the assignment sheets")
    p_sheets.add_argument("--course", default=None, help="filter by course slug")
    p_sheets.set_defaults(func=cmd_sheets)

    p_sec = sub.add_parser("sections", help="list a course's lecture-notes sections")
    p_sec.add_argument("--course", default=None, help="course slug (default: the current context)")
    p_sec.add_argument("--algorithms", action="store_true", help="count algorithms too")
    p_sec.add_argument("--all", action="store_true",
                       help="show the full tree, not just the picker's levels")
    p_sec.set_defaults(func=cmd_sections)

    p_tasks = sub.add_parser("tasks", help="list the tasks on a sheet")
    p_tasks.add_argument("sheet_id")
    p_tasks.set_defaults(func=cmd_tasks)

    p_ctx = sub.add_parser("context", help="the current context")
    p_ctx.add_argument("action", choices=["show", "clear"])
    p_ctx.set_defaults(func=cmd_context)

    for name, fn in (("build", cmd_build), ("copy", cmd_copy)):
        pb = sub.add_parser(name)
        pb.add_argument("--sheet", default=None)
        pb.add_argument("--task", type=int, default=None)
        pb.add_argument("--solution", default=None)
        pb.add_argument("--solution-file", default=None)
        pb.add_argument("--solution-image", default=None)
        pb.add_argument("--sections", nargs="*", default=None,
                        help="sections, e.g. --sections 3.1 3.2 (or '3' for a whole chapter)")
        pb.add_argument("--proofs", action="store_true", default=None,
                        help="include all proofs (default: off)")
        pb.add_argument("--proof-of", nargs="*", default=None, metavar="STATEMENT",
                        help='include single proofs, e.g. --proof-of "Satz 3.1.5"')
        pb.add_argument("--algorithms", action=argparse.BooleanOptionalAction,
                        default=None,
                        help="count algorithms as statements (default: as last "
                             "set for the course, else settings.json)")
        pb.add_argument("--statements", nargs="*", default=None, metavar="STATEMENT",
                        help='single statements, e.g. --statements "Satz 3.1.5"')
        pb.add_argument("--jev", action="store_true",
                        help="let Jev pick statements and proofs for this build")
        pb.set_defaults(func=fn)

    p_jev = sub.add_parser("jev", help="let Jev pick statements and proofs for the current task")
    p_jev.add_argument("--usage", action="store_true",
                       help="only print how many requests, tokens and dollars so far")
    p_jev.set_defaults(func=cmd_jev)

    p_plan = sub.add_parser("plan", help="let Jev estimate the work per task and an order")
    p_plan.add_argument("--sheet", default=None, help="a sheet id, e.g. analysis-4/Blatt3")
    p_plan.add_argument("--show", action="store_true", help="print the plan made earlier")
    p_plan.set_defaults(func=cmd_plan)

    p_fu = sub.add_parser("followup", help="copy a canned follow-up to the clipboard")
    p_fu.set_defaults(func=cmd_followup)

    p_pick = sub.add_parser("pick", help="the hub menu (what the top-bar click opens)")
    p_pick.add_argument("--config", default=None, help="use a different config file")
    p_pick.add_argument("--provider", default="claude",
                        choices=["claude", "chatgpt", "gemini"],
                        help="which chat 'Open chat' opens")
    p_pick.set_defaults(func=cmd_pick)

    p_wb = sub.add_parser("waybar-status", help="JSON status for the bar widget")
    p_wb.set_defaults(func=cmd_waybar_status)

    p_ob = sub.add_parser("open-browser", help="open the chat website")
    p_ob.add_argument("--provider", default="claude", choices=["claude", "chatgpt", "gemini"])
    p_ob.set_defaults(func=cmd_open_browser)

    return p


# Commands the bar polls, which therefore must not pay for the argument parser.
# argparse is ~13ms of a ~60ms run, and `waybar-status` is re-run every few
# seconds for as long as the session lasts. It takes no arguments, so there is
# nothing for a parser to do.
_NO_ARGUMENT_COMMANDS = {
    "waybar-status": lambda: cmd_waybar_status(None),
    "followup": lambda: cmd_followup(None),
}


def main() -> None:
    shortcut = _NO_ARGUMENT_COMMANDS.get(sys.argv[1]) if len(sys.argv) == 2 else None
    if shortcut:
        shortcut()
        return

    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
