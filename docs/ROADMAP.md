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
  the prompt. Every PS Optimierung task is such a reference; all 34
  resolve.
- 🟢 **Single proofs.** In the context picker, "Proofs" opens the list of the
  chosen statements' proofs, with Select all / Deselect all on top. The hub
  shows the count in its Context row. `build --proof-of "Satz 3.1.5"` on the command line.
- 🟢 **Old data is re-read automatically.** `FORMAT` in `core/knowledge.py`
  and `core/assignments.py`; "Read in new sheets" re-reads anything older.

## 0. 🟡 Jev picks statements and proofs

Nothing is chosen automatically any more - no selection, no context. With an
OpenRouter key in `~/.config/assignmentvibe/openrouter.key`, the hub's
"✨ Let Jev pick the context" row asks Jev (TypeSafe's decision model) one
yes/no question per statement and one per proof, and makes the answer the
selection. Over `max_context_chars` the least certain proofs are dropped.

- [x] First real call works (2026-09-27)
- [x] Measured on 33 real sheet tasks, 9 courses (2026-09-28). At 0.5: median
      4 statements Jev itself wants, no empty pick, the right one on top where
      the task names it (Satz 1.26 at 0.89, 2. Isomorphiesatz at 0.82, the
      Chinese remainder theorem for Z/n x Z/m). But 62% of the proofs picked
      belong to statements Jev judged NOT needed, and each drags its statement
      in: median 7 statements and 3 proofs per pick, up to 15 and 12.
- [ ] Decide the proof rule. Replayed offline on the same answers:
      proof >= 0.6 -> 5 statements / 2 proofs; proof only where the statement
      was picked too -> 4 / 1 (116 proofs down to 44). The second loses cases
      like "the p=1 case was done in the lecture" (statement 0.32, proof 0.76).
- [ ] "Beweisen Sie Satz X": Jev picks the proof of X itself (0.95 in
      maingeo2023) - the prompt then carries the answer. Wanted or not?
- [x] `usage.cost` arrives - the counter shows real dollars

**Touches:** `integrations/jev.py`, `core/selection.py`, `cli.py`.

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

## 7. 🟢 ~~Better automatic chapter suggestion~~

Replaced: the keyword guess is gone, and Jev (item 0) picks on request.
