"""
Move matching downloads into <uni_root>/<semester>/<folder>/.

Config-driven only (see assignmentvibe.uniconfig): a file is moved if, and only
if, it matches a pattern the user wrote down. Anything unmatched is counted and
left where it is. Dry run is the default.

Replacement rules, which differ by category because the real-world artefacts do:

  skript    There is exactly one per course. A newly downloaded script replaces
            whatever script is currently in the folder, even under a different
            name (VO3_... superseded by VO4_...) - that is what "new version"
            means for a lecture script.
  folien    Several per course, one per chapter. Only a file with the SAME name
            replaces an existing one; a different name is simply a different
            chapter and is added alongside.
  blaetter  Same as folien: same name replaces, different name adds.

"Same name" is compared after stripping the browser's duplicate suffix, so
re-downloading "Folien_Kapitel2.pdf" as "Folien_Kapitel2(1).pdf" is recognised
as a new version of the same file - and lands under the clean name.

Nothing is ever deleted outright: replaced files and redundant downloads go to
the desktop trash via `gio trash`, so a wrong guess stays recoverable.

Deliberately free of pymupdf, so sorting works on a bare Python install.
"""

import filecmp
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from ..uniconfig import Config, Course

NEW = "new"                # nothing there yet, just move it in
REPLACE = "replace"        # supersedes file(s) already in the course folder
DUPLICATE = "duplicate"    # byte-identical copy already filed; drop the download
SUPERSEDED = "superseded"  # another download in this same run wins this target
AMBIGUOUS = "ambiguous"    # matches two courses - the config needs sharpening

# Firefox writes "foo(1).pdf", Chrome "foo (1).pdf" when a name is taken.
# Only the parenthesised forms are treated as duplicate markers: a trailing
# "-1"/"_1" is far more likely to be a real chapter or sheet number
# ("Blatt_1.pdf"), and stripping that would merge distinct files.
DUPLICATE_SUFFIX_RE = re.compile(r"^(?P<stem>.+?) ?\(\d+\)$")


def clean_name(filename: str) -> str:
    """'Folien_Kapitel2(1).pdf' -> 'Folien_Kapitel2.pdf'"""
    parts = PurePath(filename)
    match = DUPLICATE_SUFFIX_RE.match(parts.stem)
    return f"{match.group('stem')}{parts.suffix}" if match else filename


@dataclass
class Item:
    source: Path
    course: Course
    category: str
    target: Path
    status: str
    # Files already in the course folder that this download supersedes. They are
    # trashed - not overwritten - so the previous version stays recoverable.
    replaces: list[Path] = field(default_factory=list)


def _trash(path: Path) -> None:
    """Desktop trash, so anything this tool removes can be brought back from the
    file manager. Falls back to a plain rename if gio is unavailable."""
    if shutil.which("gio"):
        result = subprocess.run(["gio", "trash", str(path)],
                                capture_output=True, check=False)
        if result.returncode == 0:
            return
    backup = path.with_name(path.name + ".alt")
    if backup.exists():
        backup.unlink()
    path.rename(backup)


def _existing_scripts(cfg: Config, course: Course, keep: Path) -> list[Path]:
    """Script files already in the course folder, other than `keep`."""
    course_dir = cfg.course_dir(course)
    if not course_dir.is_dir():
        return []
    import fnmatch
    patterns = course.patterns.get("skript", [])
    return [p for p in sorted(course_dir.iterdir())
            if p.is_file() and p != keep
            and any(fnmatch.fnmatch(p.name.lower(), pat.lower()) for pat in patterns)]


def plan(cfg: Config) -> tuple[list[Item], int]:
    """Returns (items, ignored_count). Touches nothing on disk."""
    courses = cfg.active_courses()
    items, ignored = [], 0

    for source in sorted(p for p in cfg.downloads.iterdir() if p.is_file()):
        target_name = clean_name(source.name)
        # Match on the cleaned name as well, so "01-Blatt(1).pdf" still matches
        # a pattern written as "*-Blatt*.pdf".
        hits = []
        for course in courses:
            category = course.match(source.name) or course.match(target_name)
            if category:
                hits.append((course, category))
        if not hits:
            ignored += 1
            continue

        course, category = hits[0]
        status = AMBIGUOUS if len(hits) > 1 else NEW
        items.append(Item(source, course, category,
                          cfg.course_dir(course) / target_name, status))

    _resolve_within_run(items)
    _resolve_against_disk(cfg, items)
    return items, ignored


