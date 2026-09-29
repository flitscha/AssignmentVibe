"""
Manages the scripts and assignment sheets the user has ingested, under
~/.local/share/assignmentvibe/. A thin layer over the core/ processing
engine (pdf_text/knowledge/assignments) - that does the actual PDF work,
this module is only concerned with "where does what live" and "which course
does it belong to".

Depends on assignmentvibe.core and assignmentvibe.paths.
"""

import json
import re
from pathlib import Path

from . import paths

# The extraction modules are imported by the two functions that ingest a PDF.
# Everything else here only reads JSON that was written earlier, and the bar
# polls one of those readers every few seconds.


def slug_for(name: str) -> str:
    """The key a course is filed under. The config names courses ("Parallele
    Programmierung"), everything stored names them by slug, and this is the one
    place that bridges the two."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "course"


_slugify = slug_for  # kept for readability at the existing call sites


# Reading the same file twice in one run is the normal case, not an edge one:
# building a single hub row wants the entries AND the section titles, which live
# in one 166KB document. Keyed by path and mtime, so a re-ingest inside the same
# process is still picked up.
_JSON_CACHE: dict[tuple[str, float], object] = {}


def _load_json(path: Path, default):
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return default
    if key not in _JSON_CACHE:
        _JSON_CACHE.clear()
        _JSON_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
    return _JSON_CACHE[key]


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def list_courses() -> dict:
    return _load_json(paths.COURSES_FILE, {})


def _register_course(slug: str, display_name: str) -> None:
    courses = list_courses()
    courses[slug] = display_name
    _save_json(paths.COURSES_FILE, courses)


def ingest_script(pdf_path: Path, course_name: str) -> dict:
    from .core import knowledge as knowledge_core
    from .core import pdf_text

    """PDF script -> knowledge base. Returns stats (for CLI output)."""
    paths.ensure_dirs()
    slug = _slugify(course_name)
    _register_course(slug, course_name)

    raw_path = paths.RAW_TEXT_CACHE_DIR / f"{slug}.json"
    knowledge_path = paths.KNOWLEDGE_DIR / f"{slug}.json"

    pdf_text.extract_to_json(pdf_path, raw_path)
    # core.knowledge writes the section tree alongside the entries: which
    # chapter an entry belongs to is decided there, from the PDF's outline.
    knowledge_core.run(raw_path, knowledge_path, pdf_path)
    saved = _load_json(knowledge_path, {"entries": [], "sections": []})

    return {
        "course": course_name,
        "slug": slug,
        "entries": len(saved["entries"]),
        "knowledge_path": str(knowledge_path),
        "sections": len(saved["sections"]),
    }


def load_sections(course_slug: str) -> list[dict]:
    """A course's section tree: [{"key", "level", "title", "page"}, ...] in
    reading order. Empty for a script ingested before the tree existed."""
    path = paths.KNOWLEDGE_DIR / f"{course_slug}.json"
    return _load_json(path, {}).get("sections", [])


def load_section_titles(course_slug: str) -> dict[str, str]:
    """key -> title, for labelling. A script whose PDF had no bookmarks has
    keys but no titles, and the picker then shows the bare numbers."""
    return {n["key"]: n["title"] for n in load_sections(course_slug) if n.get("title")}


def ingest_sheet(pdf_path: Path, course_name: str) -> dict:
    from .core import assignments as assignments_core

    """Assignment sheet PDF -> structured tasks, tagged with its course."""
    paths.ensure_dirs()
    slug = _slugify(course_name)
    _register_course(slug, course_name)

    sheet_id = sheet_id_for(slug, pdf_path)
    out_path = paths.ASSIGNMENTS_DIR / f"{sheet_id}.json"

    result = assignments_core.parse_assignment_sheet(pdf_path)
    result["course_slug"] = slug
    result["sheet_id"] = sheet_id
    result["path"] = str(pdf_path.resolve())
    _save_json(out_path, result)

    # The same sheet as filed before ids carried the course.
    legacy = paths.ASSIGNMENTS_DIR / f"{pdf_path.stem}.json"
    if _load_json(legacy, {}).get("course_slug") == slug:
        legacy.unlink()

    return {
        "sheet_id": sheet_id,
        "course": course_name,
        "num_tasks": result["num_tasks"],
        "path": str(out_path),
    }


def sheet_id_for(course_slug: str, pdf_path: Path) -> str:
    """"analysis/Blatt1" - the course is part of the id, because file names
    are not unique across courses: in one semester Analysis and Numerik both
    hand out "Blatt1.pdf", and "A01.pdf" is a sheet in four courses. The id is
    also the path of the sheet's file under the assignments directory."""
    return f"{course_slug}/{pdf_path.stem}"


def list_sheets(course_slug: str | None = None) -> list[dict]:
    paths.ensure_dirs()
    pattern = f"{course_slug}/*.json" if course_slug else "*/*.json"
    return [_load_json(f, {}) for f in sorted(paths.ASSIGNMENTS_DIR.glob(pattern))]


def load_sheet(sheet_id: str) -> dict:
    path = paths.ASSIGNMENTS_DIR / f"{sheet_id}.json"
    if not path.exists() and "/" not in sheet_id:
        # An id remembered from before ids carried the course: "A07".
        found = list(paths.ASSIGNMENTS_DIR.glob(f"*/{sheet_id}.json"))
        if len(found) == 1:
            path = found[0]
    if not path.exists():
        raise FileNotFoundError(f"No assignment sheet with id '{sheet_id}'. "
                                 f"Read it in with 'ingest-sheet' first.")
    return _load_json(path, {})


