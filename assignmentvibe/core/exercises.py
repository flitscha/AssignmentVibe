"""
The exercises a script carries itself - so that a sheet saying only "Lösen Sie
Aufgabe (1.1) vom Skriptum" can hand the model the actual task.

That is not a corner case. Every task on every PS Optimierung sheet is such a
reference, and without this the prompt carried the one sentence and nothing
the model could work on.

WHERE EXERCISES ARE LOOKED FOR. Only inside the sections the script's outline
calls "Aufgaben" / "Übungsaufgaben" / "Exercises" - never in running text. The
numbering "(1.1)" that VO3_Optimierung uses for its exercises is also how
scripts number equations, so matching it anywhere would turn every labelled
formula into an exercise. Inside such a section the outline has already said
what the text is, and the numbers only have to separate one item from the next.

A section ends where the next outline node starts, which is a PAGE; running
headers ("1.6 Aufgaben", "1 Geometrie linearer Ungleichungen") and page numbers
are stripped per page so they do not end up in the middle of an exercise that
spans a page break.

WHAT IS NOT COVERED. Exercises scattered through running text ("Exercise 1.2."
in the spectral graph theory notes, "Übung 12.47." in Stochastik) have no
section to delimit them - where one ends is a judgement about prose. And a
script without bookmarks has no outline to find the section in. Both yield no
exercises rather than wrong ones.

Depends on nothing else in this project (pages + outline nodes in, dicts out).
"""

import re

EXERCISE_SECTION_RE = re.compile(
    r"^(?:Aufgaben|Übungsaufgaben|Übungen|Exercises|Problems)$", re.IGNORECASE)

# "(1.1) Title: ..." (VO3_Optimierung), "Aufgabe 1. ..." (Algebra,
# Lineare_Algebra_I_II - "Aufgabe6." without the space too), "Exercise 2.4."
EXERCISE_START_RE = re.compile(
    r"(?m)^(?:\((?P<paren>\d+(?:\.\d+)*)\)"
    r"|(?:Aufgabe|Übungsaufgabe|Übung|Exercise|Problem)\s*(?P<word>\d+(?:\.\d+)*)\.?)"
    r"[ \t]*"
)

# A title is the phrase before the first colon, if the exercise opens with one:
# "(1.1) Operationen mit konvexen Mengen: Wir betrachten ...". It may wrap
# onto a second line, and it may be hyphenated across that wrap.
TITLE_RE = re.compile(r"^(?P<title>[^:\n]{3,80}(?:\n[^:\n]{1,60})?):")

PAGE_NUMBER_RE = re.compile(r"^(?:\d+|[ivxlc]+)$", re.IGNORECASE)

# How far the numbering may jump before a line start is no longer believed to
# be the next exercise. Exactly +1 would be the strict reading, but then one
# number lost to the text extraction would end the whole section; a back-
# reference "(1.3)" at a line start is still rejected, since it goes backwards.
MAX_NUMBER_GAP = 3


def _last_part(number: str) -> int:
    return int(number.rsplit(".", 1)[-1])


def _running_headers(nodes: list[dict]) -> set[str]:
    headers = set()
    for n in nodes:
        title = " ".join(n.get("title", "").split())
        if title:
            headers.add(title.lower())
            headers.add(f"{n['key']} {title}".lower())
    return headers


def _clean_page(page: str, headers: set[str]) -> list[str]:
    lines = [line.rstrip() for line in page.splitlines()]
    while lines and (not lines[0].strip()
                     or " ".join(lines[0].split()).lower() in headers):
        lines.pop(0)
    while lines and (not lines[-1].strip() or PAGE_NUMBER_RE.match(lines[-1].strip())):
        lines.pop()
    return lines


def _join_title(raw: str) -> str:
    # "Un-\nteraufgaben" -> "Unteraufgaben"; a plain wrap is just a space.
    return " ".join(re.sub(r"-\n(?=[a-zäöüß])", "", raw).split())


def extract(pages: list[str], nodes: list[dict]) -> list[dict]:
    """[{"number", "title", "text", "page", "section"}] for every exercise found
    in an exercise section of the outline, in reading order."""
    headers = _running_headers(nodes)
    exercises = []

    for i, node in enumerate(nodes):
        if not EXERCISE_SECTION_RE.match(node.get("title", "").strip()):
            continue
        start = node.get("page") or 0
        if start < 1:
            continue
        following = [n["page"] for n in nodes[i + 1:] if n.get("page", 0) > start]
        end = following[0] - 1 if following else len(pages)

        # Keep the page each line came from, so every exercise knows where it
        # starts - that is what a reader looks up in the PDF.
        lines: list[tuple[int, str]] = []
        for page_num in range(start, end + 1):
            if page_num > len(pages):
                break
            lines += [(page_num, line) for line in _clean_page(pages[page_num - 1], headers)]
        text = "\n".join(line for _, line in lines)
        offsets = []
        pos = 0
        for page_num, line in lines:
            offsets.append((pos, page_num))
            pos += len(line) + 1

        def page_at(offset: int) -> int:
            page = start
            for off, num in offsets:
                if off > offset:
                    break
                page = num
            return page

        starts = []
        previous = None
        for m in EXERCISE_START_RE.finditer(text):
            number = m.group("paren") or m.group("word")
            last = _last_part(number)
            if previous is not None and not (0 < last - previous <= MAX_NUMBER_GAP):
                continue
            starts.append((m, number))
            previous = last

        for j, (m, number) in enumerate(starts):
            stop = starts[j + 1][0].start() if j + 1 < len(starts) else len(text)
            body = text[m.end():stop].strip()
            title = None
            t = TITLE_RE.match(body)
            if t:
                title = _join_title(t.group("title"))
                body = body[t.end():].strip()
            exercises.append({
                "number": number,
                "title": title,
                "text": body,
                "page": page_at(m.start()),
                "section": node["key"],
            })

    return exercises


def find(exercises: list[dict], number: str) -> dict | None:
    return next((e for e in exercises if e["number"] == number), None)
