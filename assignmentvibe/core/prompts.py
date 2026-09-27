"""
Step 4: use-case + task + (simulated) partial solution + knowledge context
-> finished LLM prompt.

Context selection (prototype): simple keyword scoring between the task text
and the knowledge entries (Definition/Satz/...) - not embedding-based
retrieval, but it demonstrates that automatic chapter/theorem selection
works in principle. Replace with real embedding search for a production
version.

The prompt itself is English while the material it carries (task text,
definitions, theorems) is whatever language the course is in. That mix is
deliberate: the instruction is the tool talking, the rest is quoted source.

Depends on nothing else in this project (pure functions over plain dicts).
"""

import json
import math
import re
import sys
from pathlib import Path

# There is one thing to ask for: solve it. The seven modes this replaces
# ("hint", "next step", "explain the concept", ...) were the tool guessing how
# much of an answer the reader wanted, before the answer existed. That guess is
# free to make afterwards and impossible to make before - you read the first
# step, see the idea, and stop. What the modes were really for lives on in
# FOLLOW_UPS below, where it costs one click at the moment you know you need it.
SOLVE_INSTRUCTION = (
    "Solve the task below. Work through it one step at a time, and for each step "
    "name the definition or theorem from the lecture notes below that justifies "
    "it. Stick to the notation used in the notes. If anything in the task is "
    "ambiguous, say so instead of guessing."
)

# Canned replies to paste back into the chat. The point is the keyboard: these
# are used on a tablet or with a pen in hand, where typing "erklaere den letzten
# Schritt genauer" is the expensive part of asking it. Each one has to stand
# alone as a chat message - no placeholders to fill in, nothing to edit after
# pasting - which is why none of them name a step number or a symbol.
FOLLOW_UPS = [
    ("\U0001F50E", "Expand last step",
     "Expand on that last step. What exactly happens there, and why is it allowed?"),
    ("\U0001F4CF", "Step by step",
     "Break that down further. Do not skip any intermediate step, including the "
     "ones that look obvious."),
    ("\U0001F4D6", "Stick to the notes",
     "Use only the definitions and theorems from the lecture notes above. If you "
     "need something that is not in them, say so instead of using it."),
    ("\U0001F4A1", "Just a hint",
     "Do not give me the solution yet. Just give me a hint so I can get to the "
     "idea myself."),
    ("\u27A1\uFE0F", "Only the next step",
     "Only the next step, not the rest of the solution."),
    ("\u2753", "Why does that hold?",
     "Why does that hold? Name the definition or theorem that justifies this step, "
     "and explain why its conditions are met here."),
    ("\U0001F50D", "Find the mistake",
     "Check that again. If there is a mistake, tell me where it is - and fix only "
     "that spot, not the whole calculation."),
    ("\U0001F9E0", "Idea behind it",
     "Set the calculation aside for a moment: what is the idea behind this "
     "approach, and how could I have recognised myself that it fits here?"),
    ("\u2702\uFE0F", "Shorter",
     "Too long-winded. Keep it short: just the calculation and the result."),
    ("\U0001F9EA", "Give an example",
     "Give me a small concrete example I can follow to see that this is true."),
]

# German stopwords - the source material and task texts are German, so the
# keyword scoring below has to filter German stopwords to be useful.
STOPWORDS = set(
    "der die das ein eine einer einem einen und oder ist sei seien sind man "
    "wir sie es zu von mit fuer auf im in an als dass wenn falls genau also "
    "nicht auch bzw etc oben unten sowie oft oder wie oben also nach vom "
    "zum zur bei aus dem den des"
    .split()
)


# German inflection is enough to break exact matching on the words that matter:
# a task says "Epigraphs" where the script says "Epigraph", "Funktionen" where
# it says "Funktion". A full stemmer would be overkill (and a dependency), so
# we strip the handful of endings that actually cause misses, and only when
# enough of the word survives to stay distinctive.
GERMAN_ENDINGS = ("en", "es", "er", "em", "e", "n", "s")
MIN_STEM_LENGTH = 5


def stem(word: str) -> str:
    for ending in GERMAN_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= MIN_STEM_LENGTH:
            return word[: -len(ending)]
    return word


def tokenize(text: str) -> set[str]:
    # 3 letters, not 4: "epi" in "epi(f)" is exactly the kind of short technical
    # token that identifies the relevant definition.
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", text.lower())
    return {stem(w) for w in words if w not in STOPWORDS}


