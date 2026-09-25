"""
Step 2: raw text -> structured knowledge base (definitions, theorems, lemmas,
corollaries, examples, remarks, proofs).

Numbering is NOT interpreted here. "Satz 1.3.4" keeps its number verbatim;
which chapter and section that entry belongs to is decided by core.toc from the
PDF's outline, because the depth of the numbering varies between scripts and
reading "Satz 1.2" as section 1.2 shatters a script into pseudo-sections (see
core.toc for the measurements).

A plain line-start regex is NOT enough though: a back-reference like
"Satz 1.3.3" inside a later proof can end up at the start of a line by pure
chance (PDF line wrapping) and would be misdetected as a new block
(observed while testing against VO3_Optimierung.pdf: "Satz 1.3.3" showed up
this way in the middle of a KKT proof in chapter 3 and dragged along a
200-line block of unrelated text). That's why every regex match is verified
against the bold/italic detection from font_styles.py (see there) - only
genuinely styled headers count as a block boundary, everything else stays
part of the surrounding block.

Depends on core.font_styles, core.toc and core.exercises (and, transitively, core.pdf_text).
"""

import json
import re
import sys
from pathlib import Path

from . import exercises as exercises_core
from . import toc
from .font_styles import styled_type_words_per_page

# Literal German theorem-type words - see font_styles.py for why these are
# not translated (they must match the actual German source text).
NUMBERED_TYPES = [
    "Bemerkung/Beispiel",
    "Definition",
    "Satz",
    "Lemma",
    "Korollar",
    "Proposition",
    "Bemerkung",
    "Beispiel",
    "Algorithmus",
    "Konstruktion",
    # English scripts. Longest-first matters inside the alternation only for
    # prefixes of one another, which these are not; order otherwise follows the
    # German list so the two stay readable side by side.
    "Theorem",
    "Corollary",
    "Remark",
    "Example",
    "Algorithm",
    "Exercise",
    "Notation",
    "Claim",
    "Construction",
]

# \s* instead of \s+ between type and number: in at least one spot in the
# Algebra script the PDF text is missing the kerning/space
# ("Definition7.4.4" instead of "Definition 7.4.4").
NUMBERED_RE = re.compile(
    r"(?m)^(?P<type>" + "|".join(re.escape(t) for t in NUMBERED_TYPES) + r")"
    r"\s*(?P<num>\d+\.\d+(?:\.\d+)?)\.?"
    r"(?:\s*\((?P<name>[^)]{1,80})\))?"
)

# How the corpus actually writes a proof header, all of which have to match:
#   "Beweis."            everywhere            "Proof."       notes48, graphs
#   "Beweis:"            complex_analysis, Stochastik
#   "Beweis von Satz 1.2."       Stochastik, geom-tb - the reference eats the
#                                dot, so a second mandatory one made these fail
#   "Beweis (Satz von Thales)"   geom-tb - a parenthesised name instead
#
# The closing punctuation is only optional after a parenthesised name. A bare
# reference does NOT excuse it: "wie im Beweis von Satz 3.2.5 gezeigt" wraps
# onto a line start in Algebra, matches the reference form exactly, and then
# consumes the page's one styled "Beweis." - which rejected the real proof
# below it. Real headers end the line there, running text carries on. Dropping it unconditionally looked harmless and was
# not: "Beweis ist dann klar" and "Beweis gezeigt werden kann" wrap onto a line
# start in running text often enough, and each false match CONSUMES the page's
# styled "Beweis." header, so the real proof right below it was then rejected
# and stayed inside its theorem - five leaks in Algebra and Analysis_4_Notes
# that the stricter form does not have. (?!\w) keeps "Beweise" out either way.
PROOF_RE = re.compile(
    r"(?m)^(?P<type>Beweis|Proof)(?!\w)"
    r"(?:"
    r"\s*\([^)]{1,80}\)\s*[.:]?"
    r"|(?:\s+(?:von\s+|of\s+)?(?P<ref>Satz|Lemma|Korollar|Proposition|Theorem|Corollary)"
    r"\s+(?P<refnum>\d+(?:\.\d+)+))?\s*[.:]"
    r")"
)

