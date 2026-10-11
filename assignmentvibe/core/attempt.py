"""
My handwritten attempt as text for the prompt: StrokeReader's lines, exactly
as its model reads them, the parts labelled.

Nothing is judged, marked or left out: a line comes out as the model read it,
misread symbols and all - the instruction tells the chat model that the attempt
was read by machine (core.prompts.ATTEMPT_RULE). Lines in another colour than
the page's main one are left out: they are side remarks and simplifications
(green under a brace), not the attempt itself. Decoration (underlines, braces,
arrows) StrokeReader leaves out already.

Pure: lines and stretches in, text out.
"""


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


def kept(lines: list[dict]) -> list[dict]:
    """The lines that go into the prompt: those in the main colour."""
    return [line for line in lines if line.get("kind", "text") == "text"]


def compose(lines: list[dict], stretches: list[dict]) -> str:
    """The attempt as prompt text. `lines` are StrokeReader's, in reading
    order; `stretches` the task's stretches of the notebook (each {"task",
    "part", "slices"}), which label the text "a)", "b)" where more than one
    part was written."""
    lines = kept(lines)
    # Each line under the first stretch that holds it: stretches of one page
    # can overlap where statements were pasted side by side.
    home = [next((k for k, s in enumerate(stretches) if in_stretch(line, s)), None)
            for line in lines]
    labelled = len(stretches) > 1
    out = []
    for k, stretch in enumerate(stretches):
        mine = [line for line, h in zip(lines, home) if h == k]
        if not mine:
            continue
        if labelled:
            if out:
                out.append("")
            out.append(f"{stretch['part']})" if stretch["part"] else f"Task {stretch['task']}:")
        out += [line["text"] for line in mine]
    return "\n".join(out).strip()
