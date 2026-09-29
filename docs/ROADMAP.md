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
- 🟢 **A real panel instead of the Walker menu** (`plugin/`, 2026-09-28).
  Course, sheet and task side by side, the context as a tree with a box per
  chapter, statement and proof, search, a preview of the prompt, follow-ups
  as cards. Backed by `assignmentvibe serve` (`api.py` over `hub.py`).
- 🟢 **Chunking by the PDF's own outline** (`core/toc.py`), with a picker that
  offers chapters or sections depending on how big they are.
- 🟢 **Exercises from the script itself** (`core/exercises.py`). A sheet task
  "Lösen Sie Aufgabe (1.11) vom Skriptum" now carries the exercise's text in
  the prompt. Every PS Optimierung task is such a reference; all 34
  resolve.
- 🟢 **Single proofs.** In the context picker, "Proofs" opens the list of the
  chosen statements' proofs, with Select all / Deselect all on top. The hub
  shows the count in its Context row. `build --proof-of "Satz 3.1.5"` on the command line.
- 🟢 **One part at a time** (2026-09-29). A task with a), b), c) can be asked
  for part by part: the prompt keeps the whole task but asks for the chosen
  part only, earlier parts for reference. Chosen per task in the panel ("Ask
  for"), `build --part b` in the terminal.
- 🟢 **Old data is re-read automatically.** `FORMAT` in `core/knowledge.py`
  and `core/assignments.py`; "Read in new sheets" re-reads anything older.

## Next: read new PDFs in without a click

Today a new sheet or a changed script only becomes knowledge after "Read in
new PDFs" (Setup tab) or `store.ingest_missing` from somewhere. That is a step
you have to remember, right when you want to start on the new sheet. It should
happen by itself:

- **After filing.** `sort --apply` (Super+Shift+U, `bin/uni-sort`) just moved
  the files into the course folders - it knows exactly which ones are new and
  can read them in straight away, in the background.
- **When the panel's backend starts and when the panel opens** - a cheap check
  (mtimes of the course folders against what was read in) catches files that
  got there some other way, e.g. copied by hand or synced.
- Optionally a file watcher (inotify on the course folders) in `serve`, so a
  sheet dropped in while the panel is open shows up in it.

The panel then only has to say "Sheet 12 read in" once, beside the sheet
chips, and the Setup button stays for forcing a re-read. A script takes up to
a minute (pymupdf), so this must run on the backend's worker thread and never
block the panel.

## 0. 🟡 Jev picks statements and proofs

Nothing is chosen automatically any more - no selection, no context. With an
OpenRouter key in `~/.config/assignmentvibe/openrouter.key`, the panel's
"Let Jev pick" button asks Jev (TypeSafe's decision model) one
yes/no question per statement and one per proof, and makes the answer the
selection. Over `max_context_chars` the least certain proofs are dropped.

- [x] First real call works (2026-09-27)
- [x] Measured on 33 real sheet tasks, 9 courses (2026-09-28). At 0.5: median
      4 statements Jev itself wants, no empty pick, the right one on top where
      the task names it (Satz 1.26 at 0.89, 2. Isomorphiesatz at 0.82, the
      Chinese remainder theorem for Z/n x Z/m). But 62% of the proofs picked
      belong to statements Jev judged NOT needed, and each drags its statement
      in: median 7 statements and 3 proofs per pick, up to 15 and 12.
- [x] Proof rule (2026-09-28). Jev now sees the statements only, with a
      stricter proof question ("same idea or technique, or the task refers to
      the proof"), and proofs that only point elsewhere ("Übung.", "Aufgabe
      13.") are not asked about. Hand-judged on the 33 tasks: 46% of the
      picked proofs help, against 24% before; 39 proofs picked instead of 113;
      ~40% cheaper. Showing Jev the first 400 characters of each proof was in
      between (38%). What is lost: proofs whose technique fits while the
      statement looks unrelated (10 of 28 useful ones).
- [x] Earlier tasks: Jev is asked about every task of the course's earlier
      sheets; picked ones go into the prompt as task text only. Found the
      explicit references ("Blatt 7, Aufgabe 1 (c)", "Aufgabe 5) vom ersten
      Blatt") and picked nothing where there was nothing.
- [ ] "Beweisen Sie Satz X" still gets the proof of X (the notes' proof is the
      answer). Keep or leave out?
- [x] `usage.cost` arrives - the counter shows real dollars

**Touches:** `integrations/jev.py`, `core/selection.py`, `cli.py`.

- [x] A sheet's plan (2026-09-28): effort per task as a Jev "score" on four
      levels and "does task b builds on task a" per pair (core.plan). Asked
      with each task's own statements and earlier tasks as context: without
      it "Beweise Teil a) des Satzes 1.26" came out a few lines, with it a
      page. The question had to say that the result a task asks to prove may
      not be cited - otherwise Satz 4.21 of the Analysis 4 notes, which the
      task asks to prove, made it "routine" (0.23 -> 1.32). Only detected
      dependencies are shown, no suggested order.
- [x] The plan is the context pick for every task at once: going to a task
      sets its selection without asking Jev again, and a selection changed by
      hand is kept per task. ~$0.01 per sheet with a script.
- [x] Task titles (2026-09-28): only what reads like a heading - short, no
      formula, not opening like a task sentence ("Sei", "Zeigen Sie", "Let").
      Before, the first short sentence was taken: 500 of 850 tasks had a
      "title", most of them "Sei G eine Gruppe" or "1". Now 200, all real;
      headings on a line of their own ("Erwartungstreue") are found too. Read
      from the task text when shown, so no sheet has to be read in again.

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

## 4. 🟡 Xournal++ integration

The partial solution is the missing third piece of the prompt (task + notes +
*what I have so far*).

**Done (2026-09-29), from the terminal:** `assignmentvibe work [--sheet ID]
[--task N] [--list]` finds the sheet's notebook in the course folder (the
`.xopp` whose name ends in the sheet number), OCRs the task statements pasted
into it (Tesseract, cached), matches them to the sheet's tasks and parts
(`core/worklog.py`), and draws everything handwritten for a task into one PNG
(`integrations/xournal.py`, pycairo) - across page breaks, with "b)", "c)"
where each part begins. Checked on all nine Optimierung notebooks: every
pasted statement lands on its task or part; pasted excerpts of the lecture
notes ("Satz 1.1.13. …", "Theorem …") are recognised as none. ~0.1s once the
OCR is cached.

Open:
- [ ] How it reaches the chat. First try: "Copy my work" in the panel puts the
      PNG on the clipboard, to paste right after the prompt - the chat model
      reads this handwriting well, costs nothing, and cannot mistranscribe.
      If two pastes turn out to be one too many: transcribe the PNG with a
      vision model (OpenRouter) into "What I have so far".
- [ ] A thumbnail in the panel, so a wrong match is seen before pasting.
- [ ] Only the work up to the part asked for (today: the whole task).
- [ ] `tesseract-data-deu` would read the statements better (not needed so far).

## 5. ⚪ Handwriting OCR

`integrations/ocr.py` wraps Tesseract, which does not read handwriting. Only
worth doing if item 4 shows that attaching an image is not good enough - and
then as a vision model reading the PNG item 4 already draws, not local OCR.

## 6. ⚪ Exercises in running text

`core/exercises.py` only looks inside sections the outline calls
"Aufgaben"/"Exercises". Scripts that scatter "Exercise 1.2." through the text
(spectral graph theory) or have no bookmarks at all get no exercises. Only
matters once a course's sheets actually reference them.

## 7. 🟢 ~~Better automatic chapter suggestion~~

Replaced: the keyword guess is gone, and Jev (item 0) picks on request.
