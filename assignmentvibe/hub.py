"""
The hub: where you stand (course, sheet, task, the context chosen for it) and
everything that changes it or acts on it. Both front ends share it - the panel
in the Omarchy bar (through assignmentvibe.api) and the terminal commands in
cli.py - so a Jev pick or a copied prompt is the same thing from either.

Everything a person should hear about goes through `say`. From the terminal
that is a desktop notification; the panel collects the messages instead and
shows them where the click happened (see collect_messages), since a toast in
the corner is easy to miss while looking at the panel.

State is remembered per course in assignmentvibe.context; a sheet's plan
(effort per task, and every task's context) in store.save_plan.
"""

import contextvars
from pathlib import Path

from . import context, paths


# --- Feedback ------------------------------------------------------------------

_sink: contextvars.ContextVar = contextvars.ContextVar("hub_messages", default=None)

GLYPH_LEVELS = {"⚠": "warn", "✓": "ok", "⟳": "progress"}


def say(headline: str, body: str = "", glyph: str = "\U000f0dc9",
        desktop: bool = False) -> None:
    """Tell the user something. `desktop` also sends it as a notification when
    the panel is collecting - for results that outlive the panel, like a
    copied prompt: the panel closes on the click that copies it."""
    sink = _sink.get()
    if sink is None or desktop:
        from .integrations import notify
        notify.send(headline, body, glyph=glyph)
    if sink is not None:
        sink.append({"title": headline, "body": body,
                     "level": GLYPH_LEVELS.get(glyph, "info")})


class collect_messages:
    """`with collect_messages() as messages:` - what `say` is told inside the
    block lands in the list instead of a notification. Per thread: the panel's
    long jobs run beside its quick ones."""

    def __enter__(self) -> list[dict]:
        self.messages: list[dict] = []
        self._token = _sink.set(self.messages)
        return self.messages

    def __exit__(self, *exc) -> None:
        _sink.reset(self._token)


# --- Settings -----------------------------------------------------------------

_loaded_settings: dict | None = None
_settings_mtime: float | None = None


def settings() -> dict:
    """settings.json, or its defaults when it is broken - a typo there should
    not take the whole panel down. Read again when the file changes, since the
    panel's backend runs for the whole session."""
    global _loaded_settings, _settings_mtime
    try:
        mtime = paths.SETTINGS_FILE.stat().st_mtime
    except OSError:
        mtime = None
    if _loaded_settings is None or mtime != _settings_mtime:
        _loaded_settings = _read_settings()
        _settings_mtime = mtime
    return _loaded_settings


def _read_settings() -> dict:
    from . import settings as settings_module

    try:
        return settings_module.load()
    except settings_module.SettingsError as e:
        say("settings.json ignored", str(e), glyph="⚠")
        return dict(settings_module.DEFAULTS)


def count(items, noun: str) -> str:
    n = items if isinstance(items, int) else len(items)
    return f"{n} {noun}{'' if n == 1 else 's'}"


# --- Where you stand ------------------------------------------------------------

def semester_courses(cfg) -> dict[str, str]:
    """slug -> display name for the active semester's courses, in config order.

    The config is the authority on what is current; the knowledge base only
    knows what has ever been ingested, which includes last year's courses."""
    from . import store
    return {store.slug_for(c.name): c.name for c in cfg.active_courses()}


def latest_sheet(sheets: list[dict]) -> dict | None:
    """The newest sheet of a course - by sheet number, falling back to the id.
    This is the one you are working on; older ones are rarely wanted again."""
    if not sheets:
        return None
    return max(sheets, key=lambda s: (s.get("sheet_number") or 0, s["sheet_id"]))


def sheet_order(s: dict) -> tuple:
    return (s.get("sheet_number") or 0, s["sheet_id"])


def resolve_state(course: str) -> dict:
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
             or latest_sheet(sheets))
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
        "algorithms": bool(saved.get("algorithms", settings()["algorithms_by_default"])),
        "sheets": sheets,
        "exercises": store.load_exercises(course),
    }


def task_of(state: dict) -> dict | None:
    sheet = state.get("sheet")
    if not sheet or state.get("task") is None:
        return None
    return next((t for t in sheet["tasks"] if t["number"] == state["task"]), None)


