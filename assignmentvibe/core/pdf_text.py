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

# pymupdf is imported where it is used, not here. It costs ~350ms to load,
# and the bar asks for the status every few seconds while none of that path
# opens a PDF - that import was most of what made the tool feel slow.

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


# Maths-heavy PDFs hand back two kinds of character that carry no meaning once
# they leave the document's own font:
#   - Private Use Area codepoints (U+E000-U+F8FF), which the maths font uses for
#     the pieces of a tall bracket around a matrix. Outside that font they are
#     undefined glyphs.
#   - Raw control bytes (NUL, 0x01, 0x10, 0x11 were all seen in one algebra
#     script), which make the extracted text a "binary" file for git/grep and
#     can end up on the clipboard and in a prompt.
# Neither is recoverable into something meaningful, so both are dropped. TAB and
# newline are kept, since the layout does carry information.
JUNK_CHARS_RE = re.compile(r"[\uE000-\uF8FF]|(?![\t\n])[\x00-\x1f\x7f]")

# Old TeX fonts (OT1 encoding) put the ligatures at 0x1B-0x1F, and a PDF made
# with them hands those bytes back as text: "o\x1ben" is "offen". Every PS
# Analysis and PDE sheet is set this way, and without this "offen",
# "Differentialgleichung" and "trifft" come out as "oen", "Dierentialgleichung",
# "tri". The same bytes also turn up as pieces of a tall brace from the maths
# extension font, standing alone on their own line - so only a byte touching
# a letter is read as a ligature, and the rest is junk as before.
OT1_LIGATURES = {"\x1b": "ff", "\x1c": "fi", "\x1d": "fl", "\x1e": "ffi", "\x1f": "ffl"}
OT1_LIGATURE_RE = re.compile(r"(?<=[^\W\d_])[\x1b-\x1f]|[\x1b-\x1f](?=[^\W\d_])")
# The same fonts in T1 encoding put ß at 0xFF, which comes back as "ÿ":
# "heiÿt", "Gauÿ", "Maÿ" - every one of 290 in the PS Analysis and PDE
# material. German maths has no other use for a ÿ.
T1_ESZETT_RE = re.compile(r"(?<=[^\W\d_])ÿ|ÿ(?=[^\W\d_])")


def strip_undisplayable(text: str) -> str:
    return JUNK_CHARS_RE.sub("", text)


def normalize(text: str) -> str:
    text = OT1_LIGATURE_RE.sub(lambda m: OT1_LIGATURES[m.group()], text)
    text = T1_ESZETT_RE.sub("ß", text)
    text = strip_undisplayable(text)
    text = STRAY_SPACE_RE.sub(r"\1", text)
    text = STRAY_DIAERESIS_RE.sub(lambda m: unicodedata.normalize("NFC", m.group(1) + "̈"), text)
    return unicodedata.normalize("NFKC", text)


def extract_pages(pdf_path: Path) -> list[str]:
    import pymupdf

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
