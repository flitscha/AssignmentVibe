"""
`assignmentvibe` CLI - the terminal side of the tool, and the backend of the
panel in the Omarchy bar (`serve`, see assignmentvibe.api and the QML at the root).

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
  followup [N]                                 list the canned replies, or copy number N
  open-browser [--provider ...]                   open the chat website
  serve                                            the panel's backend (JSON lines on stdin/stdout)
  api <cmd> [json-args]                             one panel request, from the terminal

There is one prompt mode: solve the task. The seven it replaces ("hint",
"explain the concept", "what next", ...) asked the reader to decide how much
of an answer they wanted BEFORE seeing one, which is the wrong moment - you
read the first step, get the idea, and stop. What those modes were for now
lives in the follow-ups, one click at the moment it is needed.

Everything interactive - picking a task, the context, Jev - lives in the panel
(Service.qml, Popup.qml, views/); the logic behind it is assignmentvibe.hub, shared with the commands
here.
"""

import json
import sys
from pathlib import Path

from . import context, hub, paths


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
        hub.select_task(course_slug, sheet["sheet_id"], int(task_num))
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
        algorithms = bool(saved.get("algorithms", hub.settings()["algorithms_by_default"]))

    statements = getattr(args, "statements", None)
    if statements is None and not getattr(args, "sections", None):
        statements = saved.get("statements")
    sheets = store.list_sheets(course_slug) if course_slug else []
    earlier = saved.get("earlier_tasks") or []
    part = getattr(args, "part", None)
    if part is None:
        part = (saved.get("parts") or {}).get(hub.task_ref(sheet["sheet_id"], int(task_num)))
    if getattr(args, "jev", False):
        picked = hub.jev_pick(task, knowledge, exercises, algorithms, sheets, sheet)
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
                        earlier_tasks=selection.earlier_tasks(sheets, earlier, sheet),
                        part=part)


def cmd_build(args):
    sys.stdout.reconfigure(encoding="utf-8")
    print(_build_from_args(args))


def cmd_copy(args):
    from .integrations import clipboard

    prompt = _build_from_args(args)
    ok, method = clipboard.copy(prompt)
    if ok:
        hub.say("Prompt copied", f"{len(prompt)} characters (via {method})", glyph="")
        _print(f"Copied to clipboard ({method}).")
    else:
        hub.say("No clipboard available", f"Prompt saved to: {method}", glyph="⚠")
        _print(f"No clipboard tool found. Prompt saved to: {method}")


def cmd_open_browser(args):
    if not hub.open_chat(getattr(args, "provider", None)):
        sys.exit(1)


def cmd_followup(args):
    """The canned replies: listed, or number N copied - the panel has them on
    its own tab, this is for the terminal."""
    from .core.prompts import FOLLOW_UPS

    if args.number is None:
        for n, (emoji, label, text) in enumerate(FOLLOW_UPS, 1):
            _print(f"{n:2}  {emoji} {label}")
        return
    if not 1 <= args.number <= len(FOLLOW_UPS):
        print(f"There are {len(FOLLOW_UPS)} follow-ups.", file=sys.stderr)
        sys.exit(1)
    emoji, label, text = FOLLOW_UPS[args.number - 1]
    if not hub.copy_text(text, f"{emoji} {label}"):
        sys.exit(1)