def entry_tokens(entry: dict) -> set[str]:
    """Tokens of an entry - its name counts as much as its body.

    Some results are only findable through the name: the algebra script states
    "Satz 2.2.6 (2. Isomorphiesatz)" whose text never contains the word
    "Isomorphiesatz", so a task saying "Beweisen Sie den zweiten Isomorphiesatz"
    could not reach it at all. The proof is deliberately NOT tokenized: it adds
    length without saying what the entry is about."""
    return tokenize(f"{entry.get('name') or ''} {entry.get('text', '')}")


def _inverse_document_frequency(entries: list[dict]) -> dict[str, float]:
    """How rare each token is across the script. Without this, "funktion" and
    "menge" - which appear in half the entries and say nothing about which one
    is relevant - count as much as "epigraph", which appears in two."""
    document_count = len(entries) or 1
    frequency: dict[str, int] = {}
    for entry in entries:
        for token in entry_tokens(entry):
            frequency[token] = frequency.get(token, 0) + 1
    return {token: math.log(document_count / count)
            for token, count in frequency.items()}


def score_entry(task_tokens: set[str], entry: dict,
                idf: dict[str, float] | None = None) -> float:
    """Sum of the rarity of the shared tokens, damped by how long the entry is.

    Both halves matter. Without rarity weighting, common vocabulary decides the
    ranking. Without the length damping, a long Korollar-plus-proof outscores a
    two-line Definition purely by having more words to collide with - which is
    exactly how "Korollar 4.1.6" (gradient descent) beat "Definition 3.1.4"
    (epigraph) on a task about epigraphs."""
    tokens = entry_tokens(entry)
    shared = task_tokens & tokens
    if not shared:
        return 0.0
    weights = idf if idf is not None else {}
    # Default weight 1.0 keeps the function meaningful when called without a
    # corpus (tests, single entries).
    overlap = sum(weights.get(token, 1.0) for token in shared)
    return overlap / math.sqrt(len(tokens) or 1)


def select_context(task_text: str, knowledge_entries: list[dict], top_k: int = 3) -> list[dict]:
    task_tokens = tokenize(task_text)
    idf = _inverse_document_frequency(knowledge_entries)
    scored = [(score_entry(task_tokens, e, idf), e) for e in knowledge_entries]
    scored = [t for t in scored if t[0] > 0]
    # Ties broken by the script's own order, so the output is stable between runs.
    scored.sort(key=lambda t: -t[0])
    return [e for _, e in scored[:top_k]]


# Proofs stay out unless asked for. Retrieval is good enough to surface the very
# theorem a task asks you to prove - "Zeigen Sie: f konvex <=> epi(f) konvex"
# pulls up Satz 3.1.5, which states exactly that - so shipping its proof along
# would hand over the solution inside the context block.
INCLUDE_PROOFS_BY_DEFAULT = False


def entry_id(e: dict) -> str:
    """How a single statement is named when its proof is chosen on its own -
    "Satz 3.1.5". Type and number together: a script that counts its types
    separately has a "Satz 1.2" and a "Definition 1.2"."""
    return f"{e['type']} {e['number']}"


def proof_wanted(e: dict, include_proofs: bool,
                 proof_of: "set[str] | list[str] | None" = None) -> bool:
    """All proofs, or only the ones picked. Picking single proofs is the usual
    case: a task needs the idea of one proof, and every other proof in the
    chapter is noise at best and the answer to a different task at worst."""
    return include_proofs or (bool(proof_of) and entry_id(e) in proof_of)


def format_knowledge_entry(e: dict, include_proof: bool = True) -> str:
    header = entry_id(e)
    if e.get("name"):
        header += f" ({e['name']})"
    out = f"{header}:\n{e['text']}"
    if include_proof and e.get("proof"):
        out += f"\nProof: {e['proof']}"
    return out


def resolve_exercises(task: dict, exercises: list[dict] | None) -> tuple[list[dict], list[str]]:
    """The script's own exercises a task refers to ("Lösen Sie Aufgabe (1.1) vom
    Skriptum"), and the references that could not be found."""
    from .exercises import find

    found, missing = [], []
    for ref in task.get("script_references") or []:
        exercise = find(exercises or [], ref)
        if exercise:
            found.append(exercise)
        else:
            missing.append(ref)
    return found, missing


