"""
Fuehrt die komplette POC-Pipeline auf example_files/ aus:

  example_files/*.pdf
      -> data/_raw_text/<name>.json        (Schritt 1: extract_text)
      -> data/knowledge/<name>.json        (Schritt 2: extract_knowledge, nur Skripte)
      -> data/assignments/<name>.json      (Schritt 3: extract_assignments, nur Blaetter)

Skripte vs. Aufgabenblaetter werden ueber SCRIPTS/ASSIGNMENT_GLOBS unten
zugeordnet - fuer echte Nutzung wuerde das aus der Ordnerstruktur (siehe
Projektvision: "Download-organize") kommen statt hartcodiert zu sein.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import extract_assignments
import extract_knowledge
import extract_text

ROOT = Path(__file__).parent.parent
EXAMPLE_DIR = ROOT / "example_files"

SCRIPTS = {
    "Algebra.pdf": "algebra",
    "VO3_Optimierung.pdf": "optimierung",
}

ASSIGNMENT_PATTERNS = ["A??.pdf", "??-Blatt-PS-Optimierung.pdf"]


def main() -> None:
    for pdf_name, out_name in SCRIPTS.items():
        pdf_path = EXAMPLE_DIR / pdf_name
        raw_path = ROOT / "data" / "_raw_text" / f"{out_name}.json"
        knowledge_path = ROOT / "data" / "knowledge" / f"{out_name}.json"
        extract_text.extract_to_json(pdf_path, raw_path)
        extract_knowledge.run(raw_path, knowledge_path, pdf_path)

    print()
    for pattern in ASSIGNMENT_PATTERNS:
        for pdf_path in sorted(EXAMPLE_DIR.glob(pattern)):
            out_path = ROOT / "data" / "assignments" / f"{pdf_path.stem}.json"
            extract_assignments.run(pdf_path, out_path)


if __name__ == "__main__":
    main()