def cmd_work(args):
    """What the notebook of a sheet holds for a task: with --list how every
    pasted image was matched, else a PNG of the task's handwriting."""
    from . import store

    course = context.current_course()
    state = hub.resolve_state(course) if course else None
    sheet = store.load_sheet(args.sheet) if args.sheet else (state or {}).get("sheet")
    if not sheet:
        print("No sheet given (--sheet) and none current.", file=sys.stderr)
        sys.exit(1)
    course = sheet.get("course_slug") or course
    task = args.task or (state or {}).get("task")
    path = hub.notebook_for(course, sheet)
    if path is None:
        print(f"No .xopp for sheet {sheet.get('sheet_number')} in the course folder.",
              file=sys.stderr)
        sys.exit(1)
    if args.list:
        _, seen, found = hub.read_notebook(course, sheet, path)
        _print(path)
        for s in seen:
            what = (f"task {s['task']}{' ' + s['part'] + ')' if s['part'] else ''}"
                    if s["task"] else "-")
            _print(f"  p.{s['page'] + 1} img {s['image']}  {what:<12} {s['score']:.2f}  {s['text']}")
        for st in found:
            pages = sorted({p + 1 for p, _, _ in st["slices"]})
            _print(f"task {st['task']}{' ' + st['part'] + ')' if st['part'] else ''}: "
                   f"pages {pages}")
        return
    _, png, mine = hub.render_work(course, sheet, task)
    if png is None:
        print(f"Nothing written for task {task} in {path.name}.", file=sys.stderr)
        sys.exit(1)
    _print(png)


def cmd_serve(args):
    from . import api
    api.serve()


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


def cmd_jev(args):
    """The hub's Jev row from the terminal: pick for the current task and
    remember it, then print what was picked and the running totals."""
    from .integrations import jev

    if not args.usage:
        course = context.current_course()
        if not course:
            print("No current course - open the hub once first.", file=sys.stderr)
            sys.exit(1)
        state = hub.resolve_state(course)
        if hub.task_of(state) is None:
            print("No current task.", file=sys.stderr)
            sys.exit(1)
        if not hub.jev_into_state(course, state):
            sys.exit(1)
        for line in hub.selection_lines(course, hub.resolve_state(course)):
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
    state = hub.resolve_state(course)
    plan = (store.load_plan(state["sheet"]["sheet_id"]) if args.show and state["sheet"]
            else hub.plan_sheet(course, state))
    if not plan:
        sys.exit(1)
    for line in hub.plan_lines(plan, course):
        _print(line)


# --- Semester config, sorting and launcher entries -------------------------
# These three are the "everyday" commands and deliberately work without pymupdf
# installed (see the lazy imports above), so a fresh clone is usable right away.

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
        target.write_text(hub.STARTER_CONFIG, encoding="utf-8")
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
        if course.inhalt:
            _print(f"    {'inhalt':9} {' | '.join(course.inhalt)}  (first page)")


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

# How many rows `sections` shows without --all. Depth is spent where it buys
# something: a script whose chapters fit is listed by chapter, and only one
# that would otherwise show unusably large pieces is opened up further - the
# keys printed are what `build --sections` takes, and a parent key selects
# everything nested under it.
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
    """(label, section key) for the nodes of the script's outline that have
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
        pb.add_argument("--part", default=None, metavar="LABEL",
                        help="ask for one part of the task only, e.g. --part b "
                             "(default: as last chosen for the task)")
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

    p_fu = sub.add_parser("followup", help="list the canned follow-ups, or copy one")
    p_fu.add_argument("number", type=int, nargs="?", default=None)
    p_fu.set_defaults(func=cmd_followup)

    p_work = sub.add_parser("work", help="the handwritten work on a task, from its .xopp")
    p_work.add_argument("--sheet", default=None, help="a sheet id (default: the current one)")
    p_work.add_argument("--task", type=int, default=None)
    p_work.add_argument("--list", action="store_true",
                        help="show how the pasted statements were matched")
    p_work.set_defaults(func=cmd_work)

    p_serve = sub.add_parser("serve", help="the panel's backend: JSON lines on stdin/stdout")
    p_serve.set_defaults(func=cmd_serve)

    p_ob = sub.add_parser("open-browser", help="open the chat website")
    p_ob.add_argument("--provider", default="claude", choices=["claude", "chatgpt", "gemini"])
    p_ob.set_defaults(func=cmd_open_browser)

    return p


def main() -> None:
    # `api` takes its request as raw JSON, which argparse has no use for.
    if len(sys.argv) >= 2 and sys.argv[1] == "api":
        from . import api
        api.main(sys.argv[2:])
        return

    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
