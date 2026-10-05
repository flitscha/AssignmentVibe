"""
Task + chosen lecture notes + earlier exercises (+ an attempt, if given)
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
#
# How it asks. Chat models tend to pad (restating the task, general remarks, a
# summary) and still wave through the one step the argument rests on with
# "clearly". So: the direct route, every step justified, and the care spent
# where the difficulty is. The lines about definitions, theorems and earlier
# exercises only appear when the prompt carries such things - "use the
# definitions below" above a prompt without any is noise.
SOLVE_HEAD = "Solve {what} the way a model solution would."
SOLVE_RULES = [
    "Go straight to the result: no restating the task, no general remarks, no "
    "summary at the end, no alternative approaches.",
    "Justify every step. Routine steps get a line; the steps the argument rests "
    "on are carried out in full - never skipped or covered by \"clearly\" or "
    "\"similarly\".",
]
DEFINITIONS_RULE = "Use the definitions below exactly as stated there, in their notation."
RESULTS_RULE = ("The {what} below may be cited where they help - they are offered, "
                "not required. Do not force them in.")
TAIL_RULES = [
    "Any other result must be well known (standard Bachelor material): name it "
    "and quote, right below, the exact statement you use.",
    "If the task is ambiguous or seems wrong, say so instead of guessing.",
    "Write in the language of the task, in later replies too.",
]
WHOLE_TASK = "the task below"
# A task with parts a), b), c) is often solved one part at a time, and each
# part can be long; asking for all of it at once gets a long answer to parts
# not reached yet. With a part chosen the prompt still carries the whole task
# - the earlier parts are often what the chosen one builds on - but asks for
# that part only, and names it again at the end.
ONE_PART = "only part {label}) of the task below"
EARLIER_PARTS = " The parts before it may be used as given."


def instruction(part: str | None = None, definitions: bool = False,
                theorems: bool = False, earlier: bool = False) -> str:
    """The instruction a prompt opens with; see SOLVE_RULES above."""
    rules = list(SOLVE_RULES)
    if definitions:
        rules.append(DEFINITIONS_RULE)
    offered = [w for w, on in (("theorems", theorems), ("earlier exercises", earlier)) if on]
    if offered:
        rules.append(RESULTS_RULE.format(what=" and ".join(offered)))
    rules += TAIL_RULES
    head = SOLVE_HEAD.format(what=ONE_PART.format(label=part) if part else WHOLE_TASK)
    if part:
        head += EARLIER_PARTS
    return "\n".join([head] + [f"- {r}" for r in rules])


# Canned replies to paste back into the chat. The point is the keyboard: these
# are used on a tablet or with a pen in hand, where typing "erklaere den letzten
# Schritt genauer" is the expensive part of asking it. Each one has to stand
# alone as a chat message - no placeholders to fill in, nothing to edit after
# pasting - which is why none of them name a step number or a symbol.
FOLLOW_UPS = [
    ("\U0001F50E", "Explain that step",
     "Explain the last step in more detail: what exactly happens there, and why "
     "is it allowed?"),
    ("\u2753", "Why does that hold?",
     "Why does that hold? Name the definition or theorem that justifies this step, "
     "and show that its conditions are met here."),
    ("\U0001F9E9", "Split into lemmas",
     "This is too long to see the idea. Move the technical parts into auxiliary "
     "lemmas: state them first, then give the main proof in a few lines using "
     "them. After that, prove each lemma cleanly."),
    ("\U0001F9E0", "Idea behind it",
     "Set the calculation aside for a moment: what is the idea behind this "
     "approach, and how could I have recognised myself that it fits here?"),
    ("\U0001F4A1", "Just a hint",
     "Do not give me the solution yet. Just give me a hint so I can get to the "
     "idea myself."),
    ("\u27A1\uFE0F", "Only the next step",
     "Only the next step, not the rest of the solution."),
    ("\U0001F4DD", "Check my attempt",
     "Attached is my own attempt. Check it: is the approach sensible? Is every "
     "step correct - if not, point to the first mistake exactly? And how does it "
     "continue from where I stopped? Build on my attempt instead of starting over."),
    ("\U0001F50D", "Check your solution",
     "Check your solution again, step by step. If there is a mistake, say where "
     "it is and fix only that spot, not the whole solution."),
    ("\U0001F9EA", "Give an example",
     "Give me a small concrete example I can follow to see that this is true."),
    ("\U0001F4C4", "Write it up",
     "Now write the complete solution out cleanly, the way I would hand it in: "
     "every step, no commentary."),
]

# Proofs stay out unless asked for. The theorem a task asks you to prove is
# exactly what a good selection contains - "Zeigen Sie: f konvex <=> epi(f)
# konvex" is Satz 3.1.5 - so shipping its proof along would hand over the
# solution inside the context block.
INCLUDE_PROOFS_BY_DEFAULT = False


def entry_id(e: dict) -> str:
    """How a single statement is named when its proof is chosen on its own -
    "Satz 3.1.5". Type and number together: a script that counts its types
    separately has a "Satz 1.2" and a "Definition 1.2". A number the script
    uses twice carries its page as well - see core.knowledge.set_ids."""
    return e.get("id") or f"{e['type']} {e['number']}"


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


# What a slide holds, by its title ("Definition", "Lemma (case analysis)"),
# for the instruction's rules on definitions and citable results.
SLIDE_RESULT_WORDS = ("theorem", "lemma", "corollary", "proposition", "satz", "korollar")


def kind_of(e: dict) -> str:
    """"definition", "result" or "other" - for a slide, read off its title."""
    if e.get("type") == "Slide":
        title = (e.get("name") or "").lower()
        if title.startswith("definition"):
            return "definition"
        return "result" if title.startswith(SLIDE_RESULT_WORDS) else "other"
    return "definition" if e.get("type") == "Definition" else "result"


def source_name(context: list[dict]) -> str:
    """"lecture notes", "lecture slides", or both - where the context is from."""
    slides = any(e.get("type") == "Slide" for e in context)
    notes = any(e.get("type") != "Slide" for e in context)
    if slides and notes:
        return "lecture notes and slides"
    return "lecture slides" if slides else "lecture notes"


def context_size(entries: list[dict], include_proofs: bool,
                 proof_of: "set[str] | list[str] | None" = None) -> int:
    """Characters these entries cost a prompt: formatted as build_prompt
    formats them, with the proofs that are switched on - not the raw text."""
    proof_of = set(proof_of or ())
    return sum(len(format_knowledge_entry(
                   e, include_proof=proof_wanted(e, include_proofs, proof_of))) + 1
               for e in entries)


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


def task_parts(task: dict, exercises: list[dict] | None) -> tuple[str, list[dict]]:
    """(the text before the first part, [{"label", "text"}]) of what a task
    asks - the exercise it points at, when it points at exactly one, since
    "Lösen Sie Aufgabe (1.1) vom Skriptum" has no parts of its own. No parts:
    ("", [])."""
    from .assignments import SUBPART_RE, split_subparts

    found, _ = resolve_exercises(task, exercises)
    text = found[0]["text"] if len(found) == 1 else task["text"]
    parts = split_subparts(text)
    if not parts:
        return "", []
    return text[:SUBPART_RE.search(text).start()].strip(), parts


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
    earlier_tasks: list[tuple[str, dict]] | None = None,
    part: str | None = None,
) -> str:
    """`sections` selects script sections to include in full and `statements`
    single ones by id ("Satz 3.1.5", see core.selection); with neither, the
    prompt carries no lecture notes at all. `proof_of` names statements whose
    proofs go in even while `include_proofs` is off. `earlier_tasks` are
    (label, task) of earlier sheets the task builds on - their statement only,
    see core.selection.earlier_tasks. `part` ("b") asks for that part of the
    task only, see ONE_PART; a label the task does not have is
    ignored."""
    from . import selection
    from .assignments import title_of
    from .toc import label as section_label

    section_titles = section_titles or {}
    sections = list(sections or ())
    context = selection.chosen(knowledge_entries, sections, statements,
                               include_algorithms)
    referenced, _ = resolve_exercises(task, exercises)
    if include_proofs is None:
        include_proofs = INCLUDE_PROOFS_BY_DEFAULT
    proof_of = set(proof_of or ())

    _, parts = task_parts(task, exercises)
    asked = next((p for p in parts if p["label"] == part), None) if part else None

    lines = []
    lines.append(instruction(
        part=asked["label"] if asked else None,
        definitions=any(kind_of(e) == "definition" for e in context),
        theorems=any(kind_of(e) == "result" for e in context),
        earlier=bool(earlier_tasks)))
    lines.append("")
    lines.append(f"# Course: {course_name}")
    if sheet_meta.get("discussion_date"):
        lines.append(f"Sheet {sheet_meta.get('sheet_number', '?')}, "
                      f"due: {sheet_meta['discussion_date']}")
    lines.append("")
    title = title_of(task)
    lines.append(f"# Task {task['number']}" + (f": {title}" if title else ""))
    lines.append(task["text"])
    lines.append("")
    # The sheet only points at the script; this is the task the model can
    # actually work on.
    for exercise in referenced:
        title = f": {exercise['title']}" if exercise.get("title") else ""
        lines.append(f"## Exercise {exercise['number']} from the lecture notes{title}")
        lines.append(exercise["text"])
        lines.append("")

    if earlier_tasks:
        lines.append("# Earlier exercises this task may build on")
        lines.append("(their statements only - their results may be used as given; "
                     "my solutions to them are not included)")
        lines.append("")
        for label, earlier in earlier_tasks:
            lines.append(f"## {label}")
            lines.append(task_query(earlier, exercises))
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
        lines.append(f"# From the {source_name(context)}: {'; '.join(where)}")
        if all(e.get("type") == "Slide" for e in context):
            contents = ("every slide of these sections" if sections
                        else "the slides chosen for this task")
        else:
            contents = ("every definition and theorem of these sections" if sections
                        else "the definitions and theorems chosen for this task")
        if sections and singles:
            contents += ", plus the single statements named"
        if any(e.get("type") in selection.ALGORITHM_TYPES for e in context):
            contents += ", algorithms included"
        with_proof = [entry_id(e) for e in context
                      if not include_proofs and e.get("proof") and entry_id(e) in proof_of]
        if with_proof:
            contents += ", proofs only for " + ", ".join(with_proof)
        elif not include_proofs and any(e.get("type") != "Slide" for e in context):
            # A slide has no separate proof to leave out: it shows what it shows.
            contents += ", proofs omitted"
        lines.append(f"({contents})")
        for e in context:
            lines.append("")
            lines.append(format_knowledge_entry(
                e, include_proof=proof_wanted(e, include_proofs, proof_of)))
        lines.append("")

    if asked:
        lines.append(f"# Asked now: part {asked['label']})")
        lines.append(asked["text"])
        lines.append("")

    if partial_solution and partial_solution.strip():
        lines.append("# My attempt so far")
        lines.append(partial_solution.strip())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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
