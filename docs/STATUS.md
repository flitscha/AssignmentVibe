# Status

What exists right now, as of 2026-09-28. Three separate questions per row,
because they're genuinely different things:

- **Implemented** - does the code exist and do what it's supposed to.
- **Tested by Claude** - did Claude run it and see it work, on the real
  material (your `~/Uni` PDFs, in an isolated data directory) or the example
  set in `example_files/`.
- **Tested by you** - have you used it on your Omarchy machine.

"Tested by Claude" for the panel means: on the real Omarchy desktop, opened
over IPC, driven with the keyboard (`wtype`) and checked by screenshot. Mouse
clicks could not be simulated there.

## Core pipeline (`assignmentvibe/core/`)

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| PDF -> raw text (`pdf_text.py`) | ✅ | ✅ ten-script corpus | ✅ (via ingest) |
| Font-style header detection (`font_styles.py`) | ✅ | ✅ | ✅ (via ingest) |
| Knowledge extraction: definitions/theorems/proofs (`knowledge.py`) | ✅ | ✅ corpus spot checks | ✅ Optimierung |
| Chunking by the PDF's own outline (`toc.py`) | ✅ | ✅ 100% of entries placed in all ten corpus scripts | ✅ Optimierung |
| **The script's own exercises (`exercises.py`)** | ✅ new | ✅ Optimierung: 64 exercises, all 34 sheet references resolve; Algebra 103, LinAlg 106 | ❌ |
| Task titles only where the sheet has a heading (`assignments.guess_title`) | ✅ new | ✅ all 850 tasks compared old vs new | ❌ |
| Assignment-sheet parsing (`assignments.py`): "Aufgabe N", "(N)", "N.", "N)"; ids per course | ✅ | ✅ all 186 maths sheets under ~/Uni, 16 courses, 850 tasks (2026-09-28) | ✅ Optimierung |
| Selection: chapters and/or single statements; nothing chosen, no context (`selection.py`) | ✅ changed | ✅ | ❌ (the keyword guess is gone) |
| **Jev picks statements and proofs** (`integrations/jev.py`), one yes/no per Satz and per proof | ✅ | ✅ 33 real sheet tasks in 9 courses (2026-09-28): 0.4-1.3s and $0.001-0.008 per pick; statements mostly on target, statements only since then, proofs judged from those; earlier sheets' tasks too (see ROADMAP 0) | ✅ (before the rework) |
| **Sheet plan**: effort per task, dependencies, and every task's context picked at once (`core/plan.py`, `jev.plan_sheet`, `cli._plan_sheet`); a task's selection set on switching to it, hand edits kept per task; the Jev row says when the context is Jev's | ✅ new | ✅ real Jev on 12 sheets; switching, hand edits and the task list with scripted answers | ❌ |
| "Open the sheet" in the task list (`pdf_viewer`, Firefox) | ✅ new | ⚠️ command checked, not launched | ❌ |
| Jev cost counter: last pick and total, with request counts; cost as OpenRouter reports it (else estimated, shown as "~$") | ✅ new | ✅ with faked responses | ❌ |
| The exact selection (each section and statement, "+ proof") in the bar tooltip and in the notification after a Jev pick | ✅ new | ✅ | ❌ |
| Prompt building (`prompts.py`) | ✅ | ✅ see `docs/example_prompts/` | ⚠️ content not yet reviewed |

Not covered by `exercises.py`: exercises scattered through running text
("Exercise 1.2." in the spectral graph theory notes, "Übung 12.47." in
Stochastik) and scripts without PDF bookmarks. Those yield no exercises
rather than wrong ones.

## The panel (`plugin/`, behind the bar click)

Replaced the Walker menu (`assignmentvibe pick`) on 2026-09-28. The logic
behind it moved from cli.py to `hub.py` unchanged; `api.py` serves it.

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| Bar pill: course and task, tooltip with the selection; right click follow-ups, middle click copy | ✅ new | ⚠️ pill and tooltip text seen; clicks not simulated | ❌ |
| Backend `assignmentvibe serve` (JSON lines), slow jobs on a thread, one at a time | ✅ new | ✅ scripted: every request, a second slow one turned down, stray prints kept off stdout | ❌ |
| Task tab: course, sheet and task side by side, task text, "In the prompt" card | ✅ new | ✅ keys ↑↓, real data in two courses | ❌ |
| Context tab: outline tree with tri-state boxes, statements with a proof box each, earlier sheets, search, "Chosen" view | ✅ new | ✅ keys, search, Esc; logic in `plugin/tests/model.test.js` | ❌ |
| Jev pick and busy banner from the panel | ✅ new | ✅ real Jev, task 2 of Optimierung sheet 1 | ❌ |
| "Plan with Jev" button | ✅ new | ⚠️ button seen, not pressed (costs a plan) | ❌ |
| Effort as a bar per task (length and colour, green to red; value in the tooltip); "3 builds on 1" beside "Task" | ✅ new | ✅ on a sheet planned by you | ❌ |
| "Lecture notes" button: opens the script at the page of the task's exercise | ✅ new | ⚠️ command checked for firefox/zathura/evince/okular, not launched | ❌ |
| Jev's progress and result where they land (card, task header), not in a banner | ✅ new | ⚠️ layout seen; not run again (costs a pick) | ❌ |
| Copy prompt (Enter / button / middle click), panel closes, notification | ✅ new | ✅ Enter; clipboard checked | ❌ |
| Preview of the prompt | ✅ new | ✅ | ❌ |
| Follow-ups tab | ✅ new | ⚠️ seen, copying not pressed | ❌ |
| Setup tab: read in new PDFs, config files, Jev costs, keys | ✅ new | ⚠️ seen; reading in scripted through the backend | ❌ |
| Changes from elsewhere (terminal) show up by themselves | ✅ new | ✅ course switched with `assignmentvibe api` | ❌ |
| IPC target `assignmentvibe` (toggle / open TAB / copy) for keybindings | ✅ new | ✅ | ❌ |
| State remembered per course (`context.py`) | ✅ | ✅ | ✅ |
| Least certain proofs dropped when Jev's pick is over `max_context_chars` | ✅ | ✅ faked Jev on real sizes (44 statements: 27 proofs -> 6 kept, 14.9k) | ❌ |
| `settings.json` (context length, Jev thresholds, algorithms default), validated | ✅ | ✅ | ❌ |
| Tasks that point into the script show the exercise's title and text | ✅ | ✅ | ❌ |
| Warning when a referenced exercise is not found | ✅ | ✅ | ❌ |
| "Read in new PDFs" (`store.ingest_missing`) | ✅ | ✅ | ✅ |
| Re-read of data made by an older extraction version (`FORMAT`) | ✅ | ✅ re-reads once, then never | ❌ |

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
| [../plugin/README.md](../plugin/README.md) | The panel: install, how it is built, keys |
