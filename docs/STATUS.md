# Status

What exists right now, as of 2026-09-25. Three separate questions per row,
because they're genuinely different things:

- **Implemented** - does the code exist and do what it's supposed to.
- **Tested by Claude** - did Claude run it and see it work, on the real
  material (your `~/Uni` PDFs, in an isolated data directory) or the example
  set in `example_files/`.
- **Tested by you** - have you used it on your Omarchy machine.

"Tested by Claude" never includes clicking through the real Walker menu or
looking at the bar - menu flows are tested by scripting the answers the
picker would give back.

## Core pipeline (`assignmentvibe/core/`)

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| PDF -> raw text (`pdf_text.py`) | ✅ | ✅ ten-script corpus | ✅ (via ingest) |
| Font-style header detection (`font_styles.py`) | ✅ | ✅ | ✅ (via ingest) |
| Knowledge extraction: definitions/theorems/proofs (`knowledge.py`) | ✅ | ✅ corpus spot checks | ✅ Optimierung |
| Chunking by the PDF's own outline (`toc.py`) | ✅ | ✅ 100% of entries placed in all ten corpus scripts | ✅ Optimierung |
| **The script's own exercises (`exercises.py`)** | ✅ new | ✅ Optimierung: 64 exercises, all 34 sheet references resolve; Algebra 103, LinAlg 106 | ❌ |
| Assignment-sheet parsing (`assignments.py`): "Aufgabe N", "(N)", "N.", "N)"; ids per course | ✅ | ✅ all 186 maths sheets under ~/Uni, 16 courses, 850 tasks (2026-09-28) | ✅ Optimierung |
| Selection: chapters and/or single statements; nothing chosen, no context (`selection.py`) | ✅ changed | ✅ | ❌ (the keyword guess is gone) |
| **Jev picks statements and proofs** (`integrations/jev.py`), one yes/no per Satz and per proof | ✅ | ✅ 33 real sheet tasks in 9 courses (2026-09-28): 0.4-1.3s and $0.001-0.008 per pick; statements mostly on target, statements only since then, proofs judged from those; earlier sheets' tasks too (see ROADMAP 0) | ✅ (before the rework) |
| Jev cost counter: last pick and total, with request counts; cost as OpenRouter reports it (else estimated, shown as "~$") | ✅ new | ✅ with faked responses | ❌ |
| The exact selection (each section and statement, "+ proof") in the bar tooltip and in the notification after a Jev pick | ✅ new | ✅ | ❌ |
| Prompt building (`prompts.py`) | ✅ | ✅ see `docs/example_prompts/` | ⚠️ content not yet reviewed |

Not covered by `exercises.py`: exercises scattered through running text
("Exercise 1.2." in the spectral graph theory notes, "Übung 12.47." in
Stochastik) and scripts without PDF bookmarks. Those yield no exercises
rather than wrong ones.

## The hub (`cli.py pick`, behind the bar click)

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| Hub: copy / follow-up / open chat, task/sheet/course/chapters rows | ✅ | ✅ scripted | ✅ |
| State remembered per course (`context.py`) | ✅ | ✅ | ✅ |
| **Context picker** (was "Chapters"): chapters tick all their statements (✓/◐), live sizes, "Clear all" | ✅ reworked | ✅ scripted | ❌ |
| **Statements list** in the context picker: every statement of the touched sections, Select all / Deselect all | ✅ new | ✅ scripted | ❌ |
| **Proofs list** (one row instead of toggle + list), Select all / Deselect all | ✅ reworked | ✅ scripted | ❌ |
| **"✨ Let Jev pick the context" row** in the hub, below Context, with last and total cost | ✅ | ✅ scripted, faked Jev | ✅ |
| Least certain proofs dropped when Jev's pick is over `max_context_chars` | ✅ new | ✅ faked Jev on real sizes (44 statements: 27 proofs -> 6 kept, 14.9k) | ❌ |
| `settings.json` (context length, Jev thresholds, algorithms default), validated | ✅ new | ✅ | ❌ |
| **"⚙ Config files …"** page in the hub, opens a file in the editor | ✅ new | ⚠️ menu scripted; the editor launch itself not run | ❌ |
| Algorithms on by default; the row hidden where a script has none | ✅ new | ✅ | ❌ |
| **Tasks that point into the script show the exercise's title** | ✅ new | ✅ | ❌ |
| Warning when a referenced exercise is not found | ✅ new | ✅ | ❌ |
| Follow-ups on right click (`followup`) | ✅ | ✅ | ✅ (wording not yet reviewed) |
| "Read in new sheets" (`store.ingest_missing`) | ✅ | ✅ | ✅ |
| Re-read of data made by an older extraction version (`FORMAT`) | ✅ new | ✅ re-reads once, then never | ❌ |

## Desktop integration (`integrations/`, `linux/`)

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| Omarchy shell bar widget (`linux/bar-script`, Quickshell) | ✅ | ⚠️ JSON only | ✅ |
| Menu via `omarchy-menu-select` (Walker) | ✅ | ⚠️ fallback path only | ✅ |
| Clipboard (`wl-copy`) + notifications | ✅ | ⚠️ fallback path only | ✅ |
| Semester config, sorter, Super+Space launcher entries | ✅ | ✅ | ✅ |
| OCR for typed/printed text (Tesseract) | ✅ placeholder | ⚠️ error path only | ❌ |
| OCR for **handwriting** | ❌ | - | - |
| Xournal++ integration | ❌ | - | - |

## Known weak spots

- **Page furniture leaks into knowledge entries.** A statement that runs over
  a page break carries the page number and running header along ("2", "1.1
  Polyeder und Polytope") - visible in
  `docs/example_prompts/optimierung_script_exercise.txt`. `exercises.py`
  already strips these for exercises; `knowledge.py` does not yet.
- **Matrices lose their shape.** Every cell becomes its own line; exercise 2.9
  (the simplex one) is barely readable as a result. See ROADMAP.md.
- **Modellierung** yields 0 knowledge entries - its notes do not use the
  numbered "Definition 1.2" style at all.

## Documentation

| Document | Purpose |
|---|---|
| [ROADMAP.md](ROADMAP.md) | What's next, in order |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module map, dependency graph, language policy |
| [example_prompts/](example_prompts/) | Generated prompts, regenerated by `scripts/rebuild_example_prompts.py` |
| [POC_REPORT.md](POC_REPORT.md) | The original text-pipeline proof of concept (historical) |
| [LINUX_PROTOTYPE.md](LINUX_PROTOTYPE.md) | The first installable prototype (historical - predates the hub and the shell bar) |
| [../linux/omarchy-shell-widget.md](../linux/omarchy-shell-widget.md) | Setting up the bar widget |
