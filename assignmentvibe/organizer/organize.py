"""
Turn a pile of PDFs in a Downloads folder into a `<library>/<course>/{scripts,sheets}/`
layout, using the heuristics from organizer.classify.

This is the first, most impactful roadmap item from the project vision
("Download-organize: Skript-Downloads in richtige Ordner tun, eventuell
automatisch") - everything else (knowledge extraction, prompt building)
only becomes low-friction to use once files don't have to be pointed at by
hand every time.

Design choices, and why:
- Default is a DRY RUN (`apply=False`): moving/renaming a user's own
  downloaded files is a mildly destructive action (wrong guess -> file is
  "lost" in an unexpected folder), so the default must be safe to run
  repeatedly and inspect before anything touches disk.
- Low-confidence or unrecognized files go to a `_unsorted/` bucket instead
  of being forced into a (possibly wrong) course folder - silently
  misfiling is worse than leaving something for the user to sort by hand.
- Never overwrites an existing file at the destination; such conflicts are
  reported, not resolved automatically.
- `move` vs `copy` is the caller's choice - copying is the safer default
  for a first trial run, moving is what you actually want once you trust it.

Depends on organizer.classify only (plus stdlib). Does NOT depend on
assignmentvibe.store - organizing files and ingesting them into the
knowledge base are separate concerns; cli.py wires them together only if
the user opts in via --ingest. cli.py DOES pass in the already-known
courses (as a plain slug->display-name dict, i.e. exactly what
store.list_courses() returns) so that a script and its sheets converge on
one course folder even if their guessed names differ slightly - see
_resolve_course.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from .classify import Classification, classify

CONFIDENCE_THRESHOLD_FOR_COURSE_FOLDER = 0.4

TYPE_TO_SUBFOLDER = {
    "script": "scripts",
    "sheet": "sheets",
}


@dataclass
class PlannedMove:
    classification: Classification
    target_path: Path
    conflict: bool
    # None for files routed to _unsorted/ (no course could be determined
    # with enough confidence). Otherwise the course identity actually used
    # for target_path - always ingest under THIS, not classification.course_guess,
    # or a script and its sheets can end up split across two courses (see
    # docs/ROADMAP.md changelog for the bug this fixes).
    course_slug: str | None
    course_display_name: str | None


def _slugify(name: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "course"


def _resolve_course(guess: str, known_courses: dict[str, str]) -> tuple[str, str]:
    """Course names guessed from different PDFs of the SAME course rarely
    match exactly (e.g. a script's title page says "Algebra" while a sheet's
    "Aufgaben zur Algebra 1" content match yields "Algebra 1") - which would
    otherwise split one course into two folders. If the guess's slug is a
    prefix/substring match (either direction) of an already-known course
    slug, reuse that course (slug AND display name) instead of minting a
    new, near-duplicate one. Returns (slug, display_name).

    Known limitation: if two DIFFERENT known slugs both happen to contain the
    guess as a substring (e.g. "algebra-1" and "algebra-intro" both contain
    "algebra"), the match is ambiguous. We pick the shortest known slug
    (usually the more "canonical"/general one) and break remaining ties
    alphabetically, so the result is at least deterministic - not
    necessarily "correct" for every possible naming collision.
    """
    slug = _slugify(guess)
    if slug in known_courses:
        return slug, known_courses[slug]
    candidates = sorted(k for k in known_courses if slug in k or k in slug)
    if candidates:
        best = min(candidates, key=len)
        return best, known_courses[best]
    return slug, guess


def plan(
    source_dir: Path,
    library_dir: Path,
    known_courses: dict[str, str] | None = None,
) -> list[PlannedMove]:
    """Classify every top-level PDF in source_dir and compute where it would go,
    without touching the filesystem. `known_courses` (optional, slug ->
    display name - i.e. the shape of store.list_courses()) lets the caller
    fold a fresh guess into an already-known course instead of creating a
    near-duplicate folder - see _resolve_course."""
    # Start with whatever the caller already knows about (e.g. courses
    # already ingested into the knowledge base), then grow this as we go so
    # that multiple matching files WITHIN this same run also converge on one
    # course, not just already-ingested ones.
    seen_courses = dict(known_courses or {})
    moves = []
    for pdf_path in sorted(source_dir.glob("*.pdf")):
        c = classify(pdf_path)

        course_slug = None
        course_display_name = None
        if c.doc_type in TYPE_TO_SUBFOLDER and c.confidence >= CONFIDENCE_THRESHOLD_FOR_COURSE_FOLDER:
            if c.course_guess:
                course_slug, course_display_name = _resolve_course(c.course_guess, seen_courses)
                seen_courses[course_slug] = course_display_name
            else:
                course_slug, course_display_name = "uncategorized", "Uncategorized"
            target_dir = library_dir / course_slug / TYPE_TO_SUBFOLDER[c.doc_type]
        else:
            target_dir = library_dir / "_unsorted"

        target_path = target_dir / pdf_path.name
        moves.append(PlannedMove(
            classification=c,
            target_path=target_path,
            conflict=target_path.exists(),
            course_slug=course_slug,
            course_display_name=course_display_name,
        ))

    return moves


def apply(moves: list[PlannedMove], mode: str = "copy") -> list[str]:
    """Execute a plan. mode is 'copy' or 'move'. Returns a list of log lines.
    Skips (and reports) any move whose target already exists."""
    if mode not in ("copy", "move"):
        raise ValueError("mode must be 'copy' or 'move'")

    log = []
    for m in moves:
        if m.conflict:
            log.append(f"SKIP (target exists): {m.classification.path.name} -> {m.target_path}")
            continue
        m.target_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            shutil.copy2(m.classification.path, m.target_path)
        else:
            shutil.move(str(m.classification.path), str(m.target_path))
        log.append(f"{mode.upper()}: {m.classification.path.name} -> {m.target_path}")
    return log


def format_plan(moves: list[PlannedMove]) -> str:
    lines = []
    for m in moves:
        c = m.classification
        flag = " [CONFLICT]" if m.conflict else ""
        lines.append(
            f"{c.path.name}  ->  {m.target_path}{flag}\n"
            f"    type={c.doc_type} confidence={c.confidence:.2f} course_guess={c.course_guess!r}\n"
            f"    reason: {c.reason}"
        )
    return "\n".join(lines) if lines else "(no PDFs found)"
