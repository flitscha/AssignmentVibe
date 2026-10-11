"""
My handwritten attempt as text for the prompt: StrokeReader's lines, one
reading picked per line, illegible ones left out, the parts labelled.

StrokeReader reads every line twice, with two models trained differently
(integrations.strokereader). Where they agree there is nothing to choose.
Where they differ, Jev - which knows the task and sees the lines around - says
how plausible each reading is, and the more plausible one goes in
(integrations.jev.judge_readings): 9.6% -> 9.3% of the characters wrong on
StrokeReader's held-out lines, significant; picking the better one every
time would give 8.7%. The same probability, with the model's own confidence,
is the quality gate: a line neither believes becomes "[unreadable]", so
letter salad never reaches the chat model as if I had written it, and a
doubtful one is marked "[unsure]". Without Jev (no key, no network) the main
model's reading goes in, gated by its confidence alone.

Pure: lines, stretches and probabilities in, text out.
"""

# How a line is trusted: Jev's probability that the reading is right, averaged
# with StrokeReader's own confidence for it - each alone ranks the lines by
# their errors about as well (Spearman -0.5), together better. Measured on
# StrokeReader's 1142 held-out lines (2026-10-11; docs/ROADMAP.md, item 5):
# below 0.30 a line is dropped as [unreadable] (2% of the lines, median 34%
# of their characters wrong, 3 nearly right ones lost); below 0.45 it is
# marked [unsure] (9%, 20% wrong); the rest is 5.7% wrong. Jev's probability
# alone would drop 14% of the lines at 0.3, half of them nearly right.
UNREADABLE_BELOW = 0.30
UNSURE_BELOW = 0.45
# Without Jev: the confidence alone, as strokereader.read marks [unsure].
UNSURE_CONFIDENCE = 0.5

HEADER = ("(Read by machine from my handwriting - single symbols may be misread; "
          "[unsure] marks lines that may be misread, [unreadable] lines that could not "
          "be read, [note] my side remarks in another colour.)")


def in_stretch(line: dict, stretch: dict) -> bool:
    centre = (line["box"][1] + line["box"][3]) / 2
    return any(p == line["page"] and top <= centre < bottom
               for p, top, bottom in stretch["slices"])


def up_to_part(stretches: list[dict], part: str | None) -> list[dict]:
    """The work that matters for asking part `part`: the task's own stretch
    and the parts up to it - the earlier parts are what it builds on, the later
    ones not written for it yet. All of it without a part."""
    if not part:
        return stretches
    return [s for s in stretches if not s["part"] or s["part"] <= part]


def choose(line: dict, judged: dict | None, unreadable_below: float = UNREADABLE_BELOW) -> dict:
    """{"text", "source" ("a"|"b"), "p" (Jev's), "score", "readable",
    "unsure"} for one line. `judged` is {"a": P, "b": P} from Jev ("b" only
    where the readings differ), or None without Jev: then the main model's
    reading, judged by its confidence alone."""
    if judged is None:
        score = line.get("conf_a", 1.0)
        return {"text": line["a"], "source": "a", "p": None, "score": score,
                "readable": score >= unreadable_below, "unsure": score < UNSURE_CONFIDENCE}
    pa, pb = judged.get("a", 0.0), judged.get("b")
    source = "b" if pb is not None and line["b"] != line["a"] and pb > pa else "a"
    p = pb if source == "b" else pa
    score = (p + line.get("conf_" + source, 1.0)) / 2
    return {"text": line[source], "source": source, "p": p, "score": score,
            "readable": score >= unreadable_below, "unsure": score < UNSURE_BELOW}


def compose(lines: list[dict], stretches: list[dict], judged: list[dict | None] | None,
            unreadable_below: float = UNREADABLE_BELOW, header: bool = True) -> tuple[str, dict]:
    """(The attempt as prompt text, counts). `lines` are StrokeReader's, in
    reading order; `stretches` the task's stretches of the notebook (each
    {"task", "part", "slices"}), which label the text "a)", "b)" where more
    than one part was written. `judged` is per line, or None without Jev."""
    picked = [choose(line, judged[i] if judged else None, unreadable_below)
              for i, line in enumerate(lines)]
    labelled = len(stretches) > 1
    out, counts = [], {"lines": len(lines), "from_b": 0, "unreadable": 0, "unsure": 0}
    # Each line under the first stretch that holds it: stretches of one page
    # can overlap where statements were pasted side by side.
    home = [next((k for k, s in enumerate(stretches) if in_stretch(line, s)), None)
            for line in lines]
    for k, stretch in enumerate(stretches):
        mine = [(line, pick) for line, pick, h in zip(lines, picked, home) if h == k]
        if not mine:
            continue
        if labelled:
            if out:
                out.append("")
            out.append(f"{stretch['part']})" if stretch["part"] else f"Task {stretch['task']}:")
        gap = 0
        for line, pick in mine:
            if not pick["readable"]:
                gap += 1
                counts["unreadable"] += 1
                continue
            if gap:
                out.append("[unreadable]" if gap == 1 else f"[unreadable: {gap} lines]")
                gap = 0
            counts["from_b"] += pick["source"] == "b"
            counts["unsure"] += pick["unsure"]
            prefix = ("[note] " if line.get("kind") == "note" else "") + \
                     ("[unsure] " if pick["unsure"] else "")
            out.append(prefix + pick["text"])
        if gap:
            out.append("[unreadable]" if gap == 1 else f"[unreadable: {gap} lines]")
    text = "\n".join(out).strip()
    if text and header:
        text = HEADER + "\n\n" + text
    return text, counts
