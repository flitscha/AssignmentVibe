"""
Dev helper: does Jev pick sensible statements for a task?

The script's own exercises are the test set - each one sits at the end of the
chapter it practises, so most of what it needs should come from that chapter.
For every exercise, Jev judges every statement and proof of the whole script;
the report shows how many it picked and how many of those lie in the
exercise's own chapter. Not a ground truth (a chapter-4 exercise may well need a
chapter-1 definition), but a pick that is mostly elsewhere, or empty, or thirty
statements long, is visibly off.

    python scripts/compare_jev.py                 # data/knowledge/optimierung.json
    python scripts/compare_jev.py algebra --limit 10
    python scripts/compare_jev.py --dry-run       # batch sizes only, no API call

Needs an OpenRouter key (see integrations/jev.py) unless --dry-run. Every call
is counted in the same usage totals the hub shows.
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assignmentvibe.core import selection  # noqa: E402
from assignmentvibe.core.prompts import entry_id  # noqa: E402
from assignmentvibe.integrations import jev  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("course", nargs="?", default="optimierung")
    p.add_argument("--limit", type=int, default=0, help="only the first N exercises")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    data = json.loads((REPO_ROOT / "data" / "knowledge" / f"{args.course}.json")
                      .read_text(encoding="utf-8"))
    entries = data["entries"]
    exercises = [e for e in data.get("exercises") or [] if e.get("section")]
    if args.limit:
        exercises = exercises[:args.limit]

    items = selection.judgement_items(entries)
    sections = {entry_id(e): selection.section_of(e) or ""
                for e in selection.statements(entries)}
    batches = jev._batches("x" * 1500, items)
    print(f"{args.course}: {len(exercises)} exercises, {len(items)} statements, "
          f"{sum(1 for i in items.values() if 'proof' in i)} proofs -> "
          f"{len(batches)} requests per pick")
    if args.dry_run:
        return
    if not jev.configured():
        sys.exit("No OpenRouter key - see integrations/jev.py.")

    before = jev.usage()
    seconds, sizes, in_chapter = [], [], []
    for ex in exercises:
        text = f"{ex.get('title') or ''}\n{ex['text']}"
        chapter = ex["section"].split(".")[0]
        start = time.monotonic()
        statement_p, proof_p = jev.judge(text, items)
        seconds.append(time.monotonic() - start)
        picked, proofs = selection.pick_from_judgement(statement_p, proof_p)

        own = [i for i in picked if sections.get(i, "").split(".")[0] == chapter]
        sizes.append(len(picked))
        in_chapter.append(len(own) / len(picked) if picked else 0.0)
        shown = ", ".join(picked[:6]) + (" …" if len(picked) > 6 else "")
        print(f"({ex['number']:>5}) ch.{chapter:<3} {len(picked):>2} picked, "
              f"{len(own):>2} in ch., {len(proofs)} proofs   {shown}")

    after = jev.usage()
    n = len(exercises) or 1
    seconds.sort()
    print(f"\nper exercise: {sum(sizes) / n:.1f} statements, "
          f"{100 * sum(in_chapter) / n:.0f}% from its own chapter, "
          f"{sizes.count(0)} empty picks")
    print(f"per pick: median {seconds[len(seconds) // 2]:.2f}s, max {seconds[-1]:.2f}s")
    print(f"this run: {after['requests'] - before['requests']} requests, "
          f"{after['input_tokens'] - before['input_tokens']} tokens, "
          f"${after['cost_usd'] - before['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
