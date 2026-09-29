"""
Dev helper (not part of the installed package): re-run the whole core
pipeline over example_files/ and regenerate data/ - both local only, not in
the repository (course material is copyrighted: put your own PDFs there). Used to
regression-test the extraction logic against known-good output counts
(see docs/POC_REPORT.md) after changing anything under assignmentvibe/core/.

  example_files/*.pdf
      -> data/_raw_text/<name>.json        (step 1: core.pdf_text)
      -> data/knowledge/<name>.json        (step 2: core.knowledge, scripts only)
      -> data/assignments/<name>.json      (step 3: core.assignments, sheets only)

Scripts vs. assignment sheets are mapped via SCRIPTS/ASSIGNMENT_PATTERNS
below - for real use, that comes from the organizer (assignmentvibe/organizer/)
instead of being hardcoded here.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assignmentvibe.core import assignments, knowledge, pdf_text  # noqa: E402

EXAMPLE_DIR = REPO_ROOT / "example_files"

SCRIPTS = {
    "Algebra.pdf": "algebra",
    "VO3_Optimierung.pdf": "optimierung",
}

ASSIGNMENT_PATTERNS = ["A??.pdf", "??-Blatt-PS-Optimierung.pdf"]


def main() -> None:
    for pdf_name, out_name in SCRIPTS.items():
        pdf_path = EXAMPLE_DIR / pdf_name
        raw_path = REPO_ROOT / "data" / "_raw_text" / f"{out_name}.json"
        knowledge_path = REPO_ROOT / "data" / "knowledge" / f"{out_name}.json"
        pdf_text.extract_to_json(pdf_path, raw_path)
        knowledge.run(raw_path, knowledge_path, pdf_path)

    print()
    for pattern in ASSIGNMENT_PATTERNS:
        for pdf_path in sorted(EXAMPLE_DIR.glob(pattern)):
            out_path = REPO_ROOT / "data" / "assignments" / f"{pdf_path.stem}.json"
            assignments.run(pdf_path, out_path)


if __name__ == "__main__":
    main()
