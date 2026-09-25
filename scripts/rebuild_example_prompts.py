"""
Dev helper (not part of the installed package): regenerate the sample prompts in
docs/example_prompts/ from the committed data/ produced by
rebuild_example_data.py.

These files are documentation of what a finished prompt looks like. They were
hand-saved once, which meant they silently went stale as soon as prompt building
or knowledge retrieval changed - and a stale example is worse than none, because
it documents behaviour the code no longer has. Regenerating them is one command:

    python scripts/rebuild_example_data.py     # PDFs  -> data/
    python scripts/rebuild_example_prompts.py  # data/ -> docs/example_prompts/
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assignmentvibe.core.prompts import build_prompt  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "example_prompts"

# A partial solution with a deliberate mistake, so one example shows what a
# prompt looks like when there is already work to build on: the CRT step
# combining x=1 mod 3 and x=3 mod 4 gives x=7 mod 12, not x=9 mod 12.
FAULTY_SOLUTION = (
    "x=1 mod 3 und x=3 mod 4 ergibt zusammen x=9 mod 12 (CRT fuer 3 und 4, da "
    "teilerfremd). Jetzt noch x=2 mod 7 kombinieren: ich setze x=9+12k und loese "
    "9+12k=2 mod 7, also 12k=-7=0 mod 7, also k=0 mod 7 (da 12=5 mod 7 und 5 "
    "invertierbar). Also x=9 mod 84 als einzige Loesung."
)

EXAMPLES = [
    # (output name, sheet id, task number, course name, chapters, partial
    #  solution, single proofs)
    ("algebra_no_selection", "A02", 4, "Algebra I", None, None, None),
    ("algebra_with_partial_solution", "A07", 1, "Algebra I", None, FAULTY_SOLUTION,
     None),
    ("optimierung_chapter_chosen", "07-Blatt-PS-Optimierung", 3,
     "PS Optimierung", ["3"], None, None),
    # A task that is only a pointer into the script ("Lösen Sie Aufgabe (1.11)
    # vom Skriptum"), with one proof picked out of the chapter.
    ("optimierung_script_exercise", "03-Blatt-PS-Optimierung", 1,
     "PS Optimierung", ["1.1"], None, ["Satz 1.1.13"]),
]

KNOWLEDGE_FOR_SHEET = {"A": "algebra", "0": "optimierung", "1": "optimierung"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, sheet_id, task_number, course, sections, solution, proof_of in EXAMPLES:
        sheet = _load(REPO_ROOT / "data" / "assignments" / f"{sheet_id}.json")
        task = next(t for t in sheet["tasks"] if t["number"] == task_number)
        knowledge_name = KNOWLEDGE_FOR_SHEET[sheet_id[0]]
        knowledge = _load(REPO_ROOT / "data" / "knowledge" / f"{knowledge_name}.json")
        entries = knowledge["entries"]
        titles = {n["key"]: n["title"] for n in knowledge.get("sections", [])
                  if n.get("title")}

        prompt = build_prompt(task, sheet, entries, solution, course,
                              sections=sections, section_titles=titles,
                              exercises=knowledge.get("exercises"), proof_of=proof_of)
        out_path = OUT_DIR / f"{name}.txt"
        out_path.write_text(prompt + "\n", encoding="utf-8")
        print(f"{out_path.relative_to(REPO_ROOT)}  ({len(prompt)} characters)")


if __name__ == "__main__":
    main()
