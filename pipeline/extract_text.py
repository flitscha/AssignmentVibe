"""
Schritt 1: PDF -> Rohtext.

Nutzt PyMuPDF im einfachen "text"-Modus. Getestet gegen pdftotext (poppler) und
pymupdf4llm (Markdown-Modus) auf den Beispiel-Skripten (Algebra.pdf, VO3_Optimierung.pdf):

- pdftotext -layout: verstuemmelt Satz-/Definitionsnummern bei diesen PDFs
  (z.B. "Deﬁnition . . ." statt "Definition 2.1.1.") -> unbrauchbar fuer die
  Knowledge-Extraction.
- pymupdf4llm (Markdown): erhaelt Nummern & Fett-/Kursiv-Struktur sehr gut,
  verschluckt aber ganze Formelzeilen (Center-aligned Formeln werden beim
  Markdown-Rebuild oft weggelassen).
- PyMuPDF "text"-Modus (dieses Skript): erhaelt Nummern UND Formeln (als
  Unicode-Mathe, nicht LaTeX) verlustfrei genug fuer LLM-Kontext. -> gewaehlt.

Fuer eingescannte/handschriftliche PDFs (spaeter) reicht das nicht - dafuer
braucht es OCR (siehe docs/POC_REPORT.md).
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

# Manche PDF-Fonts kodieren Ligaturen (fi, fl, ffi, ...) als je EIN Unicode-
# Codepoint statt als zwei Buchstaben. NFKC zerlegt diese ligature-Codepoints
# (kompatibel-aequivalent) wieder in "fi", "fl" etc. - sonst matcht z.B. der
# Regex fuer "Definition" nicht mehr, weil dort ein einzelnes "ﬁ" steht.
#
# Manche Fonts (z.B. im Optimierung-Skript) zeichnen Umlaute als freistehendes
# Trema-Glyph VOR dem Buchstaben statt als vorkomponiertes ü/ö/ä, z.B. wird aus
# "Lösungsmenge" beim Textextrahieren "L¨osungsmenge" (L, U+00A8 oder U+0308,
# o, ...), manchmal noch mit einem Leerzeichen davor ("F ̈ur" statt "Für").
# Wir entfernen das Leerzeichen vor dem Trema und komponieren Trema+Buchstabe
# per NFC zu einem echten ü/ö/ä.
STRAY_SPACE_RE = re.compile(r" ([̈¨])(?=\w)")
STRAY_DIAERESIS_RE = re.compile(r"[̈¨](\w)")


def normalize(text: str) -> str:
    text = STRAY_SPACE_RE.sub(r"\1", text)
    text = STRAY_DIAERESIS_RE.sub(lambda m: unicodedata.normalize("NFC", m.group(1) + "̈"), text)
    return unicodedata.normalize("NFKC", text)


def extract_pages(pdf_path: Path) -> list[str]:
    doc = pymupdf.open(pdf_path)
    return [normalize(page.get_text("text")) for page in doc]


def extract_to_json(pdf_path: Path, out_path: Path) -> None:
    pages = extract_pages(pdf_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"source": pdf_path.name, "pages": pages}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"{pdf_path.name}: {len(pages)} Seiten -> {out_path}")


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    extract_to_json(src, dst)
