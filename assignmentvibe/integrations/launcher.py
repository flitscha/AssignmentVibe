"""
Generate .desktop entries so courses show up in the Super+Space app search
(Walker on Omarchy).

Per course of the ACTIVE semester:
    "<Kurs> Skript"          the one lecture script
    "<Kurs> Folien <name>"   one entry per slide deck - there is one per chapter,
                             and picking a specific chapter is the whole point
    "<Kurs> Blatt"           the newest assignment sheet only; older sheets would
                             add a dozen entries per course for little gain
    "<Kurs> Ordner"          the course folder in the file manager

Scripts of PAST semesters are added too (config: alte_skripte_im_launcher),
labelled "<Kurs> Skript (s4)", because a lecture script stays a reference long
after the course ends. Their slides, sheets and folders are left out.

Entries are only written for files that exist, so a course with no sheets yet
simply has no "Blatt" entry instead of a dead launcher item.

All generated files are named assignmentvibe-*.desktop and carry
X-AssignmentVibe=true, which is what `sync` uses to clean up entries from
previous runs without touching the user's own hand-written .desktop files.
"""

import fnmatch
import re
import shutil
import subprocess
from pathlib import Path

from .. import paths
from ..uniconfig import Config, Course

PREFIX = "assignmentvibe-"
MARKER = "X-AssignmentVibe=true"

TEMPLATE = """[Desktop Entry]
Type=Application
Name={name}
Comment={comment}
Exec={exec_line}
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


def _matching(course_dir: Path, patterns: list[str]) -> list[Path]:
    if not course_dir.is_dir() or not patterns:
        return []
    hits = [p for p in course_dir.iterdir() if p.is_file()
            and any(fnmatch.fnmatch(p.name.lower(), pat.lower()) for pat in patterns)]
    return sorted(hits, key=_natural_key)


def _quote(value: str) -> str:
    """Quote one Exec= argument per the desktop-entry spec."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _exec_line(cfg: Config, target: Path) -> str:
    """PDFs open in the configured viewer (a browser by default); folders always
    go through xdg-open, which lands in the desktop's file manager."""
    if target.is_dir() or target.suffix.lower() != ".pdf":
        return f"xdg-open {_quote(str(target))}"
    return f"{cfg.pdf_viewer} {_quote(str(target))}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def entries_for(cfg: Config, course: Course, scripts_only: bool = False
                ) -> list[tuple[str, dict]]:
    """(filename, template fields) for every entry this course can offer.
    `scripts_only` is used for past semesters."""
    course_dir = cfg.course_dir(course)
    suffix = "" if course.semester == cfg.active else f" ({course.semester})"
    keywords = f"Uni;{course.semester};{course.name};"
    base = f"{PREFIX}{course.semester}-{_slug(course.folder)}"
    out = []

    def add(filename: str, name: str, target: Path, icon: str, extra_keyword: str):
        out.append((filename, {
            "name": name,
            "comment": f"{target.name} ({course.semester})",
            "exec_line": _exec_line(cfg, target),
            "icon": icon,
            "keywords": keywords + f"{extra_keyword};",
        }))

    scripts = _matching(course_dir, course.patterns.get("skript", []))
    if scripts:
        # There is exactly one script per course by design (the sorter replaces
        # the old one); if several are lying around, the newest wins.
        add(f"{base}-skript.desktop", f"{course.name} Skript{suffix}",
            scripts[-1], "application-pdf", "Skript")

    if scripts_only:
        return out

    for deck in _matching(course_dir, course.patterns.get("folien", [])):
        add(f"{base}-folien-{_slug(deck.stem)}.desktop",
            f"{course.name} Folien {deck.stem}", deck, "application-pdf", "Folien")

    sheets = _matching(course_dir, course.patterns.get("blaetter", []))
    if sheets:
        add(f"{base}-blatt.desktop", f"{course.name} Blatt",
            sheets[-1], "application-pdf", "Blatt")

    if course_dir.is_dir():
        add(f"{base}-ordner.desktop", f"{course.name} Ordner",
            course_dir, "folder", "Ordner")
        out[-1][1]["comment"] = str(course_dir)

    return out


def _all_entries(cfg: Config) -> list[tuple[str, dict]]:
    entries = [e for c in cfg.active_courses() for e in entries_for(cfg, c)]
    if cfg.alte_skripte_im_launcher:
        entries += [e for c in cfg.past_courses()
                    for e in entries_for(cfg, c, scripts_only=True)]
    return entries


def sync(cfg: Config, directory: Path | None = None) -> tuple[list[str], list[str]]:
    """Regenerate all entries. Returns (written_names, removed_filenames)."""
    directory = directory or paths.APPLICATIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    entries = _all_entries(cfg)
    for filename, fields in entries:
        (directory / filename).write_text(
            TEMPLATE.format(marker=MARKER, **fields), encoding="utf-8")

    # Drop entries we generated earlier that this run did not produce again -
    # a course that ended, or a file that has since been renamed. Only files
    # carrying our marker are ever deleted.
    keep = {filename for filename, _ in entries}
    removed = []
    for stale in sorted(directory.glob(f"{PREFIX}*.desktop")):
        if stale.name in keep:
            continue
        if MARKER in stale.read_text(encoding="utf-8", errors="ignore"):
            stale.unlink()
            removed.append(stale.name)

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(directory)],
                       capture_output=True, check=False)

    return [fields["name"] for _, fields in entries], removed
