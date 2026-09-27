"""
Decide which knowledge entries go into a prompt.

Two ways in, and the choice matters more than it looks:

1. BY SECTION (the good one). The user says which part of the script the course
   is currently in, and every statement from those sections goes in. The user
   knows this; the tool cannot infer it. It is also cheap - section 3.1 of the
   Optimierung script is 11 entries / ~2.3k characters, less than the three
   keyword-picked entries it replaces.

2. BY KEYWORD (the fallback), for when no section was chosen. Ranking whole
   sections rather than single entries, then taking those sections in full: a
   near-miss then costs you a neighbouring section, not the one definition the
   task is actually about. That failure was the reason for this module -
   "Definition 3.1.8 (Subdifferential)" ranked 4th on a task about the
   subdifferential and fell outside top_k=3.

Sections are keyed by their path in the script's outline ("3", "3.1", "3.1.2"),
so selecting a parent selects everything below it - see core.toc for where those
keys come from. That prefix relationship is the whole reason the picker can
offer "all of chapter 3" as one row.

Only statements are included: definitions and the theorem family, in German or
English. Remarks, examples and the prose between them are left out - they are
bulk without being what a task needs to cite. Algorithms and proofs are opt-in
and off by default: proofs because they hand over the answer (the theorem a task
asks you to prove is exactly what good retrieval surfaces), algorithms because
they are long and only wanted when the task is to implement one, which the user
knows and the ranking does not.
"""

from .prompts import entry_tokens, tokenize, _inverse_document_frequency
from .toc import sort_key

# What counts as a statement. "Satz", "Lemma", "Korollar" and "Proposition" are
# the same thing under different names, and a script uses whichever it prefers;
# the English half is there because the corpus contains English scripts.
STATEMENT_TYPES = (
    "Definition", "Satz", "Lemma", "Korollar", "Proposition",
    "Theorem", "Corollary",
)

# Opt-in, via the picker. Rare outside applied courses - of the ten corpus
# scripts only VO3_Optimierung numbers its algorithms - but there the exercises
# are "implement Algorithmus 4.1.7", and then it is the one thing needed.
ALGORITHM_TYPES = ("Algorithmus", "Algorithm")


def is_statement(entry: dict, include_algorithms: bool = False) -> bool:
    if include_algorithms and entry.get("type") in ALGORITHM_TYPES:
        return True
    return entry.get("type") in STATEMENT_TYPES


def section_of(entry: dict) -> str | None:
    """The outline key an entry was placed under, set by core.toc at ingest."""
    return entry.get("section")


def covers(selected: str, key: str) -> bool:
    """Does selecting `selected` include section `key`? True for the section
    itself and for everything nested under it - "3" covers "3.1" and "3.1.2",
    but not "30"."""
    return key == selected or key.startswith(selected + ".")


def statements(entries: list[dict], include_algorithms: bool = False) -> list[dict]:
    return [e for e in entries if is_statement(e, include_algorithms)]


def group_by_section(entries: list[dict],
                     include_algorithms: bool = False) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in statements(entries, include_algorithms):
        key = section_of(entry)
        if key:
            grouped.setdefault(key, []).append(entry)
    return grouped


def entries_in(entries: list[dict], selected: list[str],
               include_algorithms: bool = False) -> list[dict]:
    """All statements in the selected sections and anything nested under them."""
    chosen = [
        e for e in statements(entries, include_algorithms)
        if (key := section_of(e)) is not None
        and any(covers(s, key) for s in selected)
    ]
    return sorted(chosen, key=lambda e: (sort_key(section_of(e) or "0"), e.get("page", 0)))


def rank_sections(task_text: str, entries: list[dict]) -> list[tuple[str, float]]:
    """Sections most likely to be relevant to a task, best first.

    A section scores as its best-matching statement, not the sum: a section
    containing one dead-on definition beats a long one with many weak matches,
    which is the same length bias that broke per-entry ranking."""
    from .prompts import score_entry

    task_tokens = tokenize(task_text)
    idf = _inverse_document_frequency(entries)
    best: dict[str, float] = {}
    for entry in statements(entries):
        key = section_of(entry)
        if key is None:
            continue
        score = score_entry(task_tokens, entry, idf)
        if score > best.get(key, 0.0):
            best[key] = score
    return sorted(((k, v) for k, v in best.items() if v > 0),
                  key=lambda kv: -kv[1])


