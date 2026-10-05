"""
The chapter/section tree a script is chunked into, and which entry sits where.

WHY THIS IS NOT DERIVED FROM THE LABELS. The obvious move is to read the
structure out of the entry labels: "Satz 4.1.4" is chapter 4, section 1. That
works for exactly the kind of script it was written against and breaks on
everything else, because the numbering DEPTH is a per-document choice:

    VO3_Optimierung, Algebra, Lineare_Algebra_I_II   "Satz 4.1.4"  chapter.section.index
    Stochastik, geom-tb, maingeo2023, graph theory   "Satz 1.2"    chapter.index

Read the second kind with the first kind's rule and "Satz 1.2" becomes section
1.2 - the Stochastik script then chunks into 283 pseudo-sections of 1.5 entries
each, which is no chunking at all.

So the structure comes from the PDF's own outline (its bookmarks) instead, and
an entry is placed by the PAGE it starts on: it belongs to the last section
that began at or before it. That needs no numbering convention, no language and
no heuristic, and it places 100% of the entries in all ten corpus documents.

KEYS ARE POSITIONAL, TITLES ARE REAL. A node's key ("3.1") is its path in the
outline tree, not whatever the book numbers that chapter. The two agree for the
scripts that number their sections and would only disagree where the book's own
numbering cannot be trusted anyway (Stochastik nests chapters under unnumbered
parts; the graph theory book carries its numbers inside the titles and puts an
unnumbered introduction in front of chapter 1). The user picks by title; the key
just has to be stable and orderable, and a path is both. A leading number in a
title is stripped, so the row reads "1 Graphs" rather than "1 1. Graphs".

WITHOUT BOOKMARKS (Analysis_4_Notes.pdf has none) there is nothing to read, so
the labels are used after all - but with the depth measured rather than assumed,
and only ever as a fallback.
"""

import re
from collections import Counter
from pathlib import Path

# pymupdf is imported where it is used, not here. It costs ~350ms to load,
# and the bar asks for the status every few seconds while none of that path
# opens a PDF - that import was most of what made the tool feel slow.

# A title that numbers itself ("1. Graphs", "2.3 Bipartite graphs"). The node
# carries its own key, so the duplicate leading number is dropped.
LEADING_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


def _clean(title: str) -> str:
    return LEADING_NUMBER_RE.sub("", " ".join(title.split())).strip()


def outline_tree(pdf_path: Path) -> list[dict]:
    """The PDF's bookmarks as [{"key", "level", "title", "page"}], in reading
    order. Empty when the PDF has no outline."""
    import pymupdf

    try:
        raw = pymupdf.open(pdf_path).get_toc()
    except Exception:
        return []

    nodes: list[dict] = []
    counters: list[int] = []
    for level, title, page in raw:
        # A jump from level 1 straight to level 3 has no level-2 parent to hang
        # from; clamping keeps the path contiguous instead of inventing one.
        level = max(1, min(level, len(counters) + 1))
        del counters[level:]
        while len(counters) < level:
            counters.append(0)
        counters[level - 1] += 1
        title = _clean(title)
        if not title:
            continue
        nodes.append({
            "key": ".".join(str(c) for c in counters),
            "level": level,
            "title": title,
            "page": page,
        })
    return nodes


def tree_from_numbers(entries: list[dict]) -> list[dict]:
    """Fallback for a PDF without bookmarks: the tree the entry labels imply.

    The depth is measured, not assumed - whichever of two-part ("1.2") and
    three-part ("1.2.3") numbering the majority of labels use decides whether
    the labels can name sections at all, or only chapters."""
    parts = [e["number"].split(".") for e in entries if e.get("number")]
    if not parts:
        return []
    depth = Counter(len(p) for p in parts).most_common(1)[0][0]

    seen: dict[str, int] = {}
    for p in parts:
        seen.setdefault(p[0], 0)
        if depth >= 3 and len(p) >= 2:
            seen.setdefault(f"{p[0]}.{p[1]}", 0)

    return [{"key": key, "level": key.count(".") + 1, "title": "", "page": 0}
            for key in sorted(seen, key=sort_key)]


