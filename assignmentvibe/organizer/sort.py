"""
Move matching downloads into <uni_root>/<semester>/<folder>/.

Config-driven only (see assignmentvibe.uniconfig): a file is moved if, and only
if, it matches a pattern the user wrote down. Anything unmatched is counted and
left where it is. Dry run is the default.

Replacement rules, which differ by category because the real-world artefacts do:

  skript    One per PATTERN, not one per course. A new download replaces the
            script matching the same pattern, even under a different name
            ("VO*_Optimierung.pdf" lets VO4 supersede VO3). Two patterns are two
            slots, which is how a course keeps both "lecture-notes.pdf" and
            "lecture-notes-annotated.pdf" without them fighting each other.
  folien    Several per course, one per chapter. Only a file with the SAME name
            replaces an existing one; a different name is simply a different
            chapter and is added alongside.
  blaetter  Same as folien: same name replaces, different name adds.

"Same name" is compared after stripping the browser's duplicate counter, so
re-downloading "Folien.pdf" as "Folien-1.pdf" is recognised as a new version of
the same file - and lands under the clean name. Firefox uses "-1", Chrome
"(1)"; both are handled.

That stripping is conditional, because a counter suffix is not always one:
"04x1-1.pdf" is a real slide deck in this user's material. A suffix therefore
only counts as a duplicate marker when the name WITHOUT it actually exists -
either already filed under the course, or as another file in the same batch of
downloads. Otherwise the name is kept as it is.

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

# Firefox appends "-1", Chrome " (1)" when the target name is taken. "_1" is
# left out on purpose: "Blatt_1.pdf" and "Blatt_2.pdf" are ordinary distinct
# sheets, and no browser here produces that form.
DUPLICATE_SUFFIX_RE = re.compile(r"^(?P<stem>.+?)(?: ?\(\d+\)|-\d+)$")


def base_name(filename: str) -> str | None:
    """'Folien-1.pdf' -> 'Folien.pdf'; None if there is no counter suffix.

    Whether that base name is the RIGHT target is decided by the caller, which
    checks that a file of that name actually exists - see the module docstring."""
    parts = PurePath(filename)
    match = DUPLICATE_SUFFIX_RE.match(parts.stem)
    return f"{match.group('stem')}{parts.suffix}" if match else None


@dataclass
class Item:
    source: Path
    course: Course
    category: str
    pattern: str
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


def _existing_for_pattern(cfg: Config, course: Course, category: str,
                          pattern: str, keep: Path) -> list[Path]:
    """Files already filed under this course that match the SAME pattern, other
    than `keep`. Searched recursively, because a course folder may be organised
    into subfolders by hand (e.g. vo/Kapitel 3 - .../)."""
    import fnmatch
    directory = cfg.category_dir(course, category)
    if not directory.is_dir():
        return []
    return [p for p in sorted(directory.rglob("*"))
            if p.is_file() and p != keep
            and fnmatch.fnmatch(p.name.lower(), pattern.lower())]


def _find_filed(cfg: Config, course: Course, category: str, name: str) -> Path | None:
    """An already-filed file of exactly this name, wherever it sits under the
    category folder. Re-downloads then land next to the version they replace,
    instead of a second copy appearing one level up."""
    directory = cfg.category_dir(course, category)
    if not directory.is_dir():
        return None
    return next((p for p in sorted(directory.rglob(name)) if p.is_file()), None)


def plan(cfg: Config) -> tuple[list[Item], int]:
    """Returns (items, ignored_count). Touches nothing on disk."""
    courses = cfg.active_courses()
    sources = sorted(p for p in cfg.downloads.iterdir() if p.is_file())
    in_downloads = {p.name for p in sources}
    items, ignored = [], 0

    for source in sources:
        base = base_name(source.name)
        # Match on the stripped name too, so "01-Blatt-1.pdf" still matches a
        # pattern written as "*-Blatt-PS-Optimierung.pdf".
        hits = []
        for course in courses:
            hit = course.match(source.name) or (base and course.match(base))
            if hit:
                hits.append((course, *hit))
        if not hits:
            ignored += 1
            continue

        course, category, pattern = hits[0]
        status = AMBIGUOUS if len(hits) > 1 else NEW

        # Treat the counter as a duplicate marker only if the un-suffixed name
        # is real - already filed, or sitting in Downloads next to this one.
        filed_base = _find_filed(cfg, course, category, base) if base else None
        if base and (filed_base is not None or base in in_downloads):
            target_name, filed = base, filed_base
        else:
            target_name = source.name
            filed = _find_filed(cfg, course, category, target_name)

        target = filed or (cfg.category_dir(course, category) / target_name)
        items.append(Item(source, course, category, pattern, target, status))

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
        # name - but only within its own pattern. Slides and sheets exist in
        # numbers and only ever replace an identical name.
        if item.category == "skript":
            older = _existing_for_pattern(cfg, item.course, item.category,
                                          item.pattern, keep=item.target)
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
