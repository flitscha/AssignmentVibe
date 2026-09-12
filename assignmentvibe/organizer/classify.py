"""
Guess, for a given PDF, (a) whether it is a lecture *script* or an
*assignment sheet*, and (b) which course it belongs to.

This is inherently a best-effort heuristic - filenames in a real Downloads
folder are messy and inconsistent, so we combine two signals:

1. Filename patterns (fast, no PDF parsing): keywords like "Blatt"/"Skript",
   numbering conventions like "A01" or "07-Blatt-...".
2. A light content peek (first page of text only, via core.pdf_text) for
   phrases that show up literally in the example material, e.g.
   "Aufgaben zur <course>" on assignment sheets, or
   "Skriptum zur Vorlesung\n<course>" on scripts.

Each result carries a `confidence` in [0, 1] so callers (organizer.organize)
can decide how much to trust an automatic decision vs. asking the user or
leaving the file alone. This is intentionally conservative: a wrong
DOC_TYPE guess is easy to fix by hand later, but silently misfiling a PDF
under the wrong course is annoying - so low-confidence results should be
surfaced, not acted on blindly.

Depends only on assignmentvibe.core.pdf_text (for the content peek).
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ..core import pdf_text

# Cheap, content-free prior: in the example material, assignment sheets are
# always 1-2 pages and scripts are 100+ pages. Not a rule in general, but a
# useful tie-breaker when neither filename nor first-page content gave a
# confident answer.
SCRIPT_PAGE_COUNT_THRESHOLD = 15
SHEET_PAGE_COUNT_THRESHOLD = 3

SHEET_FILENAME_HINTS = [
    "blatt", "übung", "uebung", "aufgabenblatt", "exercise", "worksheet", "hausaufgabe",
]
SCRIPT_FILENAME_HINTS = [
    "skript", "skriptum", "vorlesung", "lecture", "script", "notes",
]

# "A01", "A14" style exercise-sheet numbering (seen in the Algebra example set).
SHEET_LETTER_NUM_RE = re.compile(r"^[A-Za-z]\d{1,3}$")
# "07-Blatt-...", "12_Blatt_..." style leading week number.
SHEET_LEADING_NUM_RE = re.compile(r"^\d{1,3}[-_]")
# "VO3_Optimierung" style lecture-number prefix.
SCRIPT_VO_PREFIX_RE = re.compile(r"^VO\d*[-_]", re.IGNORECASE)

NOISE_TOKENS = {
    "blatt", "ps", "vo", "übung", "uebung", "aufgabenblatt", "skript", "skriptum",
    "lecture", "worksheet", "notes", "exercise",
}

CONTENT_SHEET_RE = re.compile(r"Aufgaben\s+zur\s+(?P<course>[^\n]+)")
CONTENT_SCRIPT_RE = re.compile(r"Skriptum\s+zur\s+Vorlesung\s*\n\s*(?P<course>[^\n]+)")


@dataclass
class Classification:
    path: Path
    doc_type: str  # "script" | "sheet" | "unknown"
    course_guess: str | None
    confidence: float  # 0.0 - 1.0
    reason: str


def _filename_tokens(stem: str) -> list[str]:
    return [t for t in re.split(r"[-_\s]+", stem) if t]


def _guess_course_from_filename(stem: str) -> str | None:
    tokens = _filename_tokens(stem)
    kept = [t for t in tokens if t.lower() not in NOISE_TOKENS and not t.isdigit()]
    return " ".join(kept) if kept else None


def _classify_by_filename(stem: str) -> tuple[str, float, str]:
    lower = stem.lower()

    if any(hint in lower for hint in SHEET_FILENAME_HINTS) or SHEET_LEADING_NUM_RE.match(stem):
        return "sheet", 0.7, "filename matches assignment-sheet pattern"
    if SHEET_LETTER_NUM_RE.match(stem):
        return "sheet", 0.6, "filename looks like a lettered sheet id (e.g. A03)"
    if any(hint in lower for hint in SCRIPT_FILENAME_HINTS) or SCRIPT_VO_PREFIX_RE.match(stem):
        return "script", 0.7, "filename matches lecture-script pattern"

    return "unknown", 0.2, "no filename pattern matched"


def _page_count(pdf_path: Path) -> int | None:
    try:
        return pymupdf.open(pdf_path).page_count
    except Exception:
        return None


def _peek_first_page_text(pdf_path: Path) -> str:
    try:
        pages = pdf_text.extract_pages(pdf_path)
    except Exception:
        return ""
    return pages[0] if pages else ""


def classify(pdf_path: Path) -> Classification:
    stem = pdf_path.stem
    doc_type, confidence, reason = _classify_by_filename(stem)
    course_guess = _guess_course_from_filename(stem)

    first_page = _peek_first_page_text(pdf_path)

    sheet_m = CONTENT_SHEET_RE.search(first_page)
    script_m = CONTENT_SCRIPT_RE.search(first_page)

    if sheet_m:
        doc_type, confidence = "sheet", 0.95
        course_guess = sheet_m.group("course").strip()
        reason = "first page contains 'Aufgaben zur <course>'"
    elif script_m:
        doc_type, confidence = "script", 0.95
        course_guess = script_m.group("course").strip()
        reason = "first page contains 'Skriptum zur Vorlesung\\n<course>'"
    elif doc_type == "unknown" and first_page.count("Aufgabe ") >= 2 and "Besprechung" in first_page:
        # Weaker content signal: several "Aufgabe N" occurrences plus a
        # discussion-date mention strongly suggests an assignment sheet even
        # without the exact "Aufgaben zur" phrasing.
        doc_type, confidence = "sheet", 0.5
        reason = "content has multiple 'Aufgabe N' + a discussion date, but no clear course phrase"

    if doc_type == "unknown":
        page_count = _page_count(pdf_path)
        if page_count is not None:
            if page_count >= SCRIPT_PAGE_COUNT_THRESHOLD:
                doc_type, confidence = "script", 0.6
                reason = f"no filename/content match, but {page_count} pages strongly suggests a script"
            elif page_count <= SHEET_PAGE_COUNT_THRESHOLD:
                doc_type, confidence = "sheet", 0.4
                reason = f"no filename/content match, but only {page_count} page(s) suggests a sheet"

    if course_guess is None and doc_type != "unknown":
        # Weakest fallback: first non-empty line of the PDF, if it looks like
        # a short title (not a full sentence).
        first_line = next((ln.strip() for ln in first_page.splitlines() if ln.strip()), None)
        if first_line and len(first_line) <= 60 and not first_line.endswith("."):
            course_guess = first_line
            confidence = min(confidence, 0.35)
            reason += "; course guessed from first line of text (low confidence)"

    return Classification(
        path=pdf_path,
        doc_type=doc_type,
        course_guess=course_guess,
        confidence=confidence,
        reason=reason,
    )
