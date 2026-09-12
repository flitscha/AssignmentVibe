# Roadmap

Prioritized checklist of what's next, ordered by impact/effort. Each item
notes its dependencies within the codebase (see ARCHITECTURE.md for the
module map) and whether it can be worked on independently of the others.

Legend: 🟢 done this session · 🟡 in progress/partial · ⚪ not started

## 1. 🟢 Downloads-folder organizer

The most important next step per the original project vision
("Download-organize: Skript-Downloads in richtige Ordner tun") - everything
downstream (ingesting, prompt-building) only becomes low-friction once PDFs
don't have to be pointed at by hand every time.

- [x] Classify a PDF as script vs. assignment sheet vs. unknown (filename +
      content-peek + page-count heuristics) - `organizer/classify.py`
- [x] Plan + apply a move/copy into a `<library>/<course>/{scripts,sheets}/`
      layout, dry-run by default - `organizer/organize.py`
- [x] Fold near-duplicate course-name guesses (e.g. a script's "Algebra" vs.
      a sheet's "Algebra 1") into one course folder
- [x] Optional auto-ingest right after organizing (`--ingest`)
- [ ] Recursive scanning of subfolders (currently top-level only)
- [ ] Try it against a REAL, messy Downloads folder (the example set is
      clean by construction - real downloads will have unrelated PDFs,
      duplicate re-downloads, inconsistent naming)

**Independent:** yes - only touches `organizer/` (+ a light dependency on
`core.pdf_text` for the content peek). Does not require touching
`core/knowledge.py`, `integrations/`, or `cli.py`'s other commands.

## 2. ⚪ Live-test on real Omarchy

Everything Wayland/Hyprland/Walker-specific was built against the *documented*
behavior of `omarchy-menu-select`/`omarchy-notification-send`/Waybar's custom
module protocol, not verified live (no compositor in this sandbox - see
docs/LINUX_PROTOTYPE.md, section 4). This is pure verification, not new
code - the highest-value/lowest-effort item on this list once you're at your
Omarchy machine.

- [ ] Waybar module actually renders + updates (`linux/waybar-module.jsonc`)
- [ ] `omarchy-menu-select` behaves as assumed on Esc/empty selection
- [ ] `wl-copy`/`notify-send` work as expected in that session
- [ ] Emoji in Walker's dmenu rendering (cosmetic risk only)

**Independent:** yes - doesn't block or get blocked by anything else here.

## 3. ⚪ Resolve in-script "Aufgaben" cross-references

Several assignment sheets (mostly PS Optimierung) just say "Lösen Sie
Aufgabe (2.9) vom Skriptum" instead of repeating the task text - the actual
task lives inside the script's own unlabeled "X.Y Aufgaben" section, which
`core/knowledge.py` currently only uses as a block *boundary*, without
extracting its content (see docs/POC_REPORT.md, section 3). Fixing this
closes the biggest remaining content gap in the prompt-builder.

- [ ] Extract numbered exercise items from a script's own "Aufgaben" sections
- [ ] Link `script_references` (already extracted in `core/assignments.py`)
      to that extracted content
- [ ] Feed the resolved task text into `core/prompts.py` instead of the bare
      "vom Skriptum" reference

**Depends on:** `core/knowledge.py` (extend it) + `core/assignments.py`
(consume the link) + `core/prompts.py` (use it). Independent of `organizer/`
and `integrations/`.

## 4. ⚪ Replace keyword-matching context selection with embeddings

`core/prompts.py`'s `select_context()` is a placeholder (word-overlap
scoring) - works well on some tasks, picks irrelevant entries on others (see
docs/POC_REPORT.md, section 4, for concrete good/bad examples).

- [ ] Embed knowledge entries + task text, rank by similarity instead of
      token overlap
- [ ] Keep the manual chapter/section-selection escape hatch from the
      original vision for cases with too little context to embed against

**Depends on:** `core/prompts.py` only. Independent of everything else.

## 5. ⚪ Xournal++ integration

Named explicitly in the original project vision ("Xournal++AI") and
confirmed to be part of Omarchy's own default toolset
(`config/xournalpp` in the Omarchy repo). Currently `pick`'s "partial
solution from image" path requires manually typing a file path.

- [ ] Detect/export the currently-open `.xopp` document
- [ ] Feed that export into `integrations/ocr.py`

**Depends on:** `integrations/ocr.py` + a new integration module. Independent
of `core/` and `organizer/`.

## 6. ⚪ Handwriting OCR

`integrations/ocr.py` currently wraps Tesseract, which is a placeholder for
typed/printed text only - explicitly not validated for handwriting (no
sample material yet, see docs/LINUX_PROTOTYPE.md).

- [ ] Get handwritten sample pages
- [ ] Evaluate pix2tex/LaTeX-OCR (or similar) against them
- [ ] Swap the backend in `integrations/ocr.py` if it's good enough

**Depends on:** `integrations/ocr.py` only.

## 7. ⚪ Table/matrix content in knowledge extraction

Matrices lose their 2D structure during text extraction (every cell becomes
its own line), inflating some knowledge entries to thousands of characters
of low-information content (see docs/POC_REPORT.md, section 2).

- [ ] Detect matrix-like blocks and either compress or flag them
- [ ] Re-measure how much this affects prompt token usage in practice

**Depends on:** `core/pdf_text.py` and/or `core/knowledge.py`.

---

## Changelog (what happened in the "documentation + architecture" session)

For context on why some of the above reads the way it does:

- Restructured `pipeline/` + the flat `assignmentvibe/*.py` integrations
  into `assignmentvibe/{core,organizer,integrations}/` for module
  independence (see ARCHITECTURE.md) - no logic changes, verified via
  identical extraction counts (284 + 131 knowledge entries, 26 sheets)
  before/after on both Windows and WSL Ubuntu.
- Translated all code comments/docstrings to English (kept literal German
  domain-matching strings, JSON *values*, and user-facing CLI/prompt text
  in German - see ARCHITECTURE.md's language policy).
- Renamed JSON schema keys to English (`aufgaben`->`tasks`,
  `blatt_nummer`->`sheet_number`, `besprechungstermin`->`discussion_date`,
  `references_skript`->`script_references`, `num_aufgaben`->`num_tasks`);
  the CLI's `--aufgabe`/`aufgaben` subcommand became `--task`/`tasks` to
  match.
- Built the downloads organizer (item 1 above) from scratch, including the
  classification heuristics and the move-planning/apply logic.
- **Found and fixed a real bug while testing organizer + `--ingest`
  together**: the auto-ingest step used a classification's raw
  `course_guess` instead of the *resolved* course (after fuzzy-folding a
  script's guess into its matching sheets' course, or vice versa). This
  silently split one course into two knowledge bases - one of them orphaned
  (a sheet's course pointing at a knowledge file that was never created).
  Fixed by having `organizer.organize.plan()` carry the resolved
  `course_slug`/`course_display_name` per file, and having `cli.py`'s
  `--ingest` use that instead of re-deriving it. Verified fixed: the
  Algebra script and all 14 Algebra sheets now converge on one course, and
  a prompt built for one of those sheets correctly retrieves knowledge
  context from the script.
