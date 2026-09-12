# Architecture

Internal reference doc - keeps us (human + Claude, across sessions) aligned
on how the code is structured and why, so changes don't silently drift out
of sync with the actual layout. Not user-facing.

## Module map

```
assignmentvibe/
  core/            Pure PDF/text processing. No filesystem STATE, no OS
                    integration, no side effects beyond writing the one
                    output file/JSON a function is asked to write. Fully
                    deterministic: same PDF in -> same data out.
    pdf_text.py       PDF -> normalized raw text (font-quirk fixes)
    font_styles.py     bold/italic header detection (depends on pdf_text)
    knowledge.py         raw text -> definitions/theorems/proofs (depends on font_styles)
    assignments.py        assignment-sheet PDF -> structured tasks (depends on pdf_text)
    prompts.py               use-case + task + knowledge -> prompt string (depends on nothing)

  organizer/       Classify & sort PDFs from a Downloads folder into a
                    library layout. Only depends on core.pdf_text (for a
                    light content peek). Deliberately NOT dependent on
                    store.py - "where do files belong" and "what's in the
                    knowledge base" are separate concerns.
    classify.py       guess doc type (script/sheet) + course for one PDF
    organize.py         turn a batch of classifications into a move plan

  integrations/    OS-level side-effecting utilities. Each one is
                    independent of the OTHERS (no imports between
                    clipboard/notify/menu/ocr) and of core/organizer.
                    Every one has a fallback chain ending in something that
                    always works (stderr print, a saved file, a stdin
                    prompt), so a missing external tool degrades instead of
                    crashing.
    clipboard.py      wl-copy/xclip/xsel -> file fallback
    notify.py           omarchy-notification-send/notify-send -> stderr
    menu.py               omarchy-menu-select/rofi/wofi/fzf -> stdin prompt
    ocr.py                 pytesseract wrapper (placeholder, see docs/LINUX_PROTOTYPE.md)

  paths.py         XDG directory locations. Depended on by store/context/
                    clipboard; depends on nothing itself.
  store.py         Ties core/ to the filesystem: ingest a script/sheet PDF,
                    persist it under paths.*, list/load what's there.
                    Depends on core/ and paths.
  context.py       "What am I working on right now" (for the Waybar
                    tooltip). Depends on paths only.
  cli.py           Orchestration layer - the only module allowed to depend
                    on everything else. This is intentional: cli.py is where
                    independent pieces get wired together, so no OTHER
                    module should need to import it.
```

## Dependency graph

```
core.pdf_text  <---  core.font_styles  <---  core.knowledge
core.pdf_text  <---  core.assignments
core.prompts   (standalone)

core.pdf_text  <---  organizer.classify  <---  organizer.organize

integrations.clipboard   (standalone)
integrations.notify      (standalone)
integrations.menu        (standalone)
integrations.ocr         (standalone)

paths  <---  context
paths  <---  store  <---  core.*

cli  --->  store, context, organizer.organize, core.prompts, integrations.*
```

Rule of thumb for where new code goes: if it's "PDF/text in, data out" with
no side effects, it's `core/`. If it decides "where does a file belong",
it's `organizer/`. If it talks to the OS/desktop (clipboard, notifications,
launchers, OCR), it's `integrations/`. Everything else is app-level
plumbing at the top of `assignmentvibe/`.

## Why this split (independence by design)

Each of `core/*`, `organizer/*`, and `integrations/*` can be developed and
unit-tested **in isolation**, without spinning up the rest of the app:

- `core.pdf_text.normalize("some string")` - no PDF, no filesystem needed.
- `core.prompts.build_prompt(...)` - pure function over plain dicts, no I/O.
- `organizer.classify.classify(some_pdf_path)` - only needs a PDF path, no
  ingested state, no store.
- `integrations.menu.pick(...)` - runs standalone from a terminal, no other
  integration module involved.

None of `core/*` know that `organizer/` or `integrations/` exist. `organizer/`
doesn't know `store.py` exists. This means: a change to how OCR works
(`integrations/ocr.py`) cannot break knowledge extraction (`core/knowledge.py`),
and vice versa - there is no import path between them. When picking up work
on one of these, you genuinely don't need to read the others first.

## Language policy

- **Code, comments, docstrings, error class names: English.** This applies
  throughout `assignmentvibe/`.
- **Literal German words that are matched against German source PDFs**
  (e.g. `TYPE_WORDS = ["Definition", "Satz", ...]` in `core/font_styles.py`,
  or the "Aufgabe"/"Besprechung" regexes in `core/assignments.py`) **stay
  German** - they're domain data, not code, and translating them would
  break the actual matching.
- **User-facing strings stay German**: CLI output (`print(...)`), desktop
  notification text, and the LLM prompt template in `core/prompts.py`
  (`USE_CASES[...]["instruction"]` and the `# Aufgabe`/`# Kontext` etc.
  section headers). This is a personal tool for a German-speaking user
  working through German course material - the product's own voice stays
  German even though the code that produces it is English.
- **JSON schema keys are English** (`tasks`, `sheet_number`,
  `discussion_date`, `script_references`, ...) even though the *values*
  behind them are German text extracted from the PDFs.
- Docs under `docs/` (this file included) can be either language - purely
  for keeping humans (and Claude, across sessions) aligned, not part of the
  product.
