"""
Verwaltet die vom Nutzer eingelesenen Skripte und Aufgabenblaetter unter
~/.local/share/assignmentvibe/. Duenne Schicht ueber der bestehenden
pipeline/-Engine (extract_text/extract_knowledge/extract_assignments) - die
macht die eigentliche PDF-Arbeit, hier geht es nur um "wo liegt was" und
"welcher Kurs gehoert dazu".
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import extract_assignments, extract_knowledge, extract_text  # noqa: E402

from . import paths


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "kurs"


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
    """PDF-Skript -> Wissensbasis. Gibt Statistik zurueck (fuer CLI-Ausgabe)."""
    paths.ensure_dirs()
    slug = _slugify(course_name)
    _register_course(slug, course_name)

    raw_path = paths.RAW_TEXT_CACHE_DIR / f"{slug}.json"
    knowledge_path = paths.KNOWLEDGE_DIR / f"{slug}.json"

    extract_text.extract_to_json(pdf_path, raw_path)
    extract_knowledge.run(raw_path, knowledge_path, pdf_path)
    saved = _load_json(knowledge_path, {"entries": []})

    return {
        "course": course_name,
        "slug": slug,
        "entries": len(saved["entries"]),
        "knowledge_path": str(knowledge_path),
    }


def ingest_sheet(pdf_path: Path, course_name: str) -> dict:
    """Aufgabenblatt-PDF -> strukturierte Aufgaben, dem Kurs zugeordnet."""
    paths.ensure_dirs()
    slug = _slugify(course_name)
    _register_course(slug, course_name)

    sheet_id = pdf_path.stem
    out_path = paths.ASSIGNMENTS_DIR / f"{sheet_id}.json"

    result = extract_assignments.parse_assignment_sheet(pdf_path)
    result["course_slug"] = slug
    result["sheet_id"] = sheet_id
    _save_json(out_path, result)

    return {
        "sheet_id": sheet_id,
        "course": course_name,
        "num_aufgaben": result["num_aufgaben"],
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