def assign_sections(entries: list[dict], nodes: list[dict]) -> int:
    """Give every entry a "section" - the key of the last node starting at or
    before its page. Returns how many entries could be placed."""
    if not nodes:
        for e in entries:
            e["section"] = None
        return 0

    by_page = sorted(nodes, key=lambda n: n["page"])
    # The section running into each entry's page, then every one starting on it.
    candidates = []
    for e in entries:
        page = e.get("page") or 0
        here = []
        for n in by_page:
            if n["page"] < page:
                here = [n["key"]]
            elif n["page"] == page:
                here.append(n["key"])
            else:
                break
        candidates.append(here)
        e["section"] = here[-1] if here else None

    trusted = _numbers_match_outline(entries)
    for e, here in zip(entries, candidates):
        if trusted:
            e["section"] = _on_shared_page(e, here)
    return sum(1 for e in entries if e["section"] is not None)


def _prefix(entry: dict) -> str | None:
    number = entry.get("number") or ""
    return number.rsplit(".", 1)[0] if "." in number else None


def _covers(outer: str, key: str) -> bool:
    return key == outer or key.startswith(outer + ".")


def _numbers_match_outline(entries: list[dict]) -> bool:
    """Whether the script's numbering names its outline: "Satz 2.2.6" placed
    in 2.2 (or below it) for nearly every entry. True for the Algebra and
    Optimierung notes; not for maingeo2023, whose outline has a preface
    chapter in front, so its "Definition 1.1" lives in section 2.1."""
    numbered = [(p, e["section"]) for e in entries
                if (p := _prefix(e)) and e.get("section")]
    agree = sum(1 for p, s in numbered if _covers(p, s))
    return bool(numbered) and agree >= 0.8 * len(numbered)


def _on_shared_page(entry: dict, candidates: list[str]) -> str | None:
    """Which of the sections sharing a page an entry belongs to. The page
    alone says the last one, but a statement above the new heading still
    belongs to the old section - Satz 2.2.6 of the Algebra notes sits on the
    page where 2.3 begins. Where the entry's own number names one of the
    candidates, that one wins - unless it is a parent of the last one: a
    section and its first subsection often start on the same page, and then
    the subsection is the more precise answer. The numbering is only consulted
    here, where the page cannot decide, and only for a script whose numbering
    matches its outline (see the module docstring)."""
    last = candidates[-1] if candidates else None
    prefix = _prefix(entry)
    if len(candidates) > 1 and prefix in candidates and not _covers(prefix, last):
        return prefix
    return last


def assign_sections_from_numbers(entries: list[dict], nodes: list[dict]) -> int:
    """The bookmark-less counterpart: place an entry by its own label."""
    keys = {n["key"] for n in nodes}
    placed = 0
    for e in entries:
        parts = (e.get("number") or "").split(".")
        key = None
        if len(parts) >= 2 and f"{parts[0]}.{parts[1]}" in keys:
            key = f"{parts[0]}.{parts[1]}"
        elif parts and parts[0] in keys:
            key = parts[0]
        e["section"] = key
        placed += key is not None
    return placed


def build(pdf_path: Path, entries: list[dict]) -> list[dict]:
    """Chunk a script: outline if it has one, labels if it does not. Mutates
    the entries' "section" and returns the tree."""
    nodes = outline_tree(pdf_path)
    if nodes and assign_sections(entries, nodes) >= len(entries) // 2:
        return nodes
    nodes = tree_from_numbers(entries)
    assign_sections_from_numbers(entries, nodes)
    return nodes


# Slide decks are keyed "S1", "S1.3" (see core.slides) and come after every
# chapter of a script.
SLIDES_OFFSET = 10_000


def sort_key(key: str) -> tuple:
    def part(p: str) -> int:
        if p.isdigit():
            return int(p)
        if p[:1] == "S" and p[1:].isdigit():
            return SLIDES_OFFSET + int(p[1:])
        return 0
    return tuple(part(p) for p in key.split("."))


def is_slides(key: str) -> bool:
    return key[:1] == "S"


def label(nodes: dict[str, str], key: str) -> str:
    """'3.1' -> '3.1 Konvexe Funktionen', or the bare key when the script had no
    outline and there is no title to show. A part of a slide deck is named by
    its deck and title, the key being nothing a reader knows:
    'S1.3' -> 'Lecture 1 · Primitive Recursive Functions'."""
    title = nodes.get(key)
    if is_slides(key):
        deck = key.split(".")[0]
        if deck != key and nodes.get(deck):
            return f"{nodes[deck]} · {title or key}"
        return title or key
    return f"{key} {title}" if title else key
