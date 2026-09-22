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
from .core import assignments as assignments_core
from .core import knowledge as knowledge_core
from .core import pdf_text


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "course"


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
        raise FileNotFoundError(f"Kein Aufgabenblatt mit id '{sheet_id}' gefunden. "
                                 f"Erst mit 'ingest-sheet' einlesen.")
    return _load_json(path, {})


def load_knowledge(course_slug: str) -> list[dict]:
    path = paths.KNOWLEDGE_DIR / f"{course_slug}.json"
    if not path.exists():
        return []
    return _load_json(path, {"entries": []})["entries"]
