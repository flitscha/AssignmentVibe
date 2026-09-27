"""
Decide which knowledge entries go into a prompt: exactly the ones chosen, and
nothing when nothing is.

Two grains, freely mixed:

1. SECTIONS. Every statement of a section of the script's outline ("3", "3.1",
   "3.1.2"); selecting a parent selects everything below it - see core.toc for
   where those keys come from. That prefix relationship is the whole reason the
   picker can offer "all of chapter 3" as one row. Section 3.1 of the
   Optimierung script is 11 entries / ~2.3k characters.

2. SINGLE STATEMENTS, by id ("Satz 3.1.5"). This is what Jev picks
   (integrations.jev asks, per statement and per proof, whether the task needs
   it; pick_from_judgement below turns the answers into a selection).

There used to be a third way in: keyword ranking when nothing was chosen. It
guessed without being asked, and a wrong guess costs prompt space and can
steer the model - so an empty selection now means an empty context.

Only statements are included: definitions and the theorem family, in German or
English. Remarks, examples and the prose between them are left out - they are
bulk without being what a task needs to cite. Algorithms and proofs are opt-in
and off by default: proofs because they hand over the answer (the theorem a task
asks you to prove is exactly what a good selection contains), algorithms because
they are long and only wanted when the task is to implement one.
"""

from .prompts import entry_id
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


def script_order(e: dict) -> tuple:
    return (sort_key(section_of(e) or "0"), e.get("page", 0))


def chosen(entries: list[dict], sections: list[str] | None,
           statement_ids: list[str] | None = None,
           include_algorithms: bool = False) -> list[dict]:
    """Everything a prompt carries: the statements of the chosen sections plus
    the single ones, each once, in the script's order. A single statement is
    taken even if it is an algorithm while algorithms are off - it was picked
    by name."""
    ids = set(statement_ids or ())
    picked = entries_in(entries, list(sections or ()), include_algorithms)
    seen = {id(e) for e in picked}
    picked += [e for e in statements(entries, include_algorithms=True)
               if entry_id(e) in ids and id(e) not in seen]
    return sorted(picked, key=script_order)


def compress(entries: list[dict], ids: set[str],
             include_algorithms: bool = False) -> tuple[list[str], list[str]]:
    """(sections, single ids) that select exactly `ids`: every outline node
    whose statements are all in `ids` becomes a section, the outermost one
    wins, and the rest stay single. The picker works on statements alone and
    stores this; it keeps the prompt's header naming "section 3.1" rather than
    eleven numbers when all of 3.1 was ticked one by one or picked by Jev."""
    by_key: dict[str, set[str]] = {}
    for e in statements(entries, include_algorithms):
        key = section_of(e)
        if not key:
            continue
        parts = key.split(".")
        for depth in range(1, len(parts) + 1):
            by_key.setdefault(".".join(parts[:depth]), set()).add(entry_id(e))

    sections: list[str] = []
    for key in sorted(by_key, key=lambda k: (k.count("."), sort_key(k))):
        if any(covers(s, key) for s in sections):
            continue
        if by_key[key] <= ids:
            sections.append(key)
    covered = set().union(*(by_key[s] for s in sections)) if sections else set()
    singles = [entry_id(e) for e in sorted(statements(entries, True), key=script_order)
               if entry_id(e) in ids and entry_id(e) not in covered]
    return sorted(sections, key=sort_key), singles


# The longest proofs run to ~5k characters; the first part says which technique
# it uses, and that is what judging its relevance needs.
MAX_PROOF_CHARS = 2500


def judgement_items(entries: list[dict],
                    include_algorithms: bool = False) -> dict[str, dict[str, str]]:
    """{id: {"statement": ..., "proof": ...}} for every statement, in the
    script's order - what integrations.jev asks about. The name leads, since it
    often says what a statement is about in words its text never uses ("2.
    Isomorphiesatz")."""
    items = {}
    for e in sorted(statements(entries, include_algorithms), key=script_order):
        name = f"({e['name']}) " if e.get("name") else ""
        item = {"statement": f"{name}{e.get('text', '')}"}
        if e.get("proof"):
            proof = e["proof"]
            item["proof"] = (proof if len(proof) <= MAX_PROOF_CHARS
                             else proof[:MAX_PROOF_CHARS - 1] + "…")
        items.setdefault(entry_id(e), item)
    return items


# Jev answers each yes/no question with a probability; at or above this it
# counts as yes.
JEV_THRESHOLD = 0.5


def pick_from_judgement(statement_p: dict[str, float], proof_p: dict[str, float],
                        threshold: float = JEV_THRESHOLD
                        ) -> tuple[list[str], list[str]]:
    """(statement ids, proof ids) from Jev's answers, in the order asked. A
    statement whose proof is wanted comes along even when it was not judged
    needed by itself - a proof without its statement is unreadable."""
    proofs = [i for i, p in proof_p.items() if p >= threshold]
    wanted = set(proofs)
    picked = [i for i, p in statement_p.items() if p >= threshold or i in wanted]
    return picked, proofs