def task_query(task: dict, exercises: list[dict] | None
               ) -> tuple[str, list[str], list[dict]]:
    """(text to rank sections by, chapters to rank within, exercises the task
    refers to) - shared by the keyword ranking below and by Jev in cli.py, so
    both judge the same text."""
    found, _ = resolve_exercises(task, exercises)
    text = "\n".join([task["text"]] + [e["text"] for e in found])
    chapters = sorted({e["section"].split(".")[0] for e in found if e.get("section")})
    return text, chapters, found


def task_context(task: dict, knowledge_entries: list[dict],
                 exercises: list[dict] | None = None,
                 sections: list[str] | None = None,
                 include_algorithms: bool = False,
                 ) -> tuple[list[dict], list[str], list[dict]]:
    """(statements for the prompt, sections they came from, exercises the task
    refers to).

    A task that only says "Aufgabe (1.1) vom Skriptum" has no vocabulary to rank
    sections by, so the exercise's own text stands in for it. And an exercise
    sits at the end of the chapter it practises - the ranking is kept inside
    that chapter, where a stray keyword from chapter 6 cannot win."""
    from . import selection

    text, chapters, found = task_query(task, exercises)
    context, used = selection.select(text, knowledge_entries, sections,
                                     include_algorithms, within=chapters or None)
    return context, used, found


def build_prompt(
    task: dict,
    sheet_meta: dict,
    knowledge_entries: list[dict],
    partial_solution: str | None = None,
    course_name: str = "",
    sections: list[str] | None = None,
    include_proofs: bool | None = None,
    include_algorithms: bool = False,
    section_titles: dict[str, str] | None = None,
    exercises: list[dict] | None = None,
    proof_of: list[str] | None = None,
) -> str:
    """`sections` selects script sections to include in full (see
    core.selection); without it, the sections its keyword ranking suggests are
    used. `proof_of` names single statements ("Satz 3.1.5") whose proofs go in
    even while `include_proofs` is off."""
    from .toc import label as section_label

    section_titles = section_titles or {}
    context, used_sections, referenced = task_context(
        task, knowledge_entries, exercises, sections, include_algorithms)
    if include_proofs is None:
        include_proofs = INCLUDE_PROOFS_BY_DEFAULT
    proof_of = set(proof_of or ())

    lines = []
    lines.append(SOLVE_INSTRUCTION)
    lines.append("")
    lines.append(f"# Course: {course_name}")
    if sheet_meta.get("discussion_date"):
        lines.append(f"Sheet {sheet_meta.get('sheet_number', '?')}, "
                      f"due: {sheet_meta['discussion_date']}")
    lines.append("")
    lines.append(f"# Task {task['number']}"
                  + (f": {task['title']}" if task.get("title") else ""))
    lines.append(task["text"])
    lines.append("")
    # The sheet only points at the script; this is the task the model can
    # actually work on.
    for exercise in referenced:
        title = f": {exercise['title']}" if exercise.get("title") else ""
        lines.append(f"## Exercise {exercise['number']} from the lecture notes{title}")
        lines.append(exercise["text"])
        lines.append("")

    if context:
        # Naming the sections lets the reader (and the model) see what the
        # context covers - and, just as usefully, what it does not.
        where = (", ".join(section_label(section_titles, s) for s in used_sections)
                 if used_sections else "?")
        lines.append(f"# From the lecture notes: section {where}")
        contents = "every definition and theorem of these sections"
        if include_algorithms:
            contents += ", algorithms included"
        with_proof = [entry_id(e) for e in context
                      if not include_proofs and e.get("proof") and entry_id(e) in proof_of]
        if with_proof:
            contents += ", proofs only for " + ", ".join(with_proof)
        elif not include_proofs:
            contents += ", proofs omitted"
        lines.append(f"({contents})")
        for e in context:
            lines.append("")
            lines.append(format_knowledge_entry(
                e, include_proof=proof_wanted(e, include_proofs, proof_of)))
        lines.append("")

    lines.append("# What I have so far")
    lines.append(partial_solution.strip() if partial_solution else "(nothing yet)")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sheet_path = Path(sys.argv[1])
    task_num = int(sys.argv[2])
    knowledge_path = Path(sys.argv[3])
    course_name = sys.argv[4] if len(sys.argv) > 4 else ""
    partial_solution = sys.argv[5] if len(sys.argv) > 5 else None

    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    task = next(t for t in sheet["tasks"] if t["number"] == task_num)
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    titles = {n["key"]: n["title"] for n in knowledge.get("sections", [])
              if n.get("title")}
    print(build_prompt(task, sheet, knowledge["entries"], partial_solution,
                       course_name, section_titles=titles))