def task_title(task: dict, exercises: list[dict]) -> str | None:
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


def task_ref(sheet_id: str | None, task: int | None) -> str | None:
    return f"{sheet_id}#{task}" if sheet_id and task is not None else None


def select_task(course: str, sheet_id: str, task: int | None) -> None:
    """Stand on a task - and, where the sheet has a plan, on the context
    selection kept for that task: what Jev picked for it, or what was made of
    that by hand since (see remember_selection)."""
    from . import store

    context.set_course(course, sheet=sheet_id, task=task)
    plan = store.load_plan(sheet_id)
    planned = (plan or {}).get("tasks", {}).get(str(task))
    if planned and planned.get("selection"):
        context.set_course(course, **planned["selection"])


def select_sheet(course: str, sheet: dict) -> None:
    """A different sheet invalidates the task number, not the chapters."""
    first = sheet["tasks"][0]["number"] if sheet["tasks"] else None
    select_task(course, sheet["sheet_id"], first)


# What a task's selection is made of, as context.set_course stores it, with
# what goes in when a key was never set. "jev_pick" says which task Jev picked
# the selection for, and whether it was changed by hand since.
SELECTION_KEYS = {"sections": [], "statements": [], "proof_of": [], "proofs": False,
                  "earlier_tasks": [], "jev_pick": None}


def selection_key(entries: list[dict], state: dict) -> tuple:
    """What a selection amounts to, to tell whether an edit changed it - the
    same statements count as the same, however they were grouped."""
    from .core import selection
    from .core.prompts import entry_id

    ids = {entry_id(e) for e in selection.chosen(entries, state["sections"],
                                                 state["statements"], True)}
    return (frozenset(ids), frozenset(state["proof_of"]), state["proofs"],
            frozenset(state["earlier"]))


def remember_selection(course: str) -> None:
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


def set_selection(course: str, ids: set[str], proof_of: list[str], proofs: bool,
                  earlier: list[str], algorithms: bool | None = None) -> None:
    """Store an edited selection: statement ids, turned back into sections plus
    single statements (selection.compress), so the prompt says "section 3.1"
    rather than eleven numbers. A selection Jev made is marked as changed by
    hand when it really changed."""
    from . import store
    from .core import selection

    state = resolve_state(course)
    entries = store.load_knowledge(course)
    if algorithms is None:
        algorithms = state["algorithms"]
    sections, singles = selection.compress(entries, set(ids), algorithms)
    before = selection_key(entries, state)
    context.set_course(course, sections=sections, statements=singles, proofs=bool(proofs),
                       algorithms=algorithms, proof_of=list(proof_of),
                       earlier_tasks=list(earlier))
    jev_pick = state.get("jev_pick")
    if jev_pick and before != selection_key(entries, resolve_state(course)):
        context.set_course(course, jev_pick={**jev_pick, "edited": True})
    remember_selection(course)


def set_algorithms(course: str, on: bool) -> None:
    """Algorithms on or off. Through sections, so a whole chapter gains or
    loses its algorithms, while one picked by name stays."""
    from . import store
    from .core import selection
    from .core.prompts import entry_id

    state = resolve_state(course)
    entries = store.load_knowledge(course)
    ids = {entry_id(e) for e in selection.chosen(entries, state["sections"],
                                                 state["statements"], on)}
    context.set_course(course, algorithms=on)
    set_selection(course, ids, state["proof_of"], state["proofs"], state["earlier"], on)


def clear_selection(course: str) -> None:
    set_selection(course, set(), [], False, [])


# --- Earlier sheets ----------------------------------------------------------------

