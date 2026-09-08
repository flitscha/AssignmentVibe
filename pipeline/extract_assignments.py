"""
Schritt 3: Aufgabenblatt (PDF) -> strukturierte Aufgabenliste.

Getestet gegen zwei sehr unterschiedliche Blatt-Formate:
- Algebra ("A01.pdf" .. "A14.pdf"): "Aufgabe N" auf eigener Zeile, Text folgt.
- PS Optimierung ("01-Blatt-PS-Optimierung.pdf" .. "12-..."): "Aufgabe N: Titel."
  auf einer Zeile, oft mit Unterpunkten a)/b)/c) und mit Verweisen auf
  Aufgaben, die im Skriptum selbst stehen ("vom Skriptum").

Beide Formate lassen sich mit derselben Regex-Familie parsen, weil "Aufgabe N"
(mit optionalem Doppelpunkt+Titel) in beiden immer der Block-Trenner ist.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_text import normalize  # noqa: E402

import pymupdf

AUFGABE_RE = re.compile(r"(?m)^Aufgabe\s+(?P<num>\d+)\s*:?\s*")
SUBPART_RE = re.compile(r"(?m)^\s*\(?(?P<label>[a-h]|i{1,3}v?|vi{0,3})\)\s")
BESPRECHUNG_RE = re.compile(r"Besprechung(?:stermin)?(?:\s+am)?:?\s*(?P<date>[^\n)]+)")
SKRIPT_REF_RE = re.compile(r"(?:Aufgabe|Programmieraufgabe)\s*\((?P<ref>\d+\.\d+)\)\s*vom\s*Skriptum")
BLATT_NUM_RE = re.compile(r"Blatt\s+(?P<num>\d+)")


def extract_pdf_text(pdf_path: Path) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n".join(normalize(p.get_text("text")) for p in doc)


TITLE_END_RE = re.compile(r"[.:]\s")


def guess_title(body: str) -> str | None:
    """Kurztitel = erster Satz des Bodys, falls kurz genug (sonst None)."""
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
    text = extract_pdf_text(pdf_path)

    besprechung = BESPRECHUNG_RE.search(text)
    blatt_num = BLATT_NUM_RE.search(text)

    matches = list(AUFGABE_RE.finditer(text))
    aufgaben = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        skript_refs = [rm.group("ref") for rm in SKRIPT_REF_RE.finditer(body)]
        aufgaben.append({
            "number": int(m.group("num")),
            "title": guess_title(body),
            "text": body,
            "subparts": split_subparts(body),
            "references_skript": skript_refs or None,
        })

    return {
        "source": pdf_path.name,
        "blatt_nummer": int(blatt_num.group("num")) if blatt_num else None,
        "besprechungstermin": besprechung.group("date").strip() if besprechung else None,
        "num_aufgaben": len(aufgaben),
        "aufgaben": aufgaben,
    }


def run(in_path: Path, out_path: Path) -> None:
    result = parse_assignment_sheet(in_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{in_path.name}: {result['num_aufgaben']} Aufgaben -> {out_path}")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
