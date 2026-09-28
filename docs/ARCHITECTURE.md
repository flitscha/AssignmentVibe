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
    knowledge.py         raw text -> definitions/theorems/proofs (depends on font_styles,
                          toc, exercises); writes entries + outline + exercises
    toc.py                 the PDF's outline -> chapter/section tree, places entries in it
    exercises.py            the script's own exercises ("(1.1) ..." in "Aufgaben" sections)
    assignments.py        assignment-sheet PDF -> structured tasks + references
                          into the script ("Aufgabe (1.1) vom Skriptum")
    selection.py           which sections and single statements go into a prompt -
                            only what was chosen; also turns Jev's answers into a pick
    prompts.py               task + exercises + knowledge -> prompt string
                             (depends on selection, toc, exercises - all pure)

  organizer/       Classify & sort PDFs from a Downloads folder into a
                    library layout. Only depends on core.pdf_text (for a
                    light content peek). Deliberately NOT dependent on
                    store.py - "where do files belong" and "what's in the
                    knowledge base" are separate concerns.
    sort.py           the one in use: config-driven filing into ~/Uni
    classify.py       (older heuristic sorter) guess doc type + course for one PDF
    organize.py         (older heuristic sorter) batch of classifications -> move plan

  integrations/    OS-level side-effecting utilities. Each one is
                    independent of the OTHERS (no imports between
                    clipboard/notify/ocr/editor) and of core/organizer.
                    Every one has a fallback chain ending in something that
                    always works (stderr print, a saved file, a stdin
                    prompt), so a missing external tool degrades instead of
                    crashing.
    clipboard.py      wl-copy/xclip/xsel -> file fallback
    notify.py           omarchy-notification-send/notify-send -> stderr
    ocr.py                 pytesseract wrapper (placeholder, see docs/LINUX_PROTOTYPE.md)
    launcher.py             .desktop entries for Super+Space
    jev.py                   asks Jev (via OpenRouter) per statement and per proof
                              whether a task needs it; counts requests/tokens/cost.
                              No key or no network -> JevUnavailable, selection
                              stays as it was
    editor.py                omarchy-launch-config-editor / xdg-terminal-exec
                              $EDITOR -> False (caller shows the path)

  paths.py         XDG directory locations. Depended on by store/context/
                    clipboard; depends on nothing itself.
  store.py         Ties core/ to the filesystem: ingest a script/sheet PDF,
                    persist it under paths.*, list/load what's there.
                    Depends on core/ and paths.
  uniconfig.py     The semester config (~/.config/assignmentvibe/uni.json).
  settings.py      How the tool behaves (~/.config/assignmentvibe/settings.json):
                    context length, Jev thresholds, algorithms default.
  context.py       "What am I working on right now", and per course what was
                    last chosen there (sheet, task, chapters, proofs). Read by
                    the hub. Depends on paths only.
  hub.py           Orchestration: where you stand (course/sheet/task/context)
                    and everything that changes or acts on it - Jev picks,
                    sheet plans, copying the prompt, opening files. Talks to
                    the user only through hub.say (a notification, or a
                    message the panel shows). Shared by api.py and cli.py.
  api.py           The panel's backend: `assignmentvibe serve` answers JSON
                    lines on stdin/stdout, every answer with the whole state
                    the panel draws. Slow jobs (Jev, reading in) on a thread.
  cli.py           The terminal commands.

plugin/            The panel in the Omarchy bar - a Quickshell plugin (QML).
                    Draws what api.py answers; only the context editor's
                    ticking is local (plugin/Model.js, tested under node).
                    See plugin/README.md.
```

## Dependency graph

```
core.pdf_text  <---  core.font_styles  <---  core.knowledge  --->  core.toc, core.exercises
core.pdf_text  <---  core.assignments
core.prompts   --->  core.selection, core.toc, core.exercises   (all pure)

core.pdf_text  <---  organizer.classify  <---  organizer.organize

integrations.clipboard   (standalone)
integrations.notify      (standalone)
integrations.ocr         (standalone)
paths  <---  integrations.jev   (key file location)

paths  <---  context
paths  <---  store  <---  core.*

hub  --->  store, context, core.*, integrations.*
api  --->  hub          cli  --->  hub, store, organizer, integrations.launcher
plugin/ (QML)  --->  `assignmentvibe serve` (api.py), over a pipe
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
- **User-facing strings are English** (since 789e858): the panel,
  notifications, and the prompt's own instruction and headers in
  `core/prompts.py`. The material a prompt carries - task text, definitions,
  exercises - stays in whatever language the course is in; the instruction
  is the tool talking, the rest is quoted source.
- **JSON schema keys are English** (`tasks`, `sheet_number`,
  `discussion_date`, `script_references`, ...) even though the *values*
  behind them are German text extracted from the PDFs.
- Docs under `docs/` (this file included) can be either language - purely
  for keeping humans (and Claude, across sessions) aligned, not part of the
  product.