def earlier_candidates(sheets: list[dict], sheet: dict | None,
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


# --- Jev ---------------------------------------------------------------------------

def judge_task(task: dict, knowledge: list[dict], exercises: list[dict],
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


def from_judgement(judged: tuple[dict, dict, dict], knowledge: list[dict],
                   include_algorithms: bool, candidates: dict[str, tuple[str, str]]
                   ) -> tuple[list[str], list[str], list[str], list[str]]:
    """Jev's answers made a selection: (statement ids, proof ids, proofs
    dropped for length, earlier task refs). Over settings' max_context_chars,
    the least certain proofs go first; the statements stay, since those are
    what the solution has to cite."""
    from .core import selection

    statement_p, proof_p, earlier_p = judged
    config = settings()
    statements, proofs = selection.pick_from_judgement(
        statement_p, proof_p, config["jev_statement_threshold"],
        config["jev_proof_threshold"])
    entries = selection.chosen(knowledge, [], statements, include_algorithms)
    proofs, dropped = selection.trim_proofs(entries, proofs, proof_p,
                                            config["max_context_chars"])
    earlier = [candidates[label][0] for label, p in earlier_p.items()
               if p >= config["jev_statement_threshold"]]
    return statements, proofs, dropped, earlier


def jev_pick(task: dict, knowledge: list[dict], exercises: list[dict],
             include_algorithms: bool = False, sheets: list[dict] | None = None,
             sheet: dict | None = None
             ) -> tuple[list[str], list[str], list[str], list[str]] | None:
    """(statement ids, proof ids, proofs dropped for length, earlier task refs)
    Jev judges the task to need, or None when it could not be asked - said
    through `say`, since the user pressed for it. Earlier tasks are those of
    the course's sheets before `sheet`."""
    from .integrations import jev

    candidates = earlier_candidates(sheets or [], sheet, exercises)
    try:
        judged = judge_task(task, knowledge, exercises, include_algorithms, candidates)
    except jev.JevUnavailable as e:
        say("Jev unavailable", f"The selection is unchanged. {e}", glyph="⚠")
        return None
    return from_judgement(judged, knowledge, include_algorithms, candidates)


def jev_into_state(course: str, state: dict) -> bool:
    """Let Jev pick for the current task, and make that the course's selection.
    It replaces what was chosen before, chapters included: Jev looks at the
    whole script, so keeping the old chapters would add back what it left out."""
    from . import store
    from .core import selection
    from .core.prompts import context_size
    from .integrations import jev

    knowledge = store.load_knowledge(course)
    # Without lecture notes there are still the earlier sheets to look at -
    # Numerik and Statistik hand out sheets but no script.
    if not knowledge and not selection.earlier_sheets(state["sheets"], state["sheet"]):
        say("No knowledge base", "Read the lecture notes in first.", glyph="⚠")
        return False
    if task_of(state) is None:
        say("No task", "Pick a task first.", glyph="⚠")
        return False
    say("Asking Jev", "Which statements, proofs and earlier tasks does "
        "this task need?", glyph="⟳")
    picked = jev_pick(task_of(state), knowledge, state["exercises"],
                      state["algorithms"], state["sheets"], state["sheet"])
    if picked is None:
        return False

    statements, proofs, dropped, earlier = picked
    sections, singles = selection.compress(knowledge, set(statements),
                                           state["algorithms"])
    sheet_id = state["sheet"]["sheet_id"] if state.get("sheet") else None
    context.set_course(course, sections=sections, statements=singles,
                       proof_of=proofs, proofs=False, earlier_tasks=earlier,
                       jev_pick={"task": task_ref(sheet_id, state.get("task")),
                                 "edited": False})
    remember_selection(course)
    state = {"sections": sections, "statements": singles, "proof_of": proofs,
             "earlier": earlier}
    lines = selection_lines(course, state, limit=12)
    if dropped:
        limit = settings()["max_context_chars"]
        shown = ", ".join(dropped[:4]) + (f" +{len(dropped) - 4} more"
                                          if len(dropped) > 4 else "")
        lines.append(f"{count(dropped, 'proof')} left out to stay under "
                     f"{limit // 1000}k characters, least certain first: {shown}")
        size = context_size(selection.chosen(knowledge, [], statements, True),
                            False, proofs)
        if size > limit:
            lines.append(f"⚠ Still {size // 1000}k characters without any proof")
    title = f"Jev picked {count(statements, 'statement')}, {count(proofs, 'proof')}"
    if earlier:
        title += f", {count(earlier, 'earlier task')}"
    say(title, "\n".join(lines + ["", jev.usage_summary()]), glyph="✓")
    return True


def plan_sheet(course: str, state: dict) -> dict | None:
    """Ask Jev once about the whole current sheet, save it, and say what it is.

    Two steps. First, per task and side by side, the same pick as for a single
    task - statements, proofs, earlier tasks - which becomes that task's
    context selection: going to a task later sets it without asking again.
    Then one request with every task and its statements, asking how much work
    each is and which builds on which. The context matters there: without it
    Jev rated "Beweise Teil a) des Satzes 1.26" a few lines; seeing what Satz
    1.26 says, it rated it a page. None if Jev could not be asked."""
    from concurrent.futures import ThreadPoolExecutor

    from . import store
    from .core import plan as plan_core
    from .core import selection
    from .core.prompts import task_query
    from .integrations import jev

    sheet, exercises = state["sheet"], state["exercises"]
    if not sheet or not sheet["tasks"]:
        say("No sheet", "Read a sheet in first ('Read in new sheets').", glyph="⚠")
        return None
    name = sheet.get("sheet_number") or sheet["sheet_id"]
    say("Asking Jev", f"The context of every task of sheet {name}, how much "
        "work each is, and what builds on what.", glyph="⟳")
    knowledge = store.load_knowledge(course)
    algorithms = state["algorithms"]
    items = selection.judgement_items(knowledge, algorithms)
    candidates = earlier_candidates(state["sheets"], sheet, exercises)
    usages: list = []

    def pick(task):
        judged = judge_task(task, knowledge, exercises, algorithms, candidates, usages)
        return judged, from_judgement(judged, knowledge, algorithms, candidates)

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
        say("Jev unavailable", f"No plan made. {e}", glyph="⚠")
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
                          "jev_pick": {"task": task_ref(sheet["sheet_id"], task["number"]),
                                       "edited": False}},
            "dropped": dropped,
        }
    plan = {"format": store.PLAN_FORMAT, "sheet_id": sheet["sheet_id"],
            "tasks_key": store.tasks_key(sheet), "tasks": tasks,
            "edges": [list(e) for e in edges], "cost_usd": total["last"]["cost_usd"]}
    store.save_plan(plan)
    select_task(course, sheet["sheet_id"], state["task"])
    say(f"Sheet {name} planned",
        "\n".join(plan_lines(plan, course) + ["", jev.usage_summary(total)]), glyph="✓")
    return plan


