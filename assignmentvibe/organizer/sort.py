"""
Move matching downloads into <uni_root>/<semester>/<folder>/.

Config-driven only (see assignmentvibe.uniconfig): a file is moved if, and only
if, it matches a pattern the user wrote down. Anything unmatched is counted and
left where it is. Dry run is the default - `apply()` only runs when asked.

Deliberately free of pymupdf, so sorting works on a bare Python install.
"""

import filecmp
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..uniconfig import Config, Course

# What we decided about one file in ~/Downloads.
OK = "ok"                # will be moved
DUPLICATE = "duplicate"  # already in the course folder, byte-identical
CONFLICT = "conflict"    # a different file of that name is already there
AMBIGUOUS = "ambiguous"  # matches patterns of two courses - user must fix config


@dataclass
class Item:
    source: Path
    course: Course
    category: str
    target: Path
    status: str


def plan(cfg: Config) -> tuple[list[Item], int]:
    """Returns (items, ignored_count). Touches nothing on disk."""
    courses = cfg.active_courses()
    items, ignored = [], 0

    for source in sorted(p for p in cfg.downloads.iterdir() if p.is_file()):
        hits = [(c, cat) for c in courses if (cat := c.match(source.name))]
        if not hits:
            ignored += 1
            continue

        course, category = hits[0]
        target = cfg.course_dir(course) / source.name

        if len(hits) > 1:
            status = AMBIGUOUS
        elif not target.exists():
            status = OK
        elif filecmp.cmp(source, target, shallow=False):
            status = DUPLICATE
        else:
            status = CONFLICT

        items.append(Item(source, course, category, target, status))

    return items, ignored


def apply(items: list[Item], mode: str = "move") -> list[str]:
    """Execute the OK items. Anything else is reported, never resolved silently."""
    log = []
    for item in items:
        if item.status != OK:
            log.append(f"uebersprungen ({item.status}): {item.source.name}")
            continue
        item.target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            shutil.copy2(item.source, item.target)
        else:
            shutil.move(str(item.source), str(item.target))
        log.append(f"{item.source.name}  ->  {item.target}")
    return log


def format_plan(cfg: Config, items: list[Item], ignored: int) -> str:
    if not items:
        return (f"Nichts zu sortieren. {ignored} Datei(en) in {cfg.downloads} "
                f"passen auf kein Muster in {cfg.path.name}.")

    by_status: dict[str, list[Item]] = {}
    for item in items:
        by_status.setdefault(item.status, []).append(item)

    lines = []
    for item in by_status.get(OK, []):
        lines.append(f"  {item.source.name}")
        lines.append(f"      -> {item.course.name} / {item.category}  ({item.target.parent})")

    labels = {
        DUPLICATE: "Liegt dort schon identisch (bleibt in Downloads):",
        CONFLICT: "ACHTUNG - gleicher Name, anderer Inhalt (nicht angefasst):",
        AMBIGUOUS: "Passt auf mehrere Kurse - Muster in der Config schaerfen:",
    }
    for status, label in labels.items():
        group = by_status.get(status)
        if not group:
            continue
        lines.append("")
        lines.append(label)
        lines.extend(f"  {i.source.name}  ({i.course.name})" for i in group)

    lines.append("")
    lines.append(f"{len(by_status.get(OK, []))} zu verschieben, {ignored} ignoriert.")
    return "\n".join(lines)
