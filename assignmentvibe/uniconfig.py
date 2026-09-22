"""
~/.config/assignmentvibe/uni.json - the one file edited once per semester.

    {
      "active": "m1",
      "uni_root": "~/Uni",
      "downloads": "~/Downloads",
      "pdf_viewer": "firefox",
      "semesters": {
        "m1": {
          "optimierung": {
            "name":     "Optimierung",
            "skript":   ["VO3_Optimierung.pdf"],
            "folien":   ["*Folien*.pdf"],
            "blaetter": ["*-Blatt-PS-Optimierung.pdf"]
          }
        }
      }
    }

Names are glob patterns (* ? [0-9]), matched case-insensitively against the
filename. A download is course material if and only if it matches a pattern
here; everything else in ~/Downloads is left alone. That is the whole rule.

The three categories don't affect where a file goes - everything lands flat in
<uni_root>/<semester>/<folder>/. They only label the file so the launcher can
offer "<course> Skript", "<course> Folien" and "<course> Blatt" (the newest one).
"""

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

CATEGORIES = ("skript", "folien", "blaetter")


class ConfigError(Exception):
    """Message is shown to the user as-is, so it is German and actionable."""


@dataclass
class Course:
    semester: str
    folder: str
    name: str
    patterns: dict[str, list[str]]
    # Optional per-category subfolder, e.g. {"folien": "vo", "blaetter": "ps"}.
    # Default is flat: everything directly in the course folder.
    unterordner: dict[str, str] = field(default_factory=dict)

    def match(self, filename: str) -> tuple[str, str] | None:
        """(category, pattern) this filename falls into, or None if not ours.

        The matching PATTERN is part of the answer because replacement is scoped
        to it: "lecture-notes-modeling.pdf" and "lecture-notes-modeling-annotated.pdf"
        are two scripts that coexist, each replaced only by a newer version of
        itself. One pattern is one slot."""
        lower = filename.lower()
        for category in CATEGORIES:
            for pattern in self.patterns.get(category, []):
                if fnmatch.fnmatch(lower, pattern.lower()):
                    return category, pattern
        return None


@dataclass
class Config:
    active: str
    uni_root: Path
    downloads: Path
    courses: list[Course]
    path: Path
    # Which program the generated launcher entries open PDFs with. The desktop
    # default (xdg-open) is Evince here, but a browser keeps a lecture script in
    # a tab next to everything else, which is how these are actually read.
    pdf_viewer: str = "firefox"
    # Lecture scripts stay searchable after the semester ends - you look things
    # up in an old script long after the course is over. Slides, sheets and
    # folders would only be noise, so those stay limited to the active semester.
    alte_skripte_im_launcher: bool = True

    def active_courses(self) -> list[Course]:
        return [c for c in self.courses if c.semester == self.active]

    def past_courses(self) -> list[Course]:
        return [c for c in self.courses if c.semester != self.active]

    def course_dir(self, course: Course) -> Path:
        return self.uni_root / course.semester / course.folder

    def category_dir(self, course: Course, category: str) -> Path:
        """Where files of this category live - the course folder itself unless
        the course declares a subfolder for it."""
        sub = course.unterordner.get(category, "")
        return self.course_dir(course) / sub if sub else self.course_dir(course)


def parse(raw: dict, path: Path) -> Config:
    active = raw.get("active")
    if not active:
        raise ConfigError('The config is missing "active": "<semester>", e.g. "m1".')

    semesters = {k: v for k, v in (raw.get("semesters") or {}).items()
                 if not k.startswith("_")}
    if active not in semesters:
        known = ", ".join(semesters) or "(none)"
        raise ConfigError(f'"active" is "{active}", but "semesters" has no such '
                          f'semester. Available: {known}.')

    courses = []
    for semester, folders in semesters.items():
        for folder, spec in folders.items():
            # JSON has no comments, so any key starting with "_" is treated as
            # a note and ignored - both as a course name and inside a course.
            if folder.startswith("_"):
                continue
            allowed = {"name", "unterordner", *CATEGORIES}
            unknown = {k for k in spec if not k.startswith("_")} - allowed
            if unknown:
                raise ConfigError(f'{semester}/{folder}: unknown fields '
                                  f'{sorted(unknown)}. Allowed: {", ".join(sorted(allowed))}.')

            subfolders = spec.get("unterordner") or {}
            bad = set(subfolders) - set(CATEGORIES)
            if bad:
                raise ConfigError(f'{semester}/{folder}: "unterordner" only knows '
                                  f'{", ".join(CATEGORIES)} - not {sorted(bad)}.')
            # A bare string is accepted where a list is expected - writing
            # "skript": "VO3.pdf" is the mistake everyone makes once.
            patterns = {}
            for category in CATEGORIES:
                value = spec.get(category) or []
                patterns[category] = [value] if isinstance(value, str) else list(value)
            courses.append(Course(
                semester=semester,
                folder=folder,
                name=spec.get("name") or folder,
                patterns=patterns,
                unterordner={k: str(v) for k, v in subfolders.items()},
            ))

    # Absolute, because generated .desktop entries embed these paths and are
    # launched from an arbitrary working directory.
    return Config(
        active=active,
        uni_root=Path(raw.get("uni_root", "~/Uni")).expanduser().resolve(),
        downloads=Path(raw.get("downloads", "~/Downloads")).expanduser().resolve(),
        courses=courses,
        path=path,
        pdf_viewer=raw.get("pdf_viewer", "firefox"),
        alte_skripte_im_launcher=bool(raw.get("alte_skripte_im_launcher", True)),
    )


def load(path: Path | None = None) -> Config:
    config_path = Path(path).expanduser() if path else paths.CONFIG_FILE
    if not config_path.exists():
        raise ConfigError(f"No config at {config_path}.\n"
                          f"Create one with: assignmentvibe config init")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{config_path} is not valid JSON: {e}") from e
    return parse(raw, config_path)