# A runner-up section is only suggested when it scores close to the winner.
# Taking a fixed top-2 doubled the prompt for nothing: on the epigraph task the
# second-placed section scored 37% of the first and was unrelated, while on the
# subdifferential task the runner-up scored 79% and genuinely belonged. The
# ratio separates those two cases; a fixed count cannot.
RUNNER_UP_RATIO = 0.7
MAX_SUGGESTED = 3

# How far the winner must stand out from the field before runner-ups are
# trusted at all. When a task carries no subject vocabulary ("Bestimmen Sie
# alle ganzzahligen Lösungen...") every section scores about the same, the
# ranking is noise, and the runner-up ratio would then WIDEN the selection
# exactly where confidence is lowest. Measured on the example material:
# discriminating rankings sit at top/mean 3.3-4.8, flat ones at 1.6-2.5.
DISCRIMINATION_THRESHOLD = 3.0


def suggest_sections(task_text: str, entries: list[dict]) -> list[str]:
    """Best guess at the relevant sections - a starting point for the user to
    correct, not an answer. When a task carries no subject vocabulary of its own
    ("Lösen Sie Aufgabe (1.11) vom Skriptum") the ranking is flat and the guess
    is worthless; nothing here can detect that, which is why the picker exists."""
    ranked = rank_sections(task_text, entries)
    if not ranked:
        return []

    scores = [score for _, score in ranked]
    top = scores[0]
    mean = sum(scores) / len(scores)
    if mean <= 0 or top / mean < DISCRIMINATION_THRESHOLD:
        return [ranked[0][0]]

    cutoff = top * RUNNER_UP_RATIO
    return [s for s, score in ranked[:MAX_SUGGESTED] if score >= cutoff]


def section_digests(entries: list[dict], titles: dict[str, str] | None = None,
                    within: list[str] | None = None,
                    budget: int | None = None) -> dict[str, str]:
    """Each section's statements as one text, keyed by section - what a model
    (integrations.jev) reads to judge relevance. The title leads, since it often
    names the topic in words the statements never use.

    `within` narrows to those sections, as in select(); a `within` that matches
    nothing is ignored rather than leaving nothing to rank. Over `budget`
    characters, every section is cut to an equal share: a long section then
    loses its tail, not a short one its only definition."""
    from .toc import label

    grouped = group_by_section(entries)
    if within:
        narrowed = {k: v for k, v in grouped.items()
                    if any(covers(w, k) for w in within)}
        grouped = narrowed or grouped
    digests = {}
    for key in sorted(grouped, key=sort_key):
        parts = [label(titles or {}, key)]
        for e in grouped[key]:
            name = f" ({e['name']})" if e.get("name") else ""
            parts.append(f"{e['type']} {e.get('number', '')}{name}: {e.get('text', '')}")
        digests[key] = "\n".join(parts)

    total = sum(len(d) for d in digests.values())
    if budget and total > budget:
        share = budget // max(len(digests), 1)
        digests = {k: d if len(d) <= share else d[:share - 1] + "…"
                   for k, d in digests.items()}
    return digests


# A model's relevance (0..1, from Jev's four-level rubric) is on an absolute
# scale, unlike the keyword scores above, so a fixed bar works: 2/3 is "contains
# some definitions or theorems a solution would use".
RELEVANCE_THRESHOLD = 2 / 3


def suggest_from_relevance(relevance: dict[str, float]) -> list[str]:
    """Sections a model rated as needed, best first, capped like the keyword
    suggestion. When none clears the bar the best one is still taken - an empty
    selection would fall back to the keyword guess, which is worse."""
    ranked = sorted(relevance.items(), key=lambda kv: -kv[1])
    if not ranked:
        return []
    top = ranked[0][1]
    picked = [k for k, v in ranked[:MAX_SUGGESTED]
              if v >= RELEVANCE_THRESHOLD and v >= top * RUNNER_UP_RATIO]
    return picked or [ranked[0][0]]


def select(task_text: str, entries: list[dict],
           sections: list[str] | None = None,
           include_algorithms: bool = False,
           within: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Returns (entries_for_the_prompt, sections_actually_used). `within` keeps
    the automatic suggestion inside those sections; a hand-made selection is
    taken as it is."""
    chosen = sections
    if not chosen and within:
        pool = [e for e in entries if (key := section_of(e)) is not None
                and any(covers(w, key) for w in within)]
        chosen = suggest_sections(task_text, pool) if pool else None
    if not chosen:
        chosen = suggest_sections(task_text, entries)
    return entries_in(entries, chosen, include_algorithms), chosen
