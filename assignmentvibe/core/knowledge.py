"""
Step 2: raw text -> structured knowledge base (definitions, theorems, lemmas,
corollaries, examples, remarks, proofs).

The German math scripts used here consistently use amsthm-style numbering
"<chapter>.<section>.<index>" (e.g. "Satz 1.3.4"). We exploit that: chapter
and section are derived directly from the number, no separate heading
detection needed.

A plain line-start regex is NOT enough though: a back-reference like
"Satz 1.3.3" inside a later proof can end up at the start of a line by pure
chance (PDF line wrapping) and would be misdetected as a new block
(observed while testing against VO3_Optimierung.pdf: "Satz 1.3.3" showed up
this way in the middle of a KKT proof in chapter 3 and dragged along a
200-line block of unrelated text). That's why every regex match is verified
against the bold/italic detection from font_styles.py (see there) - only
genuinely styled headers count as a block boundary, everything else stays
part of the surrounding block.

Depends only on core.font_styles (and, transitively, core.pdf_text).
"""

import json
import re
import sys
from pathlib import Path

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
]

# \s* instead of \s+ between type and number: in at least one spot in the
# Algebra script the PDF text is missing the kerning/space
# ("Definition7.4.4" instead of "Definition 7.4.4").
NUMBERED_RE = re.compile(
    r"(?m)^(?P<type>" + "|".join(re.escape(t) for t in NUMBERED_TYPES) + r")"
    r"\s*(?P<num>\d+\.\d+(?:\.\d+)?)\.?"
    r"(?:\s*\((?P<name>[^)]{1,80})\))?"
)

PROOF_RE = re.compile(
    r"(?m)^(?P<type>Beweis)"
    r"(?:\s+(?:von\s+)?(?P<ref>Satz|Lemma|Korollar|Proposition)\s+(?P<refnum>\d+\.\d+(?:\.\d+)?)\.?)?"
    r"\s*\."
)

PAGE_MARK_RE = re.compile(r"\x0cPAGE(\d+)\x0c")

# Every chapter ends with unlabeled sections ("4.4 Aufgaben", "4.3 Literatur
# und Ausblick") containing exercises or bibliography - not a Satz/Definition,
# but also without its own bold header. Without recognizing these as a block
# boundary, the entire rest of the chapter (often several pages of exercises)
# would get appended to the last Satz/Lemma of the chapter as its "text"
# (observed: "Satz 4.2.6" got inflated to over 100 lines this way).
SECTION_BOUNDARY_RE = re.compile(
    r"(?m)^(?:\d+\.\d+\s+(?:Aufgaben|Literatur und Ausblick)"
    r"|Literaturverzeichnis|Übungsaufgaben|Index)\s*$"
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
    (in reading order per page). "Bemerkung/Beispiel" is accepted as its own
    combined type when "Bemerkung" and "Beispiel" appear bold back-to-back."""

    def __init__(self, styled_words_per_page: list[list[str]]):
        self._queues = [list(words) for words in styled_words_per_page]

    def consume(self, page: int, type_: str) -> bool:
        idx = page - 1
        if idx < 0 or idx >= len(self._queues):
            return False
        queue = self._queues[idx]
        if type_ == "Bemerkung/Beispiel":
            if len(queue) >= 2 and queue[0] == "Bemerkung" and queue[1] == "Beispiel":
                del queue[0:2]
                return True
            return False
        if queue and queue[0] == type_:
            queue.pop(0)
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
        if verifier.consume(page, m.group("type")):
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
            parts = num.split(".")
            entry["number"] = num
            entry["chapter"] = int(parts[0])
            entry["section"] = f"{parts[0]}.{parts[1]}" if len(parts) > 1 else None
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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"source": source, "entries": results}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    by_type = {}
    for b in results:
        by_type[b["type"]] = by_type.get(b["type"], 0) + 1
    print(f"{source}: {len(results)} knowledge entries -> {out_path} "
          f"({rejected} false-positive line-starts rejected)")
    for t, c in sorted(by_type.items()):
        print(f"   {t}: {c}")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
