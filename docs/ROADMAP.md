# Roadmap

What's next, in order. Each item names the modules it touches (see
ARCHITECTURE.md) so it can be picked up without reading everything else.

Legend: 🟢 done · 🟡 partial · ⚪ not started

## Done

- 🟢 **Semester config + sorter + launcher.** `~/.config/assignmentvibe/uni.json`
  says which files belong to which course; `sort` files downloads into
  `~/Uni`, `launcher` puts them into Super+Space.
- 🟢 **Hub in the Omarchy shell bar.** One menu that shows where you are and
  changes one thing at a time, state remembered per course; follow-ups on
  right click.
- 🟢 **Chunking by the PDF's own outline** (`core/toc.py`), with a picker that
  offers chapters or sections depending on how big they are.
- 🟢 **Exercises from the script itself** (`core/exercises.py`). A sheet task
  "Lösen Sie Aufgabe (1.11) vom Skriptum" now carries the exercise's text in
  the prompt, and the automatic chapter suggestion stays inside the chapter the
  exercise belongs to. Every PS Optimierung task is such a reference; all 34
  resolve.
- 🟢 **Single proofs.** In the chapter picker, "Proofs: off/all" toggles all
  proofs in one click and the row below opens a list to pick single ones;
  single picks survive toggling "all" on and off again. The hub shows the
  state in its Chapters row. `build --proof-of "Satz 3.1.5"` on the command line.
- 🟢 **Old data is re-read automatically.** `FORMAT` in `core/knowledge.py`
  and `core/assignments.py`; "Read in new sheets" re-reads anything older.

## 1. ⚪ Review what the prompts say

The prompt is the product, and its wording has not been checked against real
use yet. Concretely:

- [ ] `SOLVE_INSTRUCTION` in `core/prompts.py` - is "solve it step by step,
      cite the notes" the right default?
- [ ] The ten `FOLLOW_UPS` - wording, which are missing, which are never used
- [ ] How the exercise block and the context block read to the model
      (`docs/example_prompts/optimierung_script_exercise.txt`)
- [ ] Whether the context header line ("every definition and theorem of these
      sections, proofs only for ...") helps or is noise

**Touches:** `core/prompts.py` only. Regenerate the examples afterwards with
`scripts/rebuild_example_prompts.py`.

## 2. ⚪ Strip page furniture from knowledge entries

A statement that runs over a page break carries the page number and running
header with it ("2", "1.1 Polyeder und Polytope"), and a section heading plus
its intro paragraph can end up appended to the statement before it.
`core/exercises.py` already strips headers per page (`_clean_page`); the same
idea belongs in `core/knowledge.py`. Bump `knowledge.FORMAT` so existing
courses get re-read.

**Touches:** `core/knowledge.py` (+ possibly moving `_clean_page` to a shared
spot). Check against the corpus with `scripts/check_corpus.py`.

## 3. ⚪ Matrices

Matrices lose their 2D structure during text extraction - every cell becomes
its own line. Exercise 2.9 (the simplex exercise) is nearly unreadable as a
result, and some knowledge entries are inflated by it.

- [ ] Detect matrix-like runs (many short numeric lines between brackets) and
      rebuild rows from the PDF's coordinates, or at least flag them

**Touches:** `core/pdf_text.py` and/or `core/knowledge.py`, `core/exercises.py`.

## 4. ⚪ Xournal++ integration

The partial solution is the missing third piece of the prompt (task + notes +
*what I have so far*). Today it can only come from the clipboard.

- [ ] Find the currently open `.xopp` document (window title via `hyprctl`)
- [ ] Export the current page (`xournalpp --create-pdf` / `--create-img`)
- [ ] Either OCR it (item 5) or attach the image - most chat UIs read
      handwriting from an image better than any local OCR would

**Touches:** a new `integrations/xournal.py`; `cli.py` for the hub row.

## 5. ⚪ Handwriting OCR

`integrations/ocr.py` wraps Tesseract, which does not read handwriting. Only
worth doing if item 4 shows that attaching an image is not good enough.

## 6. ⚪ Exercises in running text

`core/exercises.py` only looks inside sections the outline calls
"Aufgaben"/"Exercises". Scripts that scatter "Exercise 1.2." through the text
(spectral graph theory) or have no bookmarks at all get no exercises. Only
matters once a course's sheets actually reference them.

## 7. ⚪ Better automatic chapter suggestion

`core/selection.py` ranks sections by keyword overlap. It is a starting point
that is corrected by hand and then remembered, so this matters less than it
did - but embeddings would pick better where a task's vocabulary is thin.
