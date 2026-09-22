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

import argparse
import json
import sys
from pathlib import Path

from . import context, paths, uniconfig
from .core.prompts import build_prompt, format_knowledge_entry
from .integrations import clipboard, menu, notify, ocr

def _print(*args):
    print(*args)


def cmd_ingest_script(args):
    from . import store
    result = store.ingest_script(Path(args.pdf), args.course)
    _print(f"'{result['course']}' eingelesen: {result['entries']} Wissenseinheiten "
           f"-> {result['knowledge_path']}")


def cmd_ingest_sheet(args):
    from . import store
    result = store.ingest_sheet(Path(args.pdf), args.course)
    _print(f"'{result['sheet_id']}' ({result['course']}): {result['num_tasks']} Aufgaben eingelesen.")


def cmd_courses(args):
    from . import store
    courses = store.list_courses()
    if not courses:
        _print("Keine Kurse eingelesen. Mit 'ingest-script' starten.")
        return
    for slug, name in courses.items():
        _print(f"{slug}\t{name}")


def cmd_sheets(args):
    from . import store
    sheets = store.list_sheets(args.course)
    if not sheets:
        _print("Keine Aufgabenblaetter gefunden.")
        return
    for s in sheets:
        _print(f"{s['sheet_id']}\t{s.get('course_slug', '?')}\t"
               f"{s.get('num_tasks', '?')} Aufgaben\t"
               f"Blatt {s.get('sheet_number', '?')}")


def cmd_tasks(args):
    from . import store
    sheet = store.load_sheet(args.sheet_id)
    for t in sheet["tasks"]:
        title = f": {t['title']}" if t.get("title") else ""
        _print(f"{t['number']}{title}")


def cmd_context(args):
    if args.action == "show":
        ctx = context.get()
        _print(json.dumps(ctx, ensure_ascii=False, indent=1) if ctx else "(kein Kontext gesetzt)")
    elif args.action == "clear":
        context.clear()
        _print("Kontext geloescht.")


def _resolve_solution(args) -> str | None:
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


def _build_from_args(args) -> str:
    """The command-line path to the same prompt the hub builds. Arguments win
    over what is remembered for the course, so a one-off `build --sections 3.1`
    does not overwrite the setup the widget is standing on."""
    from . import store

    sheet_id = args.sheet or context.course_state().get("sheet")
    if not sheet_id:
        print("Kein Aufgabenblatt angegeben (--sheet) und kein aktueller Kontext gesetzt.",
              file=sys.stderr)
        sys.exit(1)
    sheet = store.load_sheet(sheet_id)

    course_slug = sheet.get("course_slug")
    saved = context.course_state(course_slug)

    task_num = args.task or saved.get("task")
    if not task_num:
        print("Keine Aufgabe angegeben (--task).", file=sys.stderr)
        sys.exit(1)
    task = next((t for t in sheet["tasks"] if t["number"] == int(task_num)), None)
    if task is None:
        print(f"Aufgabe {task_num} nicht in Blatt {sheet_id} gefunden.", file=sys.stderr)
        sys.exit(1)

    knowledge = store.load_knowledge(course_slug) if course_slug else []
    course_name = store.list_courses().get(course_slug, course_slug or "")
    solution = _resolve_solution(args)

    context.set_course(course_slug, sheet=sheet_id, task=int(task_num))

    sections = getattr(args, "sections", None) or saved.get("sections")
    proofs = getattr(args, "proofs", None)
    if proofs is None:
        proofs = saved.get("proofs")
    algorithms = getattr(args, "algorithms", None)
    if algorithms is None:
        algorithms = bool(saved.get("algorithms"))

    return build_prompt(task, sheet, knowledge, solution, course_name,
                        sections=sections, include_proofs=proofs,
                        include_algorithms=algorithms,
                        section_titles=store.load_section_titles(course_slug)
                        if course_slug else {})


def cmd_build(args):
    sys.stdout.reconfigure(encoding="utf-8")
    print(_build_from_args(args))


