"""
Which stretch of a handwritten notebook belongs to which task.

The notebooks (Xournal++, see integrations.xournal) are written the same way
every week: the statement of a task - or of one of its parts - pasted in as a
screenshot, the handwriting below it, the next statement below that. So the
pasted images are the landmarks: OCR says what text is on one, and that text
is matched against the sheet's tasks and their parts. A stretch runs from a
statement to the next statement of a DIFFERENT task or part; an image that
matches nothing (an excerpt of the lecture notes pasted in mid-solution) does
not end it, and neither does the second half of a statement that was pasted
in two pieces.

Matching is on character trigrams rather than words, because OCR of German
without German language data garbles exactly the words that matter
("durchfiihren", "Losung") while most of each word survives.

Pure: OCR text and task texts in, labels and page stretches out.
"""

import re

from .prompts import resolve_exercises, task_parts

# Below this an image is not a task statement (a lecture excerpt, a sketch).
MIN_SCORE = 0.35
# "(2.5) Direkte Umrechnung …" - an exercise of the notes, by its number; and
# "Aufgabe 3: …" - a task of the sheet. "Lösen Sie Aufgabe (1.11) vom
# Skriptum" names the exercise further in.
EXERCISE_NUMBER_RE = re.compile(r"\((\d+(?:\.\d+)+)\)")
SHEET_TASK_RE = re.compile(r"^\W{0,3}Aufgabe\s+(\d+)\b")
# A statement of the lecture notes pasted in for reference ("Satz 1.1.13.
# Es sei …", "Definition 3.1.8.") shares words with the task it is used in,
# sometimes enough to pass for its statement.
NOTES_STATEMENT_RE = re.compile(
    r"^\W{0,3}(Satz|Definition|Lemma|Korollar|Proposition|Bemerkung|Beispiel|"
    r"Algorithmus|Theorem|Corollary|Proof|Beweis|Remark)\b")
_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "s"})


def grams(text: str) -> set[str]:
    words = re.sub(r"[^a-z]+", " ", text.lower().translate(_FOLD)).split()
    joined = " ".join(w for w in words if len(w) > 1)
    return {joined[i:i + 3] for i in range(len(joined) - 2)}


def candidates(sheet: dict, exercises: list[dict]) -> list[dict]:
    """What a pasted image can show: every task as a whole, and each of its
    parts on its own. {"task", "part" ("" for the whole), "grams", "number"
    (the exercise it points at, "2.5", if any)}."""
    out = []
    for task in sheet.get("tasks", []):
        found, _ = resolve_exercises(task, exercises)
        text = "\n".join([task["text"]] + [e["text"] for e in found])
        number = found[0]["number"] if len(found) == 1 else None
        out.append({"task": task["number"], "part": "", "grams": grams(text), "number": number})
        for part in task_parts(task, exercises)[1]:
            out.append({"task": task["number"], "part": part["label"],
                        "grams": grams(part["text"]), "number": number})
    return out


def classify(ocr_text: str, cands: list[dict]) -> tuple[dict | None, float]:
    """The candidate an image shows, and how sure: the share of the image's
    trigrams found in the candidate, weighted by how much of the candidate
    the image covers - so a screenshot of part b) alone goes to part b), and
    one of the whole task to the task. An exercise number near the start
    ("(2.5) Direkte Umrechnung …") or "Aufgabe 3:" settles which task; an
    image that opens like a statement of the notes is none."""
    head = ocr_text.strip()
    seen = grams(head)
    if len(seen) < 15 or NOTES_STATEMENT_RE.match(head):
        return None, 0.0
    exercise = EXERCISE_NUMBER_RE.search(head[:120])
    sheet_task = SHEET_TASK_RE.match(head)
    best, best_score = None, 0.0
    for c in cands:
        if not c["grams"]:
            continue
        common = len(seen & c["grams"])
        contained = common / len(seen)
        covered = common / len(c["grams"])
        score = contained * (0.5 + 0.5 * covered)
        if exercise and c["number"] == exercise.group(1):
            score += 0.3
        if sheet_task and c["task"] == int(sheet_task.group(1)):
            score += 0.3
        # Of a task and its part, the part wins a tie only by what it covers.
        if (exercise or sheet_task) and c["part"]:
            score -= 0.05
        if score > best_score:
            best, best_score = c, score
    if best_score < MIN_SCORE:
        return None, best_score
    return best, best_score


def stretches(pages: list[dict], labels: dict[tuple[int, int], tuple[int, str] | None]
              ) -> list[dict]:
    """The notebook cut at its statements: [{"task", "part", "slices":
    [(page, top, bottom)]}] in the notebook's order, each slice trimmed to
    what is written in it. `labels` maps (page, image index) to the (task,
    part) that image shows, or None for an image that is no statement."""
    marks = sorted((p, pages[p]["images"][i]["box"][1], pages[p]["images"][i]["box"][3], key)
                   for (p, i), key in labels.items() if key is not None)
    # A statement pasted in several pieces is one mark: only a change of
    # task or part starts a new stretch. Each mark keeps where its first
    # piece begins (the end of the stretch before) and where its last one
    # ends (the start of its own).
    starts = []
    for p, top, bottom, key in marks:
        if starts and starts[-1]["key"] == key:
            starts[-1]["end"] = (p, bottom)
            continue
        starts.append({"key": key, "begin": (p, top), "end": (p, bottom)})

    out = []
    for n, mark in enumerate(starts):
        key = mark["key"]
        p0, y0 = mark["end"]
        if n + 1 < len(starts):
            p1, y1 = starts[n + 1]["begin"]
        else:
            p1, y1 = len(pages) - 1, pages[-1]["height"]
        slices = []
        for p in range(p0, p1 + 1):
            top = y0 if p == p0 else 0.0
            bottom = y1 if p == p1 else pages[p]["height"]
            written = [s["box"] for s in pages[p]["strokes"]
                       if s["box"][1] < bottom and s["box"][3] > top]
            if not written:
                continue
            slices.append((p, max(top, min(b[1] for b in written) - 6),
                           min(bottom, max(b[3] for b in written) + 6)))
        out.append({"task": key[0], "part": key[1], "slices": slices})
    return out


def work_on(stretches_: list[dict], task: int) -> list[dict]:
    """Everything written for a task - the whole of it and each of its parts
    - in the notebook's order. For a part the earlier parts' work belongs to
    "what I have so far" as much as its own: they are what it builds on."""
    return [s for s in stretches_ if s["task"] == task and s["slices"]]
