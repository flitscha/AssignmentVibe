"""
~/.config/assignmentvibe/uni.json - the one file edited once per semester.

    {
      "active": "m1",
      "uni_root": "~/Uni",
      "downloads": "~/Downloads",
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
from dataclasses import dataclass
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

    def match(self, filename: str) -> str | None:
        """Which category this filename falls into, or None if it's not ours."""
        lower = filename.lower()
        for category in CATEGORIES:
            for pattern in self.patterns.get(category, []):
                if fnmatch.fnmatch(lower, pattern.lower()):
                    return category
        return None


@dataclass
class Config:
    active: str
    uni_root: Path
    downloads: Path
    courses: list[Course]
    path: Path

    def active_courses(self) -> list[Course]:
        return [c for c in self.courses if c.semester == self.active]

    def course_dir(self, course: Course) -> Path:
        return self.uni_root / course.semester / course.folder


def parse(raw: dict, path: Path) -> Config:
    active = raw.get("active")
    if not active:
        raise ConfigError('In der Config fehlt "active": "<semester>", z.B. "m1".')

    semesters = {k: v for k, v in (raw.get("semesters") or {}).items()
                 if not k.startswith("_")}
    if active not in semesters:
        known = ", ".join(semesters) or "(keine)"
        raise ConfigError(f'"active" ist "{active}", aber unter "semesters" gibt es '
                          f'dieses Semester nicht. Vorhanden: {known}.')

    courses = []
    for semester, folders in semesters.items():
        for folder, spec in folders.items():
            # JSON has no comments, so any key starting with "_" is treated as
            # a note and ignored - both as a course name and inside a course.
            if folder.startswith("_"):
                continue
            unknown = {k for k in spec if not k.startswith("_")} - {"name", *CATEGORIES}
            if unknown:
                raise ConfigError(f'{semester}/{folder}: unbekannte Felder '
                                  f'{sorted(unknown)}. Erlaubt: name, {", ".join(CATEGORIES)}.')
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
            ))

    # Absolute, because generated .desktop entries embed these paths and are
    # launched from an arbitrary working directory.
    return Config(
        active=active,
        uni_root=Path(raw.get("uni_root", "~/Uni")).expanduser().resolve(),
        downloads=Path(raw.get("downloads", "~/Downloads")).expanduser().resolve(),
        courses=courses,
        path=path,
    )


def load(path: Path | None = None) -> Config:
    config_path = Path(path).expanduser() if path else paths.CONFIG_FILE
    if not config_path.exists():
        raise ConfigError(f"Keine Config unter {config_path}.\n"
                          f"Anlegen mit: assignmentvibe config init")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{config_path} ist kein gueltiges JSON: {e}") from e
    return parse(raw, config_path)