def plan_lines(plan: dict, course: str) -> list[str]:
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
        parts = [count(statements, "statement")] if statements else []
        if chosen.get("proof_of"):
            parts.append(count(chosen["proof_of"], "proof"))
        if chosen.get("earlier_tasks"):
            parts.append(count(chosen["earlier_tasks"], "earlier task"))
        what = f" · {', '.join(parts)}" if parts else ""
        lines.append(f"Task {n}  {plan_core.effort_bars(planned['effort'])} "
                     f"{plan_core.effort_word(planned['effort'])}{what}")
    lines.append(f"Dependencies: {plan_core.dependency_text(edges)}")
    return lines


# --- What the selection is, in words ---------------------------------------------

def statement_label(e: dict, width: int = 48) -> str:
    from .core.prompts import entry_id

    # The number alone says nothing ("Satz 3.1.5"), so the label carries what
    # the statement is about: its name if it has one, else how it begins.
    about = e.get("name") or " ".join(e["text"].split())
    if len(about) > width:
        about = about[:width - 1] + "…"
    return f"{entry_id(e)}  {about}"


def selection_lines(course: str, state: dict, limit: int = 0) -> list[str]:
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
        label = statement_label(by_id[i]) if i in by_id else i
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


# --- Acting on it --------------------------------------------------------------------

