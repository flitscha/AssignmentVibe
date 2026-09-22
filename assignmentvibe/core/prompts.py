"""
Step 4: use-case + task + (simulated) partial solution + knowledge context
-> finished LLM prompt.

Context selection (prototype): simple keyword scoring between the task text
and the knowledge entries (Definition/Satz/...) - not embedding-based
retrieval, but it demonstrates that automatic chapter/theorem selection
works in principle. Replace with real embedding search for a production
version.

Note: the instruction text and the prompt template strings further
down are deliberately kept in German - this is product content sent to an
LLM on behalf of a German-speaking student working through German course
material, not internal code. Only identifiers/comments are English here.

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
    "Loese die folgende Aufgabe. Rechne die Schritte einzeln und nachvollziehbar "
    "vor und benenne bei jedem Schritt, welche Definition oder welcher Satz aus "
    "dem Skriptum unten ihn rechtfertigt. Halte dich an die Notation des "
    "Skriptums. Wenn etwas in der Angabe unklar ist, sag das, statt es zu raten."
)

# Canned replies to paste back into the chat. The point is the keyboard: these
# are used on a tablet or with a pen in hand, where typing "erklaere den letzten
# Schritt genauer" is the expensive part of asking it. Each one has to stand
# alone as a chat message - no placeholders to fill in, nothing to edit after
# pasting - which is why none of them name a step number or a symbol.
FOLLOW_UPS = [
    ("\U0001F50E", "Letzten Schritt genauer",
     "Erklaere den letzten Schritt ausfuehrlicher. Was genau passiert da, und "
     "warum ist er erlaubt?"),
    ("\U0001F4CF", "Schritt fuer Schritt",
     "Mach das kleinschrittiger. Lass keinen Zwischenschritt aus, auch nicht die, "
     "die offensichtlich wirken."),
    ("\U0001F4D6", "An das Skript halten",
     "Benutze ausschliesslich die Definitionen und Saetze aus dem Skriptum oben. "
     "Wenn du etwas brauchst, das dort nicht steht, sag es, statt es zu verwenden."),
    ("\U0001F4A1", "Nur ein Hinweis",
     "Verrate mir die Loesung noch nicht. Gib mir nur einen Hinweis, wie ich "
     "selbst auf die Idee komme."),
    ("\u27A1\uFE0F", "Nur der naechste Schritt",
     "Nur der naechste Schritt, nicht die ganze weitere Loesung."),
    ("\u2753", "Warum gilt das?",
     "Warum gilt das? Nenne mir die Definition oder den Satz, der diesen Schritt "
     "rechtfertigt, und erklaere, warum seine Voraussetzungen hier erfuellt sind."),
    ("\U0001F50D", "Fehler suchen",
     "Pruefe das noch einmal nach. Falls ein Fehler drin ist, sag mir, an welcher "
     "Stelle - und korrigiere nur diese Stelle, nicht die ganze Rechnung."),
    ("\U0001F9E0", "Idee dahinter",
     "Lass die Rechnung kurz beiseite: was ist die Idee hinter diesem Vorgehen, "
     "und woran haette ich selbst erkennen koennen, dass es hier passt?"),
    ("\u2702\uFE0F", "Kuerzer",
     "Zu ausfuehrlich. Fasse es kurz: nur die Rechnung und das Ergebnis."),
    ("\U0001F9EA", "Beispiel dazu",
     "Gib mir ein kleines konkretes Beispiel dazu, an dem ich nachvollziehen "
     "kann, dass das stimmt."),
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


def format_knowledge_entry(e: dict, include_proof: bool = True) -> str:
    header = f"{e['type']} {e['number']}"
    if e.get("name"):
        header += f" ({e['name']})"
    out = f"{header}:\n{e['text']}"
    if include_proof and e.get("proof"):
        out += f"\nBeweis: {e['proof']}"
    return out


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
) -> str:
    """`sections` selects script sections to include in full (see
    core.selection); without it, the sections its keyword ranking suggests are
    used."""
    from . import selection
    from .toc import label as section_label

    section_titles = section_titles or {}
    context, used_sections = selection.select(
        task["text"], knowledge_entries, sections, include_algorithms)
    if include_proofs is None:
        include_proofs = INCLUDE_PROOFS_BY_DEFAULT

    lines = []
    lines.append(SOLVE_INSTRUCTION)
    lines.append("")
    lines.append(f"# Kontext: {course_name}")
    if sheet_meta.get("discussion_date"):
        lines.append(f"Aufgabenblatt {sheet_meta.get('sheet_number', '?')}, "
                      f"Besprechung: {sheet_meta['discussion_date']}")
    lines.append("")
    lines.append(f"# Aufgabe {task['number']}"
                  + (f": {task['title']}" if task.get("title") else ""))
    lines.append(task["text"])
    lines.append("")

    if context:
        # Naming the sections lets the reader (and the model) see what the
        # context covers - and, just as usefully, what it does not.
        where = (", ".join(section_label(section_titles, s) for s in used_sections)
                 if used_sections else "?")
        lines.append(f"# Aus dem Skriptum: Abschnitt {where}")
        contents = "alle Definitionen und Saetze dieser Abschnitte"
        if include_algorithms:
            contents += " samt Algorithmen"
        if not include_proofs:
            contents += ", ohne Beweise"
        lines.append(f"({contents})")
        for e in context:
            lines.append("")
            lines.append(format_knowledge_entry(e, include_proof=include_proofs))
        lines.append("")

    lines.append("# Meine bisherige Teilloesung")
    lines.append(partial_solution.strip() if partial_solution else "(noch nichts probiert)")

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
