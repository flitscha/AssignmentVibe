"""
Slide decks -> one knowledge entry per slide.

A course taught from slides has no "Satz 3.1.5" to pick: Automata and Logic and
Computability Theory hand out one Beamer deck per lecture (01x1.pdf, 02x1.pdf)
and no script. What a task needs from them is a handful of slides, so a slide
is the unit - an entry like a script's statement, with its deck and page, so
that Jev can judge it, the prompt can carry it and the panel can open the deck
right there.

    {"kind": "slide", "type": "Slide", "id": "Lecture 1, slide 16",
     "name": "Definition", "text": "class PR of primitive recursive ...",
     "page": 16, "section": "S1.3", "pdf": "/home/.../01x1.pdf"}

Sections are the decks ("S1", one per lecture) and the parts of their outline
("S1.3 Primitive Recursive Functions"). The "S" keeps them apart from a
script's chapters when a course has both; core.toc.sort_key puts them after.

What is left out, because it is not content:
  - the page footer every slide repeats ("26W / Computability Theory /
    lecture 1 / 3. Primitive Recursive Functions / 16/37"),
  - the title page and anything else before the outline's first entry,
  - "Outline" slides that only list the outline again,
  - overlay steps: a slide whose text the next slide repeats and extends.

Depends on core.pdf_text and core.toc (both pure).
"""

import re
from collections import Counter
from pathlib import Path

from .pdf_text import normalize
from .toc import LEADING_NUMBER_RE

# Bumped whenever what an ingest writes changes; see core.knowledge.FORMAT.
FORMAT = 1

# "16/37", "16 / 37" - the page counter in a Beamer footer.
COUNTER_RE = re.compile(r"^\d+\s*/\s*\d+$")
OUTLINE_TITLES = {"outline", "overview", "agenda", "contents", "table of contents",
                  "inhalt", "inhaltsverzeichnis", "gliederung", "übersicht"}
# A line on this share of the pages or more is the deck's furniture, not content.
FOOTER_SHARE = 0.6
DECK_NUMBER_RE = re.compile(r"^(\d+)|(\d+)(?!.*\d)")


def deck_number(pdf_path: Path) -> int | None:
    """01x1.pdf -> 1, 03-opt.pdf -> 3, lecture12.pdf -> 12."""
    m = DECK_NUMBER_RE.search(pdf_path.stem)
    return int(m.group(1) or m.group(2)) if m else None


def _plain(title: str) -> str:
    """A title reduced to its letters and digits, for comparing: the footer
    spells "Course – of – Values Recursion" where the outline has
    "Course–of–Values Recursion"."""
    return re.sub(r"[\W_]+", "", LEADING_NUMBER_RE.sub("", title.strip()).lower())


def _strip_furniture(lines: list[str], furniture: set[str], titles: set[str]) -> list[str]:
    """The lines of a page without the header and footer around them."""
    def is_furniture(line: str) -> bool:
        return (line in furniture or COUNTER_RE.match(line) is not None
                or _plain(line) in titles)

    while lines and is_furniture(lines[-1]):
        lines = lines[:-1]
    while lines and lines[0] in furniture:
        lines = lines[1:]
    return lines


def _is_outline(lines: list[str], titles: set[str]) -> bool:
    """An "Outline" slide repeats the deck's outline and says nothing else."""
    if not lines or _plain(lines[0]) not in OUTLINE_TITLES:
        return False
    return all(_plain(line) in titles for line in lines[1:])


def extract(pdf_path: Path, number: int) -> tuple[list[dict], list[dict]]:
    """(sections, entries) of one deck. `number` is the deck's place in the
    course - the lecture it belongs to."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        pages = [normalize(p.get_text("text")) for p in doc]
        outline = doc.get_toc()

    # A deck's outline usually wraps everything in one entry ("lecture 1");
    # its parts are then one level down.
    top = [e for e in outline if e[0] == 1]
    parts_level = 2 if len(top) == 1 else 1
    parts = [(" ".join(t.split()), p) for lvl, t, p in outline
             if lvl == parts_level and t.strip()]
    titles = {_plain(t) for _, t, _ in outline if t.strip()}
    deck_title = (" ".join(top[0][1].split()) if len(top) == 1 else "")
    deck_title = (deck_title[:1].upper() + deck_title[1:]) if deck_title \
        else f"Lecture {number}"

    lines_per_page = [[l.strip() for l in text.split("\n") if l.strip()] for text in pages]
    seen = Counter(line for lines in lines_per_page for line in set(lines))
    furniture = ({line for line, n in seen.items() if n >= FOOTER_SHARE * len(pages)}
                 if len(pages) >= 5 else set())
    first = min((p for _, _, p in outline if p > 0), default=1)

    deck_key = f"S{number}"
    sections = [{"key": deck_key, "level": 1, "title": deck_title, "page": first,
                 "pdf": str(pdf_path)}]
    for i, (title, page) in enumerate(parts, start=1):
        sections.append({"key": f"{deck_key}.{i}", "level": 2, "title": title,
                         "page": page, "pdf": str(pdf_path)})

    entries = []
    for index, raw in enumerate(lines_per_page):
        page = index + 1
        if page < first:
            continue
        lines = _strip_furniture(raw, furniture, titles)
        if not lines or _is_outline(lines, titles):
            continue
        part = sum(1 for _, p in parts if p <= page)
        entries.append({
            "kind": "slide",
            "type": "Slide",
            "id": f"{deck_title}, slide {page}",
            "number": f"{number}.{page}",
            "name": lines[0],
            "text": "\n".join(lines[1:]),
            "page": page,
            "chapter": None,
            "section": f"{deck_key}.{part}" if part else deck_key,
            "proof": None,
            "pdf": str(pdf_path),
        })

    return sections, _drop_overlay_steps(entries)


def _drop_overlay_steps(entries: list[dict]) -> list[dict]:
    """A Beamer slide built up step by step is one page per step, each
    repeating the one before; only the last, complete one is kept."""
    kept = []
    for e, after in zip(entries, entries[1:] + [None]):
        if (after is not None and after["page"] == e["page"] + 1
                and after["name"] == e["name"] and after["text"].startswith(e["text"])):
            continue
        kept.append(e)
    return kept


def extract_decks(pdfs: list[Path]) -> tuple[list[dict], list[dict]]:
    """(sections, entries) of a course's decks, numbered by the number in
    their file name, else by their order."""
    numbered = sorted(((deck_number(p), p) for p in pdfs),
                      key=lambda np: (np[0] is None, np[0] or 0, np[1].name))
    sections, entries, used = [], [], set()
    for position, (number, pdf) in enumerate(numbered, start=1):
        if number is None or number in used:
            number = max(used | {0}) + 1
        used.add(number)
        s, e = extract(pdf, number)
        sections += s
        entries += e
    return sections, entries