def _resolve_within_run(items: list[Item]) -> None:
    """Two downloads competing for one target (typically 'foo.pdf' and a later
    'foo(1).pdf') - the most recently downloaded one wins, the rest are dropped."""
    by_target: dict[Path, list[Item]] = {}
    for item in items:
        if item.status != AMBIGUOUS:
            by_target.setdefault(item.target, []).append(item)

    for group in by_target.values():
        if len(group) < 2:
            continue
        winner = max(group, key=lambda i: i.source.stat().st_mtime)
        for item in group:
            if item is not winner:
                item.status = SUPERSEDED


def _resolve_against_disk(cfg: Config, items: list[Item]) -> None:
    for item in items:
        if item.status not in (NEW,):
            continue

        if item.target.exists():
            if filecmp.cmp(item.source, item.target, shallow=False):
                item.status = DUPLICATE
                continue
            item.status = REPLACE
            item.replaces.append(item.target)

        # A lecture script replaces the previous one even under a different
        # name; slides and sheets only ever replace the same name.
        if item.category == "skript":
            older = _existing_scripts(cfg, item.course, keep=item.target)
            if older:
                item.replaces.extend(older)
                item.status = REPLACE


def apply(items: list[Item], mode: str = "move") -> list[str]:
    """Execute the plan. In copy mode the Downloads folder is never touched,
    which makes `--mode copy` a genuinely non-destructive trial run."""
    log = []
    for item in items:
        if item.status == AMBIGUOUS:
            log.append(f"uebersprungen (mehrere Kurse): {item.source.name}")
            continue

        if item.status in (DUPLICATE, SUPERSEDED):
            if mode == "copy":
                log.append(f"uebersprungen ({item.status}): {item.source.name}")
                continue
            _trash(item.source)
            log.append(f"Papierkorb (schon vorhanden): {item.source.name}")
            continue

        for old in item.replaces:
            _trash(old)
            log.append(f"Papierkorb (ersetzt): {old.name}")

        item.target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            shutil.copy2(item.source, item.target)
        else:
            shutil.move(str(item.source), str(item.target))

        renamed = "" if item.source.name == item.target.name else f"  [umbenannt]"
        log.append(f"{item.source.name}  ->  {item.target}{renamed}")

    return log


def format_plan(cfg: Config, items: list[Item], ignored: int) -> str:
    if not items:
        return (f"Nichts zu sortieren. {ignored} Datei(en) in {cfg.downloads} "
                f"passen auf kein Muster in {cfg.path.name}.")

    lines, moving = [], 0
    for item in items:
        if item.status not in (NEW, REPLACE):
            continue
        moving += 1
        rename = f"   (als {item.target.name})" if item.source.name != item.target.name else ""
        lines.append(f"  {item.source.name}{rename}")
        lines.append(f"      -> {item.course.name} / {item.category}  ({item.target.parent})")
        for old in item.replaces:
            lines.append(f"      ersetzt {old.name}  (-> Papierkorb)")

    def group(status: str, label: str) -> None:
        chosen = [i for i in items if i.status == status]
        if not chosen:
            return
        lines.append("")
        lines.append(label)
        lines.extend(f"  {i.source.name}  ({i.course.name})" for i in chosen)

    group(DUPLICATE, "Schon einsortiert, Download kommt in den Papierkorb:")
    group(SUPERSEDED, "Aeltere Version desselben Downloads, kommt in den Papierkorb:")
    group(AMBIGUOUS, "Passt auf mehrere Kurse - Muster in der Config schaerfen:")

    lines.append("")
    lines.append(f"{moving} zu verschieben, {ignored} ignoriert.")
    return "\n".join(lines)
