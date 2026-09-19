"""
Generate .desktop entries so the current semester's courses show up in the
Super+Space app search (Walker on Omarchy).

Per course, up to three entries:
    "<Kurs> Skript"   -> opens the script PDF
    "<Kurs> Folien"   -> opens the newest slide deck
    "<Kurs> Blatt"    -> opens the newest assignment sheet
    "<Kurs> Ordner"   -> opens the course folder in the file manager

Entries are only written for files that actually exist, so a course with no
sheets yet simply has no "Blatt" entry instead of a dead launcher item.

All generated files are named assignmentvibe-*.desktop and carry
X-AssignmentVibe=true, which is what `sync` uses to clean up stale entries from
previous semesters without touching the user's own hand-written .desktop files.
"""

import re
import shutil
import subprocess
from pathlib import Path

from .. import paths
from ..uniconfig import CATEGORIES, Config, Course

PREFIX = "assignmentvibe-"
MARKER = "X-AssignmentVibe=true"

# Entry label and icon per category, plus the folder entry.
CATEGORY_LABELS = {
    "skript": ("Skript", "application-pdf"),
    "folien": ("Folien", "application-pdf"),
    "blaetter": ("Blatt", "application-pdf"),
}

TEMPLATE = """[Desktop Entry]
Type=Application
Name={name}
Comment={comment}
Exec=xdg-open {target}
Icon={icon}
Terminal=false
Categories=Education;
Keywords={keywords}
StartupNotify=false
{marker}
"""


def _natural_key(path: Path):
    """Sort by the numbers in the filename, so Blatt 10 comes after Blatt 9.
    Falls back to modification time for names without a number."""
    numbers = [int(n) for n in re.findall(r"\d+", path.stem)]
    return (numbers or [0], path.stat().st_mtime)


def _newest(course_dir: Path, patterns: list[str]) -> Path | None:
    """Newest file in the course folder matching any of the patterns."""
    if not course_dir.is_dir() or not patterns:
        return None
    import fnmatch
    hits = [p for p in course_dir.iterdir() if p.is_file()
            and any(fnmatch.fnmatch(p.name.lower(), pat.lower()) for pat in patterns)]
    return max(hits, key=_natural_key) if hits else None


def _quote(path: Path) -> str:
    """Quote for the Exec= line. Desktop-entry spec: backslash and double quote
    are escaped, the whole argument wrapped in double quotes."""
    escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write(directory: Path, filename: str, **fields) -> Path:
    target = directory / filename
    target.write_text(TEMPLATE.format(marker=MARKER, **fields), encoding="utf-8")
    return target


def entries_for(cfg: Config, course: Course) -> list[tuple[str, dict]]:
    """(filename, template fields) for every entry this course can offer."""
    course_dir = cfg.course_dir(course)
    keywords = f"Uni;{course.semester};{course.name};"
    out = []

    for category in CATEGORIES:
        newest = _newest(course_dir, course.patterns.get(category, []))
        if newest is None:
            continue
        label, icon = CATEGORY_LABELS[category]
        out.append((f"{PREFIX}{course.semester}-{course.folder}-{category}.desktop", {
            "name": f"{course.name} {label}",
            "comment": f"{newest.name} ({course.semester})",
            "target": _quote(newest),
            "icon": icon,
            "keywords": keywords + f"{label};",
        }))

    if course_dir.is_dir():
        out.append((f"{PREFIX}{course.semester}-{course.folder}-ordner.desktop", {
            "name": f"{course.name} Ordner",
            "comment": str(course_dir),
            "target": _quote(course_dir),
            "icon": "folder",
            "keywords": keywords + "Ordner;",
        }))

    return out


def sync(cfg: Config, directory: Path | None = None) -> tuple[list[str], list[str]]:
    """Regenerate all entries for the active semester. Returns (written, removed)."""
    directory = directory or paths.APPLICATIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    written = []
    for course in cfg.active_courses():
        for filename, fields in entries_for(cfg, course):
            _write(directory, filename, **fields)
            written.append(fields["name"])

    # Drop entries we generated earlier that this run did not produce again -
    # last semester's courses, or a file that has since been renamed. Only files
    # carrying our marker are ever deleted.
    keep = {f for course in cfg.active_courses() for f, _ in entries_for(cfg, course)}
    removed = []
    for stale in directory.glob(f"{PREFIX}*.desktop"):
        if stale.name in keep:
            continue
        if MARKER in stale.read_text(encoding="utf-8", errors="ignore"):
            stale.unlink()
            removed.append(stale.name)

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(directory)],
                       capture_output=True, check=False)

    return written, removed
