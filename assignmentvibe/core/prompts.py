"""
Step 4: use-case + task + (simulated) partial solution + knowledge context
-> finished LLM prompt.

Context is only what was chosen - whole sections, single statements (by hand
or by Jev, see integrations/jev.py), single proofs. Nothing chosen, no context:
a guess the user did not ask for costs prompt space and can mislead the model.

The prompt itself is English while the material it carries (task text,
definitions, theorems) is whatever language the course is in. That mix is
deliberate: the instruction is the tool talking, the rest is quoted source.

Depends on nothing else in this project (pure functions over plain dicts).
"""

import json
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

# Proofs stay out unless asked for. The theorem a task asks you to prove is
# exactly what a good selection contains - "Zeigen Sie: f konvex <=> epi(f)
# konvex" is Satz 3.1.5 - so shipping its proof along would hand over the
# solution inside the context block.
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


def task_query(task: dict, exercises: list[dict] | None) -> str:
    """What the task asks, as one text to judge relevance against. A task that
    only says "Aufgabe (1.1) vom Skriptum" says nothing by itself - the
    exercise it points at does."""
    found, _ = resolve_exercises(task, exercises)
    return "\n".join([task["text"]] + [e["text"] for e in found])


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
    statements: list[str] | None = None,
) -> str:
    """`sections` selects script sections to include in full and `statements`
    single ones by id ("Satz 3.1.5", see core.selection); with neither, the
    prompt carries no lecture notes at all. `proof_of` names statements whose
    proofs go in even while `include_proofs` is off."""
    from . import selection
    from .toc import label as section_label

    section_titles = section_titles or {}
    sections = list(sections or ())
    context = selection.chosen(knowledge_entries, sections, statements,
                               include_algorithms)
    referenced, _ = resolve_exercises(task, exercises)
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
        singles = [entry_id(e) for e in context
                   if not any(selection.covers(k, selection.section_of(e) or "")
                              for k in sections)]
        where = []
        if sections:
            where.append("section " + ", ".join(section_label(section_titles, k)
                                                 for k in sections))
        if singles:
            where.append(", ".join(singles))
        lines.append(f"# From the lecture notes: {'; '.join(where)}")
        contents = ("every definition and theorem of these sections" if sections
                    else "the definitions and theorems chosen for this task")
        if sections and singles:
            contents += ", plus the single statements named"
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
