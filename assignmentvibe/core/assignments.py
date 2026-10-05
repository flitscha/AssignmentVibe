"""
Step 3: assignment sheet (PDF) -> structured task list.

Tested against two very different sheet formats:
- Algebra ("A01.pdf" .. "A14.pdf"): "Aufgabe N" on its own line, text follows.
- PS Optimierung ("01-Blatt-PS-Optimierung.pdf" .. "12-..."): "Aufgabe N: Titel."
  on one line, often with sub-parts a)/b)/c) and references to tasks that
  live inside the script itself ("vom Skriptum").

Other courses number their tasks "(1)", "1." or "1)" instead (see
TASK_STYLES); each sheet is read in whichever style gives the longest run of
task numbers going up.

Note: regexes below match literal German words ("Aufgabe", "Besprechung",
"Blatt", "vom Skriptum") because that's what appears in the source PDFs -
this is domain data being matched, not something to translate. The output
JSON schema keys, however, are English (see parse_assignment_sheet).

Depends only on core.pdf_text (for text normalization) and pymupdf.
"""

import json
import re
import sys
from pathlib import Path

# pymupdf is imported where it is used, not here. It costs ~350ms to load,
# and the bar asks for the status every few seconds while none of that path
# opens a PDF - that import was most of what made the tool feel slow.

from .pdf_text import normalize

# How a sheet numbers its tasks. Every sheet uses one of these, but which one
# differs by course: "Aufgabe 3" (Algebra, Optimierung), "(3) Titel:" (PS
# Analysis, PDE, Numerik), "3. ..." (Geometrie, Category Theory, Stochastik 2),
# "17) ..." (Diskrete Mathematik, numbered on across all sheets). A number
# must be followed by text on the same line, so an equation label "(1)" on a
# line of its own is not a task. A task that opens with a displayed formula
# has its number alone on the line too, though; the second pattern of a style
# finds those, and they are only taken where they fill a gap in the numbering
# (see _fill_gaps).
TASK_STYLES = [
    (re.compile(r"(?m)^(?:Aufgabe|Exercise|Problem)\s+(?P<num>\d+)\s*[:.]?[ \t]*"), None),
    (re.compile(r"(?m)^\((?P<num>\d+)\)[ \t]*(?=\S)"),
     re.compile(r"(?m)^\((?P<num>\d+)\)[ \t]*$")),
    # "1.Überprüfen": the umlaut repair in core.pdf_text eats the space in
    # front of a detached "¨U". A digit after the dot is a number ("1.2").
    (re.compile(r"(?m)^(?P<num>\d+)\.(?:[ \t]+(?=\S)|(?=[^\W\d_]))"),
     re.compile(r"(?m)^(?P<num>\d+)\.[ \t]*$")),
    (re.compile(r"(?m)^(?P<num>\d+)\)[ \t]*(?=\S)"),
     re.compile(r"(?m)^(?P<num>\d+)\)[ \t]*$")),
]
# How far the numbering may jump from one task to the next before a match is
# taken for something else (a date, a list inside a task).
MAX_TASK_GAP = 2
SUBPART_RE = re.compile(r"(?m)^\s*\(?(?P<label>[a-h]|i{1,3}v?|vi{0,3})\)\s")
DISCUSSION_DATE_RE = re.compile(r"Besprechung(?:stermin)?(?:\s+am)?:?\s*(?P<date>[^\n)]+)")
# "Aufgabe (1.1) vom Skriptum", "Programmieraufgabe (2.8) vom Skriptum", and
# the plainer "Aufgabe 1.1 aus dem Skript" / "im Skriptum" other courses write,
# and "im Skrip-\ntum" hyphenated across a line (sheet 12).
SCRIPT_REF_RE = re.compile(
    r"(?:Programmier|Übungs)?[Aa]ufgabe\s*\(?(?P<ref>\d+(?:\.\d+)?)\)?\s*"
    r"(?:vom|aus\s+dem|im)\s*Skrip(?:-\s*)?t(?:um)?")
# The page footer the PS Optimierung sheets carry; it would otherwise end up as
# the last line of the last task.
PAGE_FOOTER_RE = re.compile(r"(?m)^\s*Seite\s+\d+\s+von\s+\d+\s*$\n?")
# Same idea as core.knowledge.FORMAT.
#   2: page footers stripped, wider script references
#   3: tasks numbered "(1)", "1." and "1)" too; sheet number from the header
#      or the file name; OT1 ligatures
#   4: T1 "ÿ" read as ß (see core.pdf_text)
#   5: a last task whose number stands alone above its "(a)"
FORMAT = 5

