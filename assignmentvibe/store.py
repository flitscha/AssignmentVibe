"""
Manages the scripts and assignment sheets the user has ingested, under
~/.local/share/assignmentvibe/. A thin layer over the core/ processing
engine (pdf_text/knowledge/assignments) - that does the actual PDF work,
this module is only concerned with "where does what live" and "which course
does it belong to".

Depends on assignmentvibe.core and assignmentvibe.paths.
"""

import fnmatch
import json
import re
from pathlib import Path

from . import paths
from .core import assignments as assignments_core
from .core import knowledge as knowledge_core
from .core import pdf_text


def slug_for(name: str) -> str:
    """The key a course is filed under. The config names courses ("Parallele
    Programmierung"), everything stored names them by slug, and this is the one
    place that bridges the two."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "course"


_slugify = slug_for  # kept for readability at the existing call sites


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
    """Assignment sheet PDF -> structured tasks, tagged with its course."""
    paths.ensure_dirs()
    slug = _slugify(course_name)
    _register_course(slug, course_name)

    sheet_id = pdf_path.stem
    out_path = paths.ASSIGNMENTS_DIR / f"{sheet_id}.json"

    result = assignments_core.parse_assignment_sheet(pdf_path)
    result["course_slug"] = slug
    result["sheet_id"] = sheet_id
    _save_json(out_path, result)

    return {
        "sheet_id": sheet_id,
        "course": course_name,
        "num_tasks": result["num_tasks"],
        "path": str(out_path),
    }


def list_sheets(course_slug: str | None = None) -> list[dict]:
    paths.ensure_dirs()
    sheets = []
    for f in sorted(paths.ASSIGNMENTS_DIR.glob("*.json")):
        data = _load_json(f, {})
        if course_slug and data.get("course_slug") != course_slug:
            continue
        sheets.append(data)
    return sheets


def load_sheet(sheet_id: str) -> dict:
    path = paths.ASSIGNMENTS_DIR / f"{sheet_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No assignment sheet with id '{sheet_id}'. "
                                 f"Read it in with 'ingest-sheet' first.")
    return _load_json(path, {})


def load_knowledge(course_slug: str) -> list[dict]:
    path = paths.KNOWLEDGE_DIR / f"{course_slug}.json"
    if not path.exists():
        return []
    return _load_json(path, {"entries": []})["entries"]


def _matching_pdfs(cfg, course, category: str) -> list[Path]:
    """The course's files of one category, as they lie in the library."""
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
    or corrected script replaces its earlier version."""
    known_sheets = {s["sheet_id"] for s in list_sheets()}
    result = {"scripts": [], "sheets": [], "errors": []}

    for course in cfg.active_courses():
        slug = slug_for(course.name)

        script = _course_script(cfg, course)
        if script is not None:
            target = paths.KNOWLEDGE_DIR / f"{slug}.json"
            if not target.exists() or target.stat().st_mtime < script.stat().st_mtime:
                if progress:
                    progress(f"Lecture notes: {course.name}")
                try:
                    ingest_script(script, course.name)
                    result["scripts"].append(course.name)
                except Exception as e:
                    result["errors"].append(f"{script.name}: {e}")

        for pdf in _matching_pdfs(cfg, course, "blaetter"):
            if pdf.stem in known_sheets:
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
