"""
Run the ingest over every PDF in corpus/ and print what came out.

The point is the spread, not any one script: the corpus deliberately mixes
German and English, two-part and three-part numbering, outlines four levels
deep, outlines whose level 1 holds parts rather than chapters, and one script
with no outline at all. A change to the chunking is only believable if this
table stays healthy across all of them.

What to look at:
  sections  how many sections the script chunks into. Roughly one per 5-25
            statements is a usable picker; one per 1-2 means the numbering was
            misread and the chunking has collapsed.
  placed    entries that landed in a section. Anything below 100% means the
            outline and the pages disagree somewhere.
  leaks     statements whose text still contains a proof. Must be 0 - a leak
            is a proof reaching a hint prompt.

    python scripts/check_corpus.py [name-fragment ...]
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assignmentvibe.core import knowledge, pdf_text, selection  # noqa: E402

# Leaks that cannot be fixed, so that a real regression still stands out.
# Stochastik writes two of its proofs as a plain "Beweis:" in the regular weight
# - no bold, no italic, no small caps, no reference to what is being proved.
# Nothing distinguishes them from running text, and both are throwaways
# ("siehe Analysis.", "Bachelorarbeit!!!") with nothing to give away.
KNOWN_LEAKS = {"Stochastik": 2}

CORPUS = REPO_ROOT / "corpus"
CACHE = REPO_ROOT / "data" / "_corpus"
# A leaked proof, not merely the word: a line that opens a proof block. Running
# text that happens to wrap onto a line starting "Beweis mit geringfuegigen
# Anpassungen..." is prose, and counting it made the number look worse than it is.
PROOF_START_RE = re.compile(
    r"(?m)^(?:Beweis|Proof)(?:\s+(?:von|of)\s+\w+\s+[\d.]+)?\s*[.:]")


def ingest(pdf: Path) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    raw = CACHE / f"{pdf.stem}.raw.json"
    out = CACHE / f"{pdf.stem}.json"
    if not raw.exists():
        pdf_text.extract_to_json(pdf, raw)
    knowledge.run(raw, out, pdf)
    return json.loads(out.read_text(encoding="utf-8"))


def main() -> None:
    wanted = [a.lower() for a in sys.argv[1:]]
    pdfs = sorted(p for p in CORPUS.glob("*.pdf")
                  if not wanted or any(w in p.name.lower() for w in wanted))
    if not pdfs:
        print(f"No PDFs in {CORPUS}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for pdf in pdfs:
        data = ingest(pdf)
        entries, sections = data["entries"], data["sections"]
        stmts = selection.statements(entries)
        placed = sum(1 for e in entries if e.get("section"))
        leaks = sum(1 for e in stmts if PROOF_START_RE.search(e["text"]))
        per = selection.group_by_section(entries)
        sizes = sorted((len(v) for v in per.values()), reverse=True)
        rows.append({
            "name": pdf.stem[:34],
            "entries": len(entries),
            "stmts": len(stmts),
            "sections": len(sections),
            "used": len(per),
            "placed": placed,
            "leaks": leaks,
            "proofs": sum(1 for e in entries if e.get("proof")),
            "biggest": sizes[0] if sizes else 0,
            "types": Counter(e["type"] for e in stmts),
        })

    print()
    head = (f"{'script':34s} {'entries':>7s} {'stmts':>6s} {'sections':>8s} "
            f"{'used':>5s} {'placed':>7s} {'proofs':>7s} {'biggest':>8s} {'leaks':>6s}")
    print(head)
    print("-" * len(head))
    for r in rows:
        pct = 100 * r["placed"] // max(1, r["entries"])
        flag = "" if r["leaks"] == 0 else "  <-- LEAK"
        print(f"{r['name']:34s} {r['entries']:7d} {r['stmts']:6d} {r['sections']:8d} "
              f"{r['used']:5d} {str(pct) + '%':>7s} {r['proofs']:7d} {r['biggest']:8d} "
              f"{r['leaks']:6d}{flag}")

    print("\nStatement types per script:")
    for r in rows:
        print(f"  {r['name']:34s} {', '.join(f'{t} {c}' for t, c in r['types'].most_common())}")

    total_leaks = sum(r["leaks"] for r in rows)
    print(f"\n{len(rows)} scripts, {sum(r['entries'] for r in rows)} entries, "
          f"{total_leaks} leaked proofs.")

    over = [(r["name"], r["leaks"], KNOWN_LEAKS.get(r["name"], 0))
            for r in rows if r["leaks"] > KNOWN_LEAKS.get(r["name"], 0)]
    if over:
        for name, got, expected in over:
            print(f"  REGRESSION {name}: {got} leaks, expected at most {expected}")
    else:
        print("No regression against the known edge cases.")
    sys.exit(1 if over else 0)


if __name__ == "__main__":
    main()