# 2: each task carries its context selection
PLAN_FORMAT = 2


def save_plan(plan: dict) -> None:
    """A sheet's plan (see core.plan), filed like the sheet itself."""
    _save_json(paths.PLANS_DIR / f"{plan['sheet_id']}.json", plan)


def tasks_key(sheet: dict) -> str:
    """What a plan was made for: the sheet's tasks, number and text."""
    import hashlib

    text = json.dumps([(t["number"], t["text"]) for t in sheet.get("tasks", [])],
                      ensure_ascii=False)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def load_plan(sheet_id: str) -> dict | None:
    """The plan made for a sheet, or None. It holds while the sheet's tasks are
    the ones it was made for - a sheet read in again with the same tasks (a
    new version of the extraction) keeps its plan and the selections in it."""
    plan = _load_json(paths.PLANS_DIR / f"{sheet_id}.json", None)
    if plan is None or plan.get("format", 1) < PLAN_FORMAT:
        return None
    sheet = _load_json(paths.ASSIGNMENTS_DIR / f"{sheet_id}.json", None)
    if sheet is not None and plan.get("tasks_key") not in (None, tasks_key(sheet)):
        return None
    return plan


def load_knowledge(course_slug: str) -> list[dict]:
    path = paths.KNOWLEDGE_DIR / f"{course_slug}.json"
    if not path.exists():
        return []
    return _load_json(path, {"entries": []})["entries"]


def knowledge_source(course_slug: str) -> str | None:
    """The file name of the lecture notes a knowledge base was read from."""
    path = paths.KNOWLEDGE_DIR / f"{course_slug}.json"
    return _load_json(path, {}).get("source")


def load_exercises(course_slug: str) -> list[dict]:
    """The exercises the script itself carries (see core.exercises). Empty for
    a script ingested before these were extracted - re-ingesting it fills them."""
    path = paths.KNOWLEDGE_DIR / f"{course_slug}.json"
    return _load_json(path, {}).get("exercises", [])


def _matching_pdfs(cfg, course, category: str) -> list[Path]:
    """The course's files of one category, as they lie in the library."""
    import fnmatch

    directory = cfg.category_dir(course, category)
    if not directory.is_dir():
        return []
    patterns = course.patterns.get(category, [])
    found = [f for f in sorted(directory.glob("*.pdf"))
             if any(fnmatch.fnmatch(f.name.lower(), pat.lower()) for pat in patterns)]
    return found


def ingest_missing(cfg, progress=None) -> dict:
    """Read in whatever the active semester has that the knowledge base does
    not. Scripts and assignment sheets both, but only for the courses of the
    semester the config calls active - the point is one click after a download,
    not a rebuild of everything ever ingested.

    A sheet is only ever read once: its tasks do not change, and re-reading
    would throw away nothing but cost seconds per sheet. A script is re-read
    when its PDF is newer than what was made from it, which is how an annotated
    or corrected script replaces its earlier version. Both are re-read when they
    were made by an older version of the extraction (see the FORMAT constants
    in core.knowledge and core.assignments)."""
    from .core.assignments import FORMAT as SHEET_FORMAT
    from .core.knowledge import FORMAT as KNOWLEDGE_FORMAT

    known_sheets = {s["sheet_id"] for s in list_sheets()
                    if s.get("format", 1) >= SHEET_FORMAT}
    result = {"scripts": [], "sheets": [], "errors": []}

    for course in cfg.active_courses():
        slug = slug_for(course.name)

        script = _course_script(cfg, course)
        if script is not None:
            target = paths.KNOWLEDGE_DIR / f"{slug}.json"
            outdated = (not target.exists()
                        or target.stat().st_mtime < script.stat().st_mtime
                        or _load_json(target, {}).get("format", 1) < KNOWLEDGE_FORMAT)
            if outdated:
                if progress:
                    progress(f"Lecture notes: {course.name}")
                try:
                    ingest_script(script, course.name)
                    result["scripts"].append(course.name)
                except Exception as e:
                    result["errors"].append(f"{script.name}: {e}")

        for pdf in _matching_pdfs(cfg, course, "blaetter"):
            if sheet_id_for(slug, pdf) in known_sheets:
                continue
            if progress:
                progress(f"Sheet: {pdf.stem}")
            try:
                ingest_sheet(pdf, course.name)
                result["sheets"].append(pdf.stem)
            except Exception as e:
                result["errors"].append(f"{pdf.name}: {e}")

    return result


def _course_script(cfg, course) -> Path | None:
    """The one script PDF a course's knowledge base is built from.

    A course can have several: Modellierung ships the lecture notes twice, plain
    and annotated, and both match its "skript" patterns. One course is one
    knowledge base, so ingesting both would have them overwrite each other - and
    worse, each would then look outdated next to the file the other one wrote,
    so every run would redo both. The newest wins, which is also the one you
    want: an annotated or corrected script is the later file.

    (A course whose script genuinely comes in several parts - Analysis I and II
    as separate PDFs - is not handled by this. It would need the section keys of
    several PDFs merged into one tree, which is a different job.)"""
    candidates = _matching_pdfs(cfg, course, "skript")
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
