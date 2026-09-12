"""
Detects "real" Satz/Definition/.../Beweis headers by font styling, instead of
just guessing from line starts.

Why this is necessary: a naive line-start regex on plain text produces false
positives as soon as a back-reference like "Satz 1.3.3" (e.g. cited in a
later proof) happens to land at the start of a line because of PDF line
wrapping. In the original PDF, real headers are ALWAYS specially styled
(bold or italic, depending on the theorem package), while references in
running text are always in the regular font. Tested against two scripts with
completely different font setups:

  - VO3_Optimierung.pdf (Computer Modern): "Definition/Satz/Lemma/Korollar"
    bold (CMBX10), "Bemerkung/Beispiel/Algorithmus/Beweis" italic (CMTI10);
    each word is its own text span.
  - Algebra.pdf (Alegreya): "Bemerkung/Lemma" (and presumably others) bold,
    but type+number sit in ONE span ("Lemma 2.1.5.").

Hence: (a) matching is done via a prefix match on the span text (not
equality), and (b) any kind of styling (bold OR italic) counts as a signal -
which of the two a given theorem package uses is beside the point; what
matters is that it stands out from the regular running text.

Note: TYPE_WORDS below are literal German words (Definition, Satz, Lemma,
...) because the source PDFs are German-language math scripts - this is
domain data being matched, not something to translate.

Depends only on core.pdf_text (for text normalization) and pymupdf.
"""

import re
from pathlib import Path

import pymupdf

from .pdf_text import normalize

TYPE_WORDS = [
    "Definition", "Satz", "Lemma", "Korollar", "Proposition",
    "Bemerkung", "Beispiel", "Algorithmus", "Beweis", "Konstruktion",
]

# Usually there is a space between the type word and the number ("Definition
# 7.1.1"), but in at least one section of Algebra.pdf the PDF is missing that
# kerning/space ("Definition7.4.4" as ONE word/span) - hence a lookahead
# instead of \b, which also allows immediately-following digits.
TYPE_PREFIX_RE = re.compile(r"^(" + "|".join(TYPE_WORDS) + r")(?=[\s\d.]|$)")

BOLD_FLAG = 2 ** 4
ITALIC_FLAG = 2 ** 1


def is_styled(span: dict) -> bool:
    font = span.get("font", "")
    bold = bool(span["flags"] & BOLD_FLAG) or "Bold" in font or "-BX" in font or font.endswith("BX10")
    italic = bool(span["flags"] & ITALIC_FLAG) or "Italic" in font or "-TI" in font or font.endswith("TI10")
    return bold or italic


def styled_type_words_per_page(pdf_path: Path) -> list[list[str]]:
    """Per page: list of styled (bold/italic) type words in reading order."""
    doc = pymupdf.open(pdf_path)
    result = []
    for page in doc:
        words_on_page = []
        d = page.get_text("dict")
        for block in d["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = normalize(span["text"]).strip()
                    m = TYPE_PREFIX_RE.match(text)
                    if m and is_styled(span):
                        words_on_page.append(m.group(1))
        result.append(words_on_page)
    return result
