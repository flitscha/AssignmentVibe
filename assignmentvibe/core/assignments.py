"""
Step 3: assignment sheet (PDF) -> structured task list.

Tested against two very different sheet formats:
- Algebra ("A01.pdf" .. "A14.pdf"): "Aufgabe N" on its own line, text follows.
- PS Optimierung ("01-Blatt-PS-Optimierung.pdf" .. "12-..."): "Aufgabe N: Titel."
  on one line, often with sub-parts a)/b)/c) and references to tasks that
  live inside the script itself ("vom Skriptum").

Both formats can be parsed with the same regex family, because "Aufgabe N"
(with an optional colon+title) is always the block separator in either case.

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

TASK_RE = re.compile(r"(?m)^Aufgabe\s+(?P<num>\d+)\s*:?\s*")
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
FORMAT = 2

SHEET_NUM_RE = re.compile(r"Blatt\s+(?P<num>\d+)")
TITLE_END_RE = re.compile(r"[.:]\s")


def extract_pdf_text(pdf_path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    return "\n".join(normalize(p.get_text("text")) for p in doc)


def guess_title(body: str) -> str | None:
    """Short title = first sentence of the body, if short enough (else None)."""
    m = TITLE_END_RE.search(body)
    if not m or m.start() > 80:
        return None
    return body[:m.start()].strip() or None


def split_subparts(body: str) -> list[dict]:
    matches = list(SUBPART_RE.finditer(body))
    if len(matches) < 2:
        return []
    parts = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        parts.append({"label": m.group("label"), "text": body[m.end():end].strip()})
    return parts


def parse_assignment_sheet(pdf_path: Path) -> dict:
    text = PAGE_FOOTER_RE.sub("", extract_pdf_text(pdf_path))

    discussion_date = DISCUSSION_DATE_RE.search(text)
    sheet_num = SHEET_NUM_RE.search(text)

    matches = list(TASK_RE.finditer(text))
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
        "sheet_number": int(sheet_num.group("num")) if sheet_num else None,
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
