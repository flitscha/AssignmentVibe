"""
Schritt 2: Rohtext -> strukturierte Wissensbasis (Definitionen, Saetze, Lemmata,
Korollare, Beispiele, Bemerkungen, Beweise).

Die deutschen Mathe-Skripten hier verwenden durchgaengig eine amsthm-artige
Nummerierung "<Kapitel>.<Abschnitt>.<Index>" (z.B. "Satz 1.3.4"). Das machen
wir uns zunutze: Kapitel/Abschnitt werden direkt aus der Nummer abgeleitet,
keine separate Ueberschriften-Erkennung noetig.

Ein reiner Zeilenanfang-Regex reicht aber NICHT: Ein Rueckverweis wie
"Satz 1.3.3" in einem spaeteren Beweis kann durch Zeilenumbruch zufaellig am
Zeilenanfang stehen und wuerde faelschlich als neuer Block erkannt (beobachtet
im Test mit VO3_Optimierung.pdf: "Satz 1.3.3" tauchte so mitten in einem
KKT-Beweis auf, Kapitel 3, und riss einen 200-Zeilen-Textblock mit sich).
Deshalb wird jeder Regex-Treffer gegen die Fett-/Kursiv-Erkennung aus
bold_headers.py verifiziert (siehe dort) - nur wirklich ausgezeichnete
Ueberschriften zaehlen als Blockgrenze, alles andere bleibt Teil des
umgebenden Blocks.
"""

import json
import re
import sys
from pathlib import Path

from bold_headers import styled_type_words_per_page

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

# \s* statt \s+ zwischen Typ und Nummer: an mind. einer Stelle im Algebra-Skript
# fehlt das Kerning/Leerzeichen im PDF-Text ("Definition7.4.4" statt
# "Definition 7.4.4").
NUMBERED_RE = re.compile(
    r"(?m)^(?P<type>" + "|".join(re.escape(t) for t in NUMBERED_TYPES) + r")"
    r"\s*(?P<num>\d+\.\d+(?:\.\d+)?)\.?"
    r"(?:\s*\((?P<name>[^)]{1,80})\))?"
)

BEWEIS_RE = re.compile(
    r"(?m)^(?P<type>Beweis)"
    r"(?:\s+(?:von\s+)?(?P<ref>Satz|Lemma|Korollar|Proposition)\s+(?P<refnum>\d+\.\d+(?:\.\d+)?)\.?)?"
    r"\s*\."
)

PAGE_MARK_RE = re.compile(r"\x0cPAGE(\d+)\x0c")

# Am Ende jedes Kapitels stehen unmarkierte Abschnitte ("4.4 Aufgaben",
# "4.3 Literatur und Ausblick") mit Uebungsaufgaben bzw. Quellenangaben - kein
# Satz/keine Definition, aber auch kein eigener fett gesetzter Header. Ohne
# diese als Blockgrenze zu erkennen, wuerde der komplette Rest des Kapitels
# (oft mehrere Seiten Uebungsaufgaben) dem letzten Satz/Lemma des Kapitels
# als "Text" angehaengt werden (beobachtet: "Satz 4.2.6" wurde so auf ueber
# 100 Zeilen aufgeblaeht).
SECTION_BOUNDARY_RE = re.compile(
    r"(?m)^(?:\d+\.\d+\s+(?:Aufgaben|Literatur und Ausblick)"
    r"|Literaturverzeichnis|Übungsaufgaben|Index)\s*$"
)


def load_pages(path: Path) -> list[str]:
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
    """Verifiziert Regex-Treffer gegen die per Font-Stil erkannten echten
    Ueberschriften (in Lesereihenfolge je Seite). "Bemerkung/Beispiel" wird
    dabei als eigener kombinierter Typ akzeptiert, wenn direkt hintereinander
    "Bemerkung" und "Beispiel" fett vorkommen."""

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


def extract_knowledge(text: str, styled_words_per_page: list[list[str]]) -> list[dict]:
    page_marks = [(m.start(), int(m.group(1))) for m in PAGE_MARK_RE.finditer(text)]
    verifier = HeaderVerifier(styled_words_per_page)

    raw_matches = []
    for m in NUMBERED_RE.finditer(text):
        raw_matches.append(("numbered", m))
    for m in BEWEIS_RE.finditer(text):
        raw_matches.append(("beweis", m))
    for m in SECTION_BOUNDARY_RE.finditer(text):
        raw_matches.append(("boundary", m))
    raw_matches.sort(key=lambda t: t[1].start())

    # matches enthaelt auch "boundary"-Eintraege: die zaehlen nicht als
    # eigener Wissensblock, begrenzen aber den davorliegenden Block.
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
                entry["proves"] = "vorheriger Block (implizit)"
        blocks.append(entry)

    return blocks, rejected


def attach_proofs(blocks: list[dict]) -> list[dict]:
    last_numbered = None
    for b in blocks:
        if b["kind"] == "numbered":
            b["proof"] = None
            last_numbered = b
        elif b["kind"] == "beweis":
            if b.get("proves") == "vorheriger Block (implizit)" and last_numbered is not None:
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
    print(f"{source}: {len(results)} Wissenseinheiten -> {out_path} "
          f"({rejected} False-Positive-Zeilenanfaenge verworfen)")
    for t, c in sorted(by_type.items()):
        print(f"   {t}: {c}")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