# Looked for in the sheet's header only - further down, "Blatt 2" is a task
# referring to an earlier sheet.
SHEET_NUM_RE = re.compile(
    r"(?:Blatt|Problem Set|Sheet)\s+(?P<num>\d+)"
    r"|(?P<pre>\d+)\.\s*Übungsblatt", re.IGNORECASE)
HEADER_CHARS = 400
FILE_NUM_RE = re.compile(r"(\d+)(?!.*\d)")


def extract_pdf_text(pdf_path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    return "\n".join(normalize(p.get_text("text")) for p in doc)


# --- Task titles ----------------------------------------------------------------
# Some courses give every task a heading ("(2) Produkttopologie: Es sei ...",
# "Aufgabe 3: Konvexe Funktionen.", "Erwartungstreue" on a line of its own);
# most give none and start with the task itself ("Sei G eine Gruppe. ...").
# Taking the first short sentence as the title made "Sei G eine Gruppe",
# "Zeigen Sie" and "1" titles. A title is what reads like a heading: short, no
# formula, and not opening the way a task sentence opens.

# The end of a heading on the task's first line. Not a dot of an abbreviation
# ("Maximum-Likelihood-Estimator (MLE) vs. Bayes").
TITLE_END_RE = re.compile(r"(?<!\bvs)(?<!\bbzw)(?<!\bd\.h)(?<!\bz\.B)(?<!\bi\.e)(?<!\be\.g)"
                          r"(?<!\bca)(?<!\bvgl)[.:](?=\s)")
# Words a task sentence opens with. No heading starts with one.
STARTER_WORDS = set("""
    sei seien es zeigen zeige beweisen beweise bestimmen bestimme berechnen berechne
    gegeben betrachte betrachten wir man für finden finde geben gib lösen löse
    skizzieren skizziere verwenden verwende implementieren implementiere programmieren
    programmiere nehmen überprüfen untersuchen untersuche diagonalisieren interpolieren
    setzen variieren stellen lese lies lesen definieren definiere begründen ermitteln
    vervollständigen versuchen importieren wie was welche ein eine einen der die das
    den dem auf im in an ist sind
    let show prove suppose consider determine find compute calculate we the a an for
    given if write describe use using recall
""".split())
# Words only a sentence has. A heading before a colon may still have one
# ("Kompakte Intervalle sind kompakt:"); one before a full stop or on a line
# of its own may not - that is the task's first sentence.
SENTENCE_WORDS = set("""
    sei seien ist sind gilt gelte hat haben wird werden sie wir man kann können soll
    sollen is are be let we
""".split())
MATH_CHARS = set("=∈∉⊂⊆⊃⊇→←↦≤≥<>|{}[]∀∃^_∗·∑∫∞⩾⩽≠≈×")
MAX_TITLE_CHARS = 70
MAX_TITLE_WORDS = 8
# A subpart label opening the next line: "a)", "(a)", "(i)".
NEXT_PART_RE = re.compile(r"^\(?(?:[a-h]|i{1,3}v?|vi{0,3})[).]")


def _heading(text: str, before_colon: bool) -> str | None:
    """`text` as a title, if it reads like one."""
    title = " ".join(re.sub(r"-\n(?=[a-zäöüß])", "", text).split())
    if title.startswith("(") and title.endswith(")"):
        title = title[1:-1].strip()          # "(Hermite-Interpolation)."
    words = [w.strip(",;()").lower() for w in title.split()]
    if not words or len(title) > MAX_TITLE_CHARS or len(words) > MAX_TITLE_WORDS:
        return None
    if not title[0].isalpha() or SUBPART_RE.match(title + " ") or words[0] in STARTER_WORDS:
        return None
    # "Radiale Lösungen der Wellengleichung in d = 3:" - one sign before a
    # colon is a heading's; anywhere else any is a formula's.
    if sum(c in MATH_CHARS for c in title) > (1 if before_colon else 0):
        return None
    if not before_colon and any(w in SENTENCE_WORDS for w in words):
        return None
    return title


def guess_title(body: str) -> str | None:
    """The heading a task opens with, or None - see STARTER_WORDS above."""
    body = body.strip()
    m = TITLE_END_RE.search(body)
    if m and m.start() <= 2 * MAX_TITLE_CHARS:
        head = re.sub(r"-\n(?=[a-zäöüß])", "", body[:m.start()])
        before_colon = body[m.start()] == ":"
        last_line = head.rsplit("\n", 1)[-1].strip()
        # A heading wraps onto a second line only before a colon, and the
        # dot of "Erwartungstreue Schätzer\na. Seien ..." ends a subpart label.
        if "\n" not in head or (before_colon and not NEXT_PART_RE.match(last_line)):
            title = _heading(head, before_colon)
            if title:
                return title
    # A heading on a line of its own, the task starting on the next.
    first, _, rest = body.partition("\n")
    rest = rest.lstrip()
    if (rest and (rest[0].isupper() or NEXT_PART_RE.match(rest))
            and not first.rstrip().endswith((",", "-"))):
        return _heading(first, before_colon=False)
    return None


def title_of(task: dict) -> str | None:
    """A task's title, read from its text each time - so a sheet read in
    before the rule above changed gets the new title without reading it in
    again."""
    return guess_title(task.get("text") or "")


def split_subparts(body: str) -> list[dict]:
    matches = list(SUBPART_RE.finditer(body))
    if len(matches) < 2:
        return []
    parts = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        parts.append({"label": m.group("label"), "text": body[m.end():end].strip()})
    return parts


def _run_from(matches: list[re.Match], first: int) -> list[re.Match]:
    run = [matches[first]]
    for m in matches[first + 1:]:
        if 0 < int(m.group("num")) - int(run[-1].group("num")) <= MAX_TASK_GAP:
            run.append(m)
    return run


def _num(m: re.Match) -> int:
    return int(m.group("num"))


def _fill_gaps(run: list[re.Match], lone: list[re.Match]) -> list[re.Match]:
    """`run` with the numbers it skips filled in from `lone` - "(3)" on a line
    of its own between task 2 and task 4, or "1." and "2." before a run that
    starts at 3. Only exactly the next missing number is taken, in order.

    After the last task, a lone number is taken only when a part "(a)" follows
    it straight away: the last task of Automata and Logic's sheet 1 is "4." on
    its own line above "(a) Prove that ...". Without that, an equation label
    "(4)" below the last task would become a task of its own."""
    filled = []
    prev_pos, expected = -1, 1 if _num(run[0]) > 1 else _num(run[0])
    for m in run:
        for candidate in lone:
            if prev_pos < candidate.start() < m.start() and _num(candidate) == expected < _num(m):
                filled.append(candidate)
                expected += 1
        filled.append(m)
        prev_pos, expected = m.start(), _num(m) + 1
    for candidate in lone:
        if (candidate.start() > prev_pos and _num(candidate) == expected
                and NEXT_PART_RE.match(candidate.string[candidate.end():].lstrip())):
            filled.append(candidate)
            prev_pos, expected = candidate.start(), expected + 1
    return filled


def find_tasks(text: str) -> list[re.Match]:
    """The task headings: of every style and every starting point, the longest
    run of numbers going up. Ties go to the style listed first. A header line
    "3. Übungsblatt" starts a run of its own and loses to the real one."""
    best: list[re.Match] = []
    best_lone = None
    for style, lone in TASK_STYLES:
        matches = list(style.finditer(text))
        for first in range(len(matches)):
            run = _run_from(matches, first)
            if len(run) > len(best):
                best, best_lone = run, lone
    if best and best_lone is not None:
        best = _fill_gaps(best, list(best_lone.finditer(text)))
    return best


def sheet_number(text: str, pdf_path: Path) -> int | None:
    m = SHEET_NUM_RE.search(text[:HEADER_CHARS])
    if m:
        return int(m.group("num") or m.group("pre"))
    m = FILE_NUM_RE.search(pdf_path.stem)
    return int(m.group(1)) if m else None


def parse_assignment_sheet(pdf_path: Path) -> dict:
    text = PAGE_FOOTER_RE.sub("", extract_pdf_text(pdf_path))

    discussion_date = DISCUSSION_DATE_RE.search(text)

    matches = find_tasks(text)
    tasks = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        script_refs = [rm.group("ref") for rm in SCRIPT_REF_RE.finditer(body)]
        tasks.append({
            "number": int(m.group("num")),
            "title": guess_title(body),
            "text": body,
            "subparts": split_subparts(body),
            "script_references": script_refs or None,
        })

    return {
        "format": FORMAT,
        "source": pdf_path.name,
        "sheet_number": sheet_number(text, pdf_path),
        "discussion_date": discussion_date.group("date").strip() if discussion_date else None,
        "num_tasks": len(tasks),
        "tasks": tasks,
    }


def run(in_path: Path, out_path: Path) -> None:
    result = parse_assignment_sheet(in_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{in_path.name}: {result['num_tasks']} tasks -> {out_path}")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