def build_current_prompt(course: str, course_name: str, state: dict,
                         solution: str | None = None) -> str:
    from . import store
    from .core import selection
    from .core.prompts import build_prompt

    return build_prompt(
        task_of(state), state["sheet"], store.load_knowledge(course), solution, course_name,
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


def copy_prompt(course: str, course_name: str, state: dict,
                solution: str | None = None) -> int | None:
    """Build the prompt and put it on the clipboard. Its length, or None when
    there is no task to build it for."""
    from .core.prompts import resolve_exercises
    from .integrations import clipboard

    task = task_of(state)
    if task is None:
        say("No task", "Pick a task first.", glyph="⚠")
        return None
    prompt = build_current_prompt(course, course_name, state, solution)
    ok, method = clipboard.copy(prompt)
    _, missing = resolve_exercises(task, state["exercises"])
    if missing:
        # The prompt still goes out - the reference is in it - but without the
        # exercise the model has nothing to solve, and that must not be silent.
        say("Exercise not found",
            f"Aufgabe {', '.join(missing)} is not in the read-in lecture notes. "
            "Paste it into the chat yourself, or read the notes in again.",
            glyph="⚠", desktop=True)
    if ok:
        say(f"Task {state['task']} copied",
            f"{len(prompt)} characters - paste it into the chat.", glyph="", desktop=True)
    else:
        say("Prompt built", f"No clipboard available, saved to: {method}", glyph="⚠",
            desktop=True)
    return len(prompt)


def copy_text(text: str, headline: str) -> bool:
    from .integrations import clipboard

    ok, method = clipboard.copy(text)
    if ok:
        say(headline, "Copied to clipboard.", glyph="", desktop=True)
    else:
        say(headline, f"No clipboard available: {method}", glyph="⚠", desktop=True)
    return ok


CHAT_URLS = {
    "claude": "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com",
    "gemini": "https://gemini.google.com/app",
}


def open_chat(provider: str | None = None) -> bool:
    import shutil
    import subprocess

    url = CHAT_URLS.get(provider or "claude", CHAT_URLS["claude"])
    for launcher in ("omarchy-launch-webapp", "xdg-open"):
        if shutil.which(launcher):
            subprocess.Popen([launcher, url], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    say("No browser launcher found", f"Open it yourself: {url}", glyph="⚠")
    return False


def sheet_pdf(sheet: dict) -> Path | None:
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


def open_sheet(sheet: dict) -> bool:
    """Open the sheet's PDF in the configured viewer (Firefox by default)."""
    import shlex
    import subprocess

    from . import uniconfig

    path = sheet_pdf(sheet)
    if path is None:
        say("Sheet not found", f"{sheet.get('source')} is not in the course folder "
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
        say("Could not open the sheet", f"{viewer}: {e}", glyph="⚠")
        return False
    return True


def ingest(cfg) -> dict:
    from . import store

    say("Reading in", "Processing new lecture notes and sheets.", glyph="⟳")
    result = store.ingest_missing(cfg)
    parts = []
    if result["scripts"]:
        parts.append(f"{len(result['scripts'])} lecture note(s)")
    if result["sheets"]:
        parts.append(f"{len(result['sheets'])} sheet(s)")
    if result["errors"]:
        say("Read in with errors", "\n".join(result["errors"][:3]), glyph="⚠")
    elif parts:
        say("Read in", ", ".join(parts), glyph="✓")
    else:
        say("Nothing new", "Every sheet this semester has already been read in.")
    return result


# --- Config files ------------------------------------------------------------------

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


def config_files() -> list[tuple[str, str, Path]]:
    """(name, what it is for, path) for every file the tool reads that is meant
    to be edited, in the order they matter."""
    files = [
        ("uni.json", "Semester, courses, and where their PDFs are", paths.CONFIG_FILE),
        ("settings.json", "Context length, Jev thresholds, algorithms",
         paths.SETTINGS_FILE),
        ("openrouter.key", "API key for Jev", paths.OPENROUTER_KEY_FILE),
    ]
    if paths.JEV_USAGE_FILE.exists():
        files.append(("jev_usage.json", "Jev's cost counter - empty it to start at $0",
                      paths.JEV_USAGE_FILE))
    return files


def open_config_file(name: str) -> bool:
    """Open one of config_files() in the editor. A file that is not there yet
    starts out as a template that explains itself - an empty buffer says
    nothing."""
    from . import settings as settings_module
    from .integrations import editor

    path = next((p for n, _, p in config_files() if n == name), None)
    if path is None:
        say("Unknown file", name, glyph="⚠")
        return False
    if path == paths.CONFIG_FILE and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STARTER_CONFIG, encoding="utf-8")
    elif path == paths.SETTINGS_FILE:
        settings_module.ensure_file()
    elif path == paths.OPENROUTER_KEY_FILE and not path.exists():
        # Created here rather than by the editor, so it is private from the
        # first byte instead of world-readable until someone runs chmod.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)

    if not editor.open_file(path):
        say("No editor found", f"Open it yourself: {path}", glyph="⚠")
        return False
    return True