# Bumped whenever what an ingest writes changes in a way an older file lacks.
# store.ingest_missing re-reads a script whose knowledge base is older than
# this, so an update reaches existing courses without anyone knowing to ask.
#   2: the script's own exercises ("exercises", see core.exercises)
FORMAT = 2

PAGE_MARK_RE = re.compile(r"\x0cPAGE(\d+)\x0c")

# Every chapter ends with unlabeled sections ("4.4 Aufgaben", "4.3 Literatur
# und Ausblick") containing exercises or bibliography - not a Satz/Definition,
# but also without its own bold header. Without recognizing these as a block
# boundary, the entire rest of the chapter (often several pages of exercises)
# would get appended to the last Satz/Lemma of the chapter as its "text"
# (observed: "Satz 4.2.6" got inflated to over 100 lines this way).
SECTION_BOUNDARY_RE = re.compile(
    r"(?m)^(?:\d+\.\d+\s+(?:Aufgaben|Literatur und Ausblick|Exercises|Notes)"
    r"|Literaturverzeichnis|Übungsaufgaben|Index"
    r"|Literatur|References|Bibliography)\s*$"
)


def load_pages(path: Path) -> tuple[list[str], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["pages"], data["source"]


def build_joined_text(pages: list[str]) -> str:
    parts = []
    for i, p in enumerate(pages):
        parts.append(f"\x0cPAGE{i + 1}\x0c\n")
        parts.append(p)
    return "".join(parts)


def page_at(offset: int, page_marks: list[tuple[int, int]]) -> int:
    page = 1
    for pos, num in page_marks:
        if pos <= offset:
            page = num
        else:
            break
    return page


class HeaderVerifier:
    """Verifies regex matches against the font-style-detected real headers
    (per page). "Bemerkung/Beispiel" is accepted as its own combined type when
    "Bemerkung" and "Beispiel" appear bold back-to-back.

    A styled word is matched ANYWHERE in its page's queue, not just at the head.
    Strict head matching assumed the two detectors see exactly the same headers
    in exactly the same order, and one disagreement then poisoned the whole rest
    of the page: on page 65 of VO3_Optimierung the styled reading order is
    [Beweis, Bemerkung, Satz, Algorithmus, Beweis] while the text regex finds
    [Beweis, Bemerkung 4.1.3, Satz 4.1.4, Beweis] - the algorithm header sits in
    a float and never reaches the text stream at a line start. The head-matching
    queue stalled on it and rejected the trailing Beweis, so the proof of Satz
    4.1.4 stayed glued inside the theorem's own text, where include_proof=False
    cannot reach it and it leaked into hint prompts.

    Matching anywhere still requires a styled header of that exact type to exist
    on that page and consumes it, so a back-reference in running text is only
    accepted when the page genuinely has an unclaimed header of its type - the
    false positives this was built to reject (6 across the corpus) stay rejected,
    while 6 wrongly-swallowed proofs and 6 lost entries come back."""

    def __init__(self, styled_words_per_page: list[list[str]]):
        self._queues = [list(words) for words in styled_words_per_page]

    def consume(self, page: int, type_: str) -> bool:
        idx = page - 1
        if idx < 0 or idx >= len(self._queues):
            return False
        queue = self._queues[idx]
        if type_ == "Bemerkung/Beispiel":
            for i in range(len(queue) - 1):
                if queue[i] == "Bemerkung" and queue[i + 1] == "Beispiel":
                    del queue[i:i + 2]
                    return True
            return False
        if type_ in queue:
            queue.remove(type_)
            return True
        return False


def extract_knowledge(text: str, styled_words_per_page: list[list[str]]) -> tuple[list[dict], int]:
    page_marks = [(m.start(), int(m.group(1))) for m in PAGE_MARK_RE.finditer(text)]
    verifier = HeaderVerifier(styled_words_per_page)

    raw_matches = []
    for m in NUMBERED_RE.finditer(text):
        raw_matches.append(("numbered", m))
    for m in PROOF_RE.finditer(text):
        raw_matches.append(("proof", m))
    for m in SECTION_BOUNDARY_RE.finditer(text):
        raw_matches.append(("boundary", m))
    raw_matches.sort(key=lambda t: t[1].start())

    # matches also contains "boundary" entries: they don't become their own
    # knowledge block, but they do cap the block right before them.
    matches = []
    rejected = 0
    for kind, m in raw_matches:
        if kind == "boundary":
            matches.append((kind, m))
            continue
        page = page_at(m.start(), page_marks)
        # A proof header that names what it proves ("Beweis von Satz 3.2.3 bzw.
        # Lemma 2.1.5.") is self-evidencing and does not need the font to agree.
        # Algebra sets exactly that line in the regular weight while the ordinary
        # "Beweis." above it is italic, so the page offers one styled proof word
        # for two real headers - and the styled one was spent on the first,
        # leaving the second glued inside its theorem. Running text cannot fake
        # this form: it has to close with punctuation straight after the number,
        # which "wie im Beweis von Satz 3.2.5 gezeigt" does not.
        if kind == "proof" and m.group("ref"):
            matches.append((kind, m))
        elif verifier.consume(page, m.group("type")):
            matches.append((kind, m))
        else:
            rejected += 1

    blocks = []
    for i, (kind, m) in enumerate(matches):
        if kind == "boundary":
            continue
        start = m.start()
        end = matches[i + 1][1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        body = PAGE_MARK_RE.sub("", body).strip()

        entry = {
            "kind": kind,
            "type": m.group("type"),
            "page": page_at(start, page_marks),
            "text": body,
        }
        if kind == "numbered":
            num = m.group("num")
            entry["number"] = num
            entry["chapter"] = int(num.split(".")[0])
            # "section" is filled in by core.toc, which knows the outline; the
            # number alone cannot say whether "1.2" means section 2 of chapter 1
            # or item 2 of chapter 1.
            entry["section"] = None
            entry["name"] = m.group("name")
        else:
            entry["number"] = None
            entry["chapter"] = None
            entry["section"] = None
            if m.group("ref"):
                entry["proves"] = f"{m.group('ref')} {m.group('refnum')}"
            else:
                entry["proves"] = "previous block (implicit)"
        blocks.append(entry)

    return blocks, rejected


def attach_proofs(blocks: list[dict]) -> list[dict]:
    last_numbered = None
    for b in blocks:
        if b["kind"] == "numbered":
            b["proof"] = None
            last_numbered = b
        elif b["kind"] == "proof":
            if b.get("proves") == "previous block (implicit)" and last_numbered is not None:
                last_numbered["proof"] = b["text"]
    return [b for b in blocks if b["kind"] == "numbered"]


def run(in_path: Path, out_path: Path, pdf_path: Path) -> None:
    pages, source = load_pages(in_path)
    text = build_joined_text(pages)
    styled_words_per_page = styled_type_words_per_page(pdf_path)
    blocks, rejected = extract_knowledge(text, styled_words_per_page)
    results = attach_proofs(blocks)
    sections = toc.build(pdf_path, results)
    exercises = exercises_core.extract(pages, sections)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"format": FORMAT, "source": source, "sections": sections,
                    "entries": results,
                    "exercises": exercises},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    by_type = {}
    for b in results:
        by_type[b["type"]] = by_type.get(b["type"], 0) + 1
    placed = sum(1 for b in results if b.get("section"))
    print(f"{source}: {len(results)} knowledge entries -> {out_path} "
          f"({rejected} false-positive line-starts rejected; "
          f"{placed}/{len(results)} placed in {len(sections)} sections; "
          f"{len(exercises)} exercises)")
    for t, c in sorted(by_type.items()):
        print(f"   {t}: {c}")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
