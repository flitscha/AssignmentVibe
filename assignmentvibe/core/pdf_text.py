"""
Step 1: PDF -> raw text.

Uses PyMuPDF's plain "text" mode. Benchmarked against pdftotext (poppler) and
pymupdf4llm (Markdown mode) on the example scripts (Algebra.pdf,
VO3_Optimierung.pdf):

- pdftotext -layout: mangles theorem/definition numbers on these PDFs
  (e.g. "Deﬁnition . . ." instead of "Definition 2.1.1.") -> unusable for
  knowledge extraction.
- pymupdf4llm (Markdown): keeps numbers & bold/italic structure very well,
  but swallows entire formula lines (center-aligned formulas are often
  dropped during the Markdown rebuild).
- PyMuPDF "text" mode (this module): keeps numbers AND formulas (as Unicode
  math, not LaTeX) with enough fidelity for LLM context. -> chosen.

Not sufficient for scanned/handwritten PDFs (future work) - that needs OCR
(see docs/POC_REPORT.md).

No dependency on any other module in this project - this is the lowest-level
building block of the core pipeline (core/font_styles.py imports `normalize`
from here, everything else builds on top of that).
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

# Some PDF fonts encode ligatures (fi, fl, ffi, ...) as a single Unicode
# codepoint instead of two letters. NFKC decomposes these ligature codepoints
# (compatibility-equivalent) back into "fi", "fl" etc. - otherwise e.g. the
# regex for "Definition" no longer matches, because the source text contains
# a single "ﬁ" glyph.
#
# Some fonts (e.g. in the Optimierung script) draw umlauts as a free-standing
# diaeresis glyph BEFORE the base letter instead of a precomposed ü/ö/ä, so
# text extraction turns "Lösungsmenge" into "L¨osungsmenge" (L, U+00A8 or
# U+0308, o, ...), sometimes with a stray space in front ("F ̈ur" instead of
# "Für"). We strip the space before the diaeresis and recompose
# diaeresis+letter into a real ü/ö/ä via NFC.
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
    print(f"{pdf_path.name}: {len(pages)} pages -> {out_path}")


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    extract_to_json(src, dst)
