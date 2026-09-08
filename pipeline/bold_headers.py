"""
Erkennt "echte" Satz/Definition/.../Beweis-Ueberschriften anhand der
Schriftauszeichnung, statt nur am Zeilenanfang zu raten.

Warum das noetig ist: Ein simpler Zeilenanfang-Regex auf reinem Text erzeugt
False Positives, sobald ein Rueckverweis wie "Satz 1.3.3" (z.B. in einem
spaeteren Beweis zitiert) durch PDF-Zeilenumbruch zufaellig an einem
Zeilenanfang landet. Im Original-PDF sind echte Ueberschriften aber IMMER
speziell ausgezeichnet (fett oder kursiv, je nach Theorem-Package), Zitate im
Fliesstext dagegen immer in der regulaeren Schrift. Getestet an zwei Skripten
mit komplett unterschiedlichen Font-Setups:

  - VO3_Optimierung.pdf (Computer Modern): "Definition/Satz/Lemma/Korollar"
    fett (CMBX10), "Bemerkung/Beispiel/Algorithmus/Beweis" kursiv (CMTI10);
    jedes Wort ist ein eigener Text-Span.
  - Algebra.pdf (Alegreya): "Bemerkung/Lemma" (und vermutlich weitere) fett
    gesetzt, aber Typ+Nummer stehen in EINEM Span ("Lemma 2.1.5.").

Deshalb: (a) es wird per Praefix-Match auf den Span-Text geprueft (nicht auf
Gleichheit), und (b) es zaehlt jede Auszeichnung (fett ODER kursiv) als
Signal - welche der beiden ein Theorem-Package benutzt, ist Nebensache;
entscheidend ist nur, dass es sich vom regulaeren Fliesstext abhebt.
"""

import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))
from extract_text import normalize  # noqa: E402

TYPE_WORDS = [
    "Definition", "Satz", "Lemma", "Korollar", "Proposition",
    "Bemerkung", "Beispiel", "Algorithmus", "Beweis", "Konstruktion",
]

# Normalerweise steht zwischen Typwort und Nummer ein Leerzeichen ("Definition
# 7.1.1"), aber in mind. einem Abschnitt von Algebra.pdf fehlt das Kerning
# dafuer im PDF ("Definition7.4.4" als EIN Wort/Span) - daher hier ein
# Lookahead statt \b, der auch direkt folgende Ziffern zulaesst.
TYPE_PREFIX_RE = re.compile(r"^(" + "|".join(TYPE_WORDS) + r")(?=[\s\d.]|$)")

BOLD_FLAG = 2 ** 4
ITALIC_FLAG = 2 ** 1


def is_styled(span: dict) -> bool:
    font = span.get("font", "")
    bold = bool(span["flags"] & BOLD_FLAG) or "Bold" in font or "-BX" in font or font.endswith("BX10")
    italic = bool(span["flags"] & ITALIC_FLAG) or "Italic" in font or "-TI" in font or font.endswith("TI10")
    return bold or italic


def styled_type_words_per_page(pdf_path: Path) -> list[list[str]]:
    """Je Seite: Liste der ausgezeichneten (fett/kursiv) Type-Woerter in Lesereihenfolge."""
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
