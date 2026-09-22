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

import pymupdf

# A title that numbers itself ("1. Graphs", "2.3 Bipartite graphs"). The node
# carries its own key, so the duplicate leading number is dropped.
LEADING_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


def _clean(title: str) -> str:
    return LEADING_NUMBER_RE.sub("", " ".join(title.split())).strip()


def outline_tree(pdf_path: Path) -> list[dict]:
    """The PDF's bookmarks as [{"key", "level", "title", "page"}], in reading
    order. Empty when the PDF has no outline."""
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
    placed = 0
    for e in entries:
        page = e.get("page") or 0
        current = None
        for n in by_page:
            if n["page"] <= page:
                current = n["key"]
            else:
                break
        e["section"] = current
        placed += current is not None
    return placed


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


def sort_key(key: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in key.split("."))


def label(nodes: dict[str, str], key: str) -> str:
    """'3.1' -> '3.1 Konvexe Funktionen', or the bare key when the script had no
    outline and there is no title to show."""
    title = nodes.get(key)
    return f"{key} {title}" if title else key