def cmd_copy(args):
    prompt = _build_from_args(args)
    ok, method = clipboard.copy(prompt)
    if ok:
        notify.send("Prompt kopiert", f"{len(prompt)} Zeichen (via {method})", glyph="📋")
        _print(f"In Zwischenablage kopiert ({method}).")
    else:
        notify.send("Zwischenablage nicht verfuegbar", f"Prompt gespeichert: {method}", glyph="⚠️")
        _print(f"Kein Zwischenablage-Tool gefunden. Prompt gespeichert unter: {method}")


def cmd_waybar_status(args):
    """What the top bar shows. Course and task, because those are the two things
    you check without clicking: am I still pointed at the right course, and
    which task is loaded."""
    from . import store

    course = context.current_course()
    state = context.course_state(course) if course else {}
    if not course or not state.get("task"):
        print(json.dumps({"text": "🧮",
                          "tooltip": "AssignmentVibe - keine Aufgabe gewaehlt",
                          "class": "idle"}, ensure_ascii=False))
        return

    name = store.list_courses().get(course, course)
    # The first word is the course ("Parallele Programmierung" -> "Parallele");
    # the bar is shared with everything else running, so it gets one word.
    short = name.split()[0][:12]

    sheet_id = state.get("sheet")
    sheet_text = sheet_id or "?"
    if sheet_id:
        try:
            sheet_text = f"Blatt {store.load_sheet(sheet_id).get('sheet_number') or sheet_id}"
        except (FileNotFoundError, OSError):
            sheet_text = sheet_id

    sections = ", ".join(state.get("sections") or []) or "automatisch nach Stichworten"
    print(json.dumps({
        "text": f"🧮 {short} A{state['task']}",
        "tooltip": (f"Kurs: {name}\n{sheet_text}, Aufgabe {state['task']}\n"
                    f"Kapitel: {sections}"),
        "class": "active",
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
        print(f"Kein Browser-Launcher gefunden. Oeffne manuell: {url}", file=sys.stderr)
        sys.exit(1)


def cmd_organize(args):
    from . import store
    from .organizer import organize as organizer_module
    source_dir = Path(args.source)
    library_dir = Path(args.target) if args.target else paths.DEFAULT_LIBRARY_DIR

    moves = organizer_module.plan(source_dir, library_dir, store.list_courses())
    _print(organizer_module.format_plan(moves))

    if not args.apply:
        _print(f"\n(Dry run - nichts wurde veraendert. Mit --apply ausfuehren, "
                f"Ziel-Bibliothek: {library_dir})")
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
        _print("Automatisch eingelesen (--ingest).")


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

ARROW = "▸"
COPY_ROW = "▶  Prompt kopieren"
FOLLOWUP_ROW = "💬 Nachfrage kopieren …"
BROWSER_ROW = "🌐 Chat oeffnen"
INGEST_ROW = "⟳  Neue Blaetter einlesen"
SOLUTION_ROW = "📋 Teilloesung aus Zwischenablage"
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

    sheet = by_id.get(saved.get("sheet")) or _latest_sheet(sheets)
    task_num = saved.get("task")
    if sheet and not any(t["number"] == task_num for t in sheet["tasks"]):
        task_num = sheet["tasks"][0]["number"] if sheet["tasks"] else None

    return {
        "sheet": sheet,
        "task": task_num,
        "sections": saved.get("sections") or [],
        "proofs": bool(saved.get("proofs")),
        "algorithms": bool(saved.get("algorithms")),
        "sheets": sheets,
    }


def _task_of(state: dict) -> dict | None:
    sheet = state.get("sheet")
    if not sheet or state.get("task") is None:
        return None
    return next((t for t in sheet["tasks"] if t["number"] == state["task"]), None)


def _sections_summary(course: str, state: dict) -> str:
    from . import store
    from .core import selection, toc

    if not state["sections"]:
        return "automatisch nach Stichworten"

    titles = store.load_section_titles(course)
    entries = selection.entries_in(store.load_knowledge(course), state["sections"],
                                   state["algorithms"])
    size = sum(len(format_knowledge_entry(e, include_proof=state["proofs"])) + 1
               for e in entries)
    names = ", ".join(toc.label(titles, k) for k in state["sections"])
    if len(names) > 44:
        names = names[:41] + "…"
    return f"{names}  ({len(entries)}, {size // 1000}k)"


def _hub_rows(course: str, course_name: str, state: dict) -> list[tuple[str, str]]:
    """(label, action) for the hub, top to bottom."""
    task = _task_of(state)
    sheet = state["sheet"]

    task_text = "keine"
    if task:
        title = f"  {task['title']}" if task.get("title") else ""
        task_text = f"{task['number']}{title}"
    sheet_text = "keins eingelesen"
    if sheet:
        newest = _latest_sheet(state["sheets"])
        suffix = "  (neuestes)" if newest and newest["sheet_id"] == sheet["sheet_id"] else ""
        sheet_text = f"{sheet.get('sheet_number') or sheet['sheet_id']}{suffix}"

    rows = []
    if task:
        rows.append((COPY_ROW, "copy"))
    rows.append((FOLLOWUP_ROW, "followup"))
    rows.append((BROWSER_ROW, "browser"))
    rows.append((SEPARATOR, None))
    rows += [
        (f"   Aufgabe  {ARROW}  {task_text}", "task"),
        (f"   Blatt    {ARROW}  {sheet_text}", "sheet"),
        (f"   Kurs     {ARROW}  {course_name}", "course"),
        (f"   Kapitel  {ARROW}  {_sections_summary(course, state)}", "sections"),
        (f"   Beweise  {ARROW}  {'an' if state['proofs'] else 'aus'}", "proofs"),
    ]
    rows.append((SEPARATOR + " ", None))
    rows.append((INGEST_ROW, "ingest"))
    return rows


def _pick_course(cfg, current: str | None) -> str | None:
    from . import store

    courses = _semester_courses(cfg)
    if not courses:
        notify.send("Keine Kurse", f"Semester '{cfg.active}' hat keine Kurse in der Config.",
                    glyph="⚠️")
        return None
    counts = {slug: len(store.list_sheets(slug)) for slug in courses}
    labels = {f"{'●' if slug == current else '○'} {name}  "
              f"({counts[slug]} Blaetter)": slug
              for slug, name in courses.items()}
    choice = menu.pick("Kurs", list(labels))
    return labels.get(choice) if choice else None


def _pick_sheet(state: dict, current_id: str | None) -> dict | None:
    sheets = sorted(state["sheets"], key=lambda s: (s.get("sheet_number") or 0),
                    reverse=True)
    labels = {f"{'●' if s['sheet_id'] == current_id else '○'} Blatt "
              f"{s.get('sheet_number') or s['sheet_id']}  "
              f"({s.get('num_tasks', '?')} Aufgaben)": s
              for s in sheets}
    choice = menu.pick("Aufgabenblatt", list(labels))
    return labels.get(choice) if choice else None


def _pick_task(sheet: dict, current: int | None) -> int | None:
    labels = {}
    for t in sheet["tasks"]:
        title = f": {t['title']}" if t.get("title") else ""
        labels[f"{'●' if t['number'] == current else '○'} Aufgabe {t['number']}{title}"] = t["number"]
    choice = menu.pick("Aufgabe", list(labels))
    return labels.get(choice) if choice else None


def cmd_followup(args):
    """The canned replies, as their own entry point so the Waybar module can put
    them on the right mouse button - mid-conversation you want them without
    walking through the hub."""
    from .core.prompts import FOLLOW_UPS

    labels = {f"{emoji} {label}": text for emoji, label, text in FOLLOW_UPS}
    choice = menu.pick("Nachfrage", list(labels))
    if not choice:
        return
    ok, method = clipboard.copy(labels[choice])
    if ok:
        notify.send(choice, "In Zwischenablage kopiert.", glyph="💬")
    else:
        notify.send("Nachfrage", f"Zwischenablage nicht verfuegbar: {method}", glyph="⚠️")


def _do_ingest(cfg) -> None:
    from . import store

    notify.send("Einlesen laeuft", "Neue Skripte und Blaetter werden verarbeitet.",
                glyph="⟳")
    result = store.ingest_missing(cfg)
    parts = []
    if result["scripts"]:
        parts.append(f"{len(result['scripts'])} Skript(e)")
    if result["sheets"]:
        parts.append(f"{len(result['sheets'])} Blatt/Blaetter")
    if result["errors"]:
        notify.send("Einlesen mit Fehlern", "\n".join(result["errors"][:3]), glyph="⚠️")
    elif parts:
        notify.send("Eingelesen", ", ".join(parts), glyph="✅")
    else:
        notify.send("Nichts Neues", "Alle Blaetter des Semesters sind schon eingelesen.",
                    glyph="🧮")


def _copy_prompt(course: str, course_name: str, state: dict, solution: str | None) -> None:
    from . import store
    from .core.prompts import build_prompt

    task = _task_of(state)
    prompt = build_prompt(
        task, state["sheet"], store.load_knowledge(course), solution, course_name,
        sections=state["sections"] or None,
        include_proofs=state["proofs"],
        include_algorithms=state["algorithms"],
        section_titles=store.load_section_titles(course),
    )
    ok, method = clipboard.copy(prompt)
    if ok:
        notify.send(f"Aufgabe {state['task']} kopiert",
                    f"{len(prompt)} Zeichen - jetzt im Chat einfuegen.", glyph="📋")
    else:
        notify.send("Prompt erstellt",
                    f"Zwischenablage nicht verfuegbar, gespeichert: {method}", glyph="⚠️")


def cmd_pick(args):
    """The hub behind the top-bar click."""
    from . import store

    if not menu.any_picker_available():
        # Only a warning, not a hard abort: the stdin fallback also works
        # without a TTY (e.g. in tests via a pipe), as long as data actually
        # arrives - see integrations/menu.py.
        notify.send("Kein grafischer Picker gefunden",
                    "Weder Walker/rofi/wofi/fzf verfuegbar - falls kein "
                    "Terminal offen ist, passiert jetzt evtl. nichts.", glyph="⚠️")

    cfg = _load_config_or_exit(args)
    courses = _semester_courses(cfg)
    if not courses:
        notify.send("Keine Kurse", f"Semester '{cfg.active}' hat keine Kurse in der Config.",
                    glyph="⚠️")
        return

    course = context.current_course()
    if course not in courses:
        course = next(iter(courses))

    solution = None
    while True:
        state = _resolve_state(course)
        rows = _hub_rows(course, courses[course], state)
        where = f"Aufgabe {state['task']}" if state["task"] is not None else "keine Aufgabe"
        header = f"{courses[course]} · {where}"
        choice = menu.pick(header, [label for label, _ in rows])
        if choice is None:
            return
        action = next((a for label, a in rows if label == choice), None)
        if action is None:
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
                context.set_course(course, sheet=picked["sheet_id"], task=first)
            continue
        if action == "task":
            if not state["sheet"]:
                notify.send("Kein Aufgabenblatt",
                            "Erst ein Blatt einlesen ('Neue Blaetter einlesen').",
                            glyph="⚠️")
                continue
            picked = _pick_task(state["sheet"], state["task"])
            if picked is not None:
                context.set_course(course, sheet=state["sheet"]["sheet_id"], task=picked)
            continue
        if action == "proofs":
            context.set_course(course, proofs=not state["proofs"])
            continue
        if action == "sections":
            entries = store.load_knowledge(course)
            if not entries:
                notify.send("Keine Wissensbasis",
                            f"Fuer '{courses[course]}' ist noch kein Skript eingelesen.",
                            glyph="⚠️")
                continue
            picked = _pick_sections(entries, store.load_sections(course),
                                    state["sections"])
            if picked is not None:
                sections, proofs, algorithms = picked
                context.set_course(course, sections=sections, proofs=proofs,
                                   algorithms=algorithms)
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
    try:
        return uniconfig.load(getattr(args, "config", None))
    except uniconfig.ConfigError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def cmd_config(args):
    if args.action == "init":
        target = Path(args.config).expanduser() if args.config else paths.CONFIG_FILE
        if target.exists() and not args.force:
            print(f"{target} existiert bereits. Mit --force ueberschreiben.", file=sys.stderr)
            sys.exit(1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(STARTER_CONFIG, encoding="utf-8")
        _print(f"Vorlage angelegt: {target}")
        _print("Jetzt Kurse und Dateinamen eintragen, dann: assignmentvibe sort")
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
        print(f"Downloads-Ordner nicht gefunden: {cfg.downloads}", file=sys.stderr)
        sys.exit(1)

    items, ignored = sorter.plan(cfg)
    _print(sorter.format_plan(cfg, items, ignored))

    if not args.apply:
        if not any(i.status in (sorter.NEW, sorter.REPLACE) for i in items):
            # Distinct exit code so bin/uni-sort can skip the "move it?" prompt
            # when there is nothing to move.
            sys.exit(NOTHING_TO_DO)
        _print("\n(Vorschau - nichts veraendert. Mit --apply wirklich verschieben.)")
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
        _print(f"Launcher aktualisiert: {len(written)} Eintraege.")
        return
    for name in written:
        _print(f"  {name}")
    for name in removed:
        _print(f"  entfernt: {name}")
    if not written:
        _print("Keine Eintraege erzeugt - passen die Dateinamen in der Config "
               "zu dem, was in den Kurs-Ordnern liegt? (assignmentvibe config show)")
    else:
        _print(f"\n{len(written)} Eintraege in {paths.APPLICATIONS_DIR}. "
               f"Mit Super+Space suchbar.")


# --- Script context: which sections of the script go into the prompt --------

DONE_LABEL = "── FERTIG ──"
PROOF_LABEL = "── Beweise: {state} ──"
ALGO_LABEL = "── Algorithmen: {state} ──"


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


def _section_tree(entries: list[dict], nodes: list[dict], selected: set[str],
                  include_algorithms: bool = False,
                  max_rows: int = MAX_PICKER_ROWS) -> list[tuple[str, str]]:
    """(menu label, section key) for the nodes of the script's outline that have
    statements beneath them, indented by depth and cut off at the depth that
    fits the row and chunk budgets (max_rows=0 shows all of them).

    Parents are offered alongside their children, so "give me all of chapter 3"
    is one keystroke rather than four - selection.entries_in treats a parent key
    as everything nested under it. Nodes with nothing in them are left out; a
    bibliography or a foreword is not something to hand to the model."""
    from .core import selection, toc

    grouped = selection.group_by_section(entries, include_algorithms)
    titles = {n["key"]: n["title"] for n in nodes if n.get("title")}

    filled = []
    for node in nodes:
        inside = [e for k, v in grouped.items() if selection.covers(node["key"], k)
                  for e in v]
        if inside:
            # The size the row actually costs a prompt, which is the formatted
            # statements without their proofs - not the raw entries.
            size = sum(len(format_knowledge_entry(e, include_proof=False)) + 1
                       for e in inside)
            filled.append((node, len(inside), size))

    depth = (_display_depth([(n["level"], size) for n, _, size in filled], max_rows)
             if max_rows else None)

    rows = []
    for node, count, size in filled:
        if depth is not None and node["level"] > depth:
            continue
        key = node["key"]
        mark = "✓" if any(selection.covers(s, key) for s in selected) else " "
        indent = "   " * (node["level"] - 1)
        # Without an outline there are no titles, only numbers - and then the
        # row has to say what the number counts.
        if titles:
            name = toc.label(titles, key)
        else:
            name = f"{'Kapitel' if node['level'] == 1 else 'Abschnitt'} {key}"
        rows.append((f"[{mark}] {indent}{name}  ({count}, {size // 1000}k)", key))
    return rows


def _pick_sections(entries: list[dict], nodes: list[dict],
                   preselected: list[str]) -> tuple[list[str], bool, bool] | None:
    """The selection loop. Returns (sections, include_proofs, include_algorithms),
    or None if the user aborted. A loop rather than a multi-select widget because
    the picker chain (Walker, wofi, fzf, stdin) only ever returns ONE choice -
    see integrations/menu.py."""
    from .core import selection, toc

    selected = set(preselected)
    include_proofs = False
    include_algorithms = False

    while True:
        rows = _section_tree(entries, nodes, selected, include_algorithms)
        chosen_entries = selection.entries_in(entries, sorted(selected),
                                              include_algorithms)
        size = sum(len(e["text"]) for e in chosen_entries)
        proof_label = PROOF_LABEL.format(state="an" if include_proofs else "aus")
        algo_label = ALGO_LABEL.format(state="an" if include_algorithms else "aus")
        done_label = f"── FERTIG: {len(chosen_entries)} Aussagen, {size} Zeichen ──"

        labels = [done_label, proof_label, algo_label] + [label for label, _ in rows]
        choice = menu.pick("Skript-Kontext", labels)

        if choice is None:
            return None
        if choice == done_label:
            return (sorted(selected, key=toc.sort_key), include_proofs,
                    include_algorithms)
        if choice == proof_label:
            include_proofs = not include_proofs
            continue
        if choice == algo_label:
            include_algorithms = not include_algorithms
            continue

        key = next((k for label, k in rows if label == choice), None)
        if key is None:
            continue
        # Toggling a parent clears its children too, so the two cannot disagree
        # about what is selected.
        if key in selected:
            selected.discard(key)
        else:
            selected.add(key)
            selected -= {s for s in list(selected)
                         if s != key and selection.covers(key, s)}


def cmd_sections(args):
    from . import store
    from .core import selection

    course = args.course or context.get().get("course")
    if not course:
        print("Kein Kurs angegeben (--course) und kein Kontext gesetzt.", file=sys.stderr)
        sys.exit(1)

    entries = store.load_knowledge(course)
    if not entries:
        print(f"Keine Wissensbasis fuer '{course}'. Erst 'ingest-script' ausfuehren.",
              file=sys.stderr)
        sys.exit(1)

    nodes = store.load_sections(course)
    for label, _key in _section_tree(entries, nodes, set(), args.algorithms,
                                     max_rows=0 if args.all else MAX_PICKER_ROWS):
        _print(label.replace("[ ] ", "  ", 1))
    total = len(selection.statements(entries, args.algorithms))
    kinds = "Definitionen/Saetze" + ("/Algorithmen" if args.algorithms else "")
    _print(f"\n{total} Aussagen ({kinds}) von {len(entries)} Eintraegen gesamt, "
           f"{len(nodes)} Abschnitte.")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="assignmentvibe")
    sub = p.add_subparsers(dest="command", required=True)

    p_cfg = sub.add_parser("config", help="Semester-Konfiguration")
    p_cfg.add_argument("action", choices=["show", "init", "path"], nargs="?", default="show")
    p_cfg.add_argument("--config", default=None, help="andere Config-Datei benutzen")
    p_cfg.add_argument("--force", action="store_true", help="bei 'init' ueberschreiben")
    p_cfg.set_defaults(func=cmd_config)

    p_sort = sub.add_parser("sort", help="Downloads laut Config in ~/Uni einsortieren")
    p_sort.add_argument("--apply", action="store_true", help="wirklich verschieben (sonst nur Vorschau)")
    p_sort.add_argument("--mode", choices=["move", "copy"], default="move")
    p_sort.add_argument("--config", default=None)
    p_sort.add_argument("--no-launcher", action="store_true",
                        help="nach --apply die Launcher-Eintraege nicht aktualisieren")
    p_sort.set_defaults(func=cmd_sort)

    p_launch = sub.add_parser("launcher", help="Kurse in die Super+Space-Suche eintragen")
    p_launch.add_argument("--config", default=None)
    p_launch.set_defaults(func=cmd_launcher)

    p_org = sub.add_parser("organize", help="Downloads-Ordner in die Bibliotheks-Struktur sortieren")
    p_org.add_argument("source", help="Ordner, der durchsucht wird (z.B. ~/Downloads)")
    p_org.add_argument("--target", default=None,
                        help=f"Ziel-Bibliothek (default: {paths.DEFAULT_LIBRARY_DIR})")
    p_org.add_argument("--apply", action="store_true", help="Tatsaechlich verschieben/kopieren (sonst nur Vorschau)")
    p_org.add_argument("--mode", choices=["copy", "move"], default="copy")
    p_org.add_argument("--ingest", action="store_true",
                        help="Nach --apply automatisch in die Wissensbasis einlesen")
    p_org.set_defaults(func=cmd_organize)

    p_is = sub.add_parser("ingest-script", help="Skript-PDF -> Wissensbasis")
    p_is.add_argument("pdf")
    p_is.add_argument("--course", required=True)
    p_is.set_defaults(func=cmd_ingest_script)

    p_ish = sub.add_parser("ingest-sheet", help="Aufgabenblatt-PDF einlesen")
    p_ish.add_argument("pdf")
    p_ish.add_argument("--course", required=True)
    p_ish.set_defaults(func=cmd_ingest_sheet)

    p_courses = sub.add_parser("courses", help="Kurse auflisten")
    p_courses.set_defaults(func=cmd_courses)

    p_sheets = sub.add_parser("sheets", help="Aufgabenblaetter auflisten")
    p_sheets.add_argument("--course", default=None, help="Kurs-Slug filtern")
    p_sheets.set_defaults(func=cmd_sheets)

    p_sec = sub.add_parser("sections", help="Skript-Abschnitte eines Kurses auflisten")
    p_sec.add_argument("--course", default=None, help="Kurs-Slug (default: aktueller Kontext)")
    p_sec.add_argument("--algorithms", action="store_true", help="Algorithmen mitzaehlen")
    p_sec.add_argument("--all", action="store_true",
                       help="Vollen Baum zeigen, nicht nur die Ebenen des Pickers")
    p_sec.set_defaults(func=cmd_sections)

    p_tasks = sub.add_parser("tasks", help="Aufgaben eines Blatts auflisten")
    p_tasks.add_argument("sheet_id")
    p_tasks.set_defaults(func=cmd_tasks)

    p_ctx = sub.add_parser("context", help="Aktueller Kontext")
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
                        help="Skript-Abschnitte, z.B. --sections 3.1 3.2 (oder '3' fuer ein ganzes Kapitel)")
        pb.add_argument("--proofs", action="store_true", default=None,
                        help="Beweise mitgeben (Standard: aus bei hint/next_step)")
        pb.add_argument("--algorithms", action="store_true", default=None,
                        help="Algorithmen mitgeben (Standard: aus)")
        pb.set_defaults(func=fn)

    p_fu = sub.add_parser("followup", help="Typische Nachfrage in die Zwischenablage kopieren")
    p_fu.set_defaults(func=cmd_followup)

    p_pick = sub.add_parser("pick", help="Das Hub-Menue (fuer den Top-Bar-Klick)")
    p_pick.add_argument("--config", default=None, help="andere Config-Datei benutzen")
    p_pick.add_argument("--provider", default="claude",
                        choices=["claude", "chatgpt", "gemini"],
                        help="Welcher Chat bei 'Chat oeffnen' aufgeht")
    p_pick.set_defaults(func=cmd_pick)

    p_wb = sub.add_parser("waybar-status", help="JSON-Status fuers Waybar-Custom-Modul")
    p_wb.set_defaults(func=cmd_waybar_status)

    p_ob = sub.add_parser("open-browser", help="Chat-Webseite oeffnen")
    p_ob.add_argument("--provider", default="claude", choices=["claude", "chatgpt", "gemini"])
    p_ob.set_defaults(func=cmd_open_browser)

    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
