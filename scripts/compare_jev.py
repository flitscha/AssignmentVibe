"""
Dev helper: does Jev pick better sections than the keyword ranking?

The script's own exercises are the test set - each one sits at the end of the
chapter it practises, so its chapter is a known right answer. Every exercise's
text is ranked against the WHOLE script (no `within`: that restriction exists
exactly because the chapter is already known, and would make the test trivial),
once by keyword, once by Jev, and the suggestion counts as right when its top
section lies in the exercise's chapter.

    python scripts/compare_jev.py                 # data/knowledge/optimierung.json
    python scripts/compare_jev.py algebra --limit 10
    python scripts/compare_jev.py --dry-run       # sizes only, no API call

Needs an OpenRouter key (see integrations/jev.py) unless --dry-run.
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assignmentvibe.core import selection  # noqa: E402
from assignmentvibe.integrations import jev  # noqa: E402


def chapter(key: str) -> str:
    return key.split(".")[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("course", nargs="?", default="optimierung")
    p.add_argument("--limit", type=int, default=0, help="only the first N exercises")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    data = json.loads((REPO_ROOT / "data" / "knowledge" / f"{args.course}.json")
                      .read_text(encoding="utf-8"))
    entries, exercises = data["entries"], data.get("exercises") or []
    titles = {n["key"]: n["title"] for n in data.get("sections") or []
              if n.get("key") and n.get("title")}
    exercises = [e for e in exercises if e.get("section")]
    if args.limit:
        exercises = exercises[:args.limit]

    digests = selection.section_digests(entries, titles, budget=jev.MAX_STATE_CHARS)
    size = sum(len(d) for d in digests.values())
    print(f"{args.course}: {len(exercises)} exercises, {len(digests)} sections, "
          f"{size} characters of state per call")
    if args.dry_run:
        return
    if not jev.configured():
        sys.exit("No OpenRouter key - see integrations/jev.py.")

    hits = {"keyword": 0, "jev": 0}
    cost, seconds = 0.0, []
    for ex in exercises:
        text = f"{ex.get('title') or ''}\n{ex['text']}"
        want = chapter(ex["section"])

        by_keyword = selection.suggest_sections(text, entries)
        start = time.monotonic()
        relevance, call_cost = jev.rank(text, digests)
        seconds.append(time.monotonic() - start)
        cost += call_cost or 0.0
        by_jev = selection.suggest_from_relevance(relevance)

        row = []
        for name, picked in (("keyword", by_keyword), ("jev", by_jev)):
            ok = bool(picked) and chapter(picked[0]) == want
            hits[name] += ok
            row.append(f"{'✓' if ok else '✗'} {name} {','.join(picked) or '-'}")
        print(f"({ex['number']:>5}) ch.{want:<3} " + "   ".join(row))

    n = len(exercises) or 1
    seconds.sort()
    print(f"\nright chapter: keyword {hits['keyword']}/{n}, jev {hits['jev']}/{n}")
    print(f"jev: median {seconds[len(seconds) // 2]:.2f}s, max {seconds[-1]:.2f}s, "
          f"total ${cost:.4f}")


if __name__ == "__main__":
    main()
