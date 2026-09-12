# Status

Checklist of what exists right now. Three separate questions per row, because
they're genuinely different things:

- **Implemented** - does the code exist and do what it's supposed to.
- **Tested by Claude** - did *I* run it and see it work (in WSL Ubuntu 22.04
  for anything Linux-specific, or on Windows for the platform-independent
  core), during development.
- **Tested by you** - have *you* actually run this on your own machine /
  Omarchy setup. **As of 2026-09-12: nothing has been. That's the honest
  baseline this file starts from.**

"Tested by Claude" is real testing (not just "I read the code and it looks
right"), but it is not a substitute for you trying it - especially anything
touching Walker/Waybar/Hyprland, none of which exist in the sandbox this was
built in (see docs/LINUX_PROTOTYPE.md for the detailed breakdown of what
that means per feature).

## Core pipeline (`assignmentvibe/core/`)

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| PDF -> raw text (`pdf_text.py`) | ✅ | ✅ both scripts, both platforms | ❌ |
| Font-style header detection (`font_styles.py`) | ✅ | ✅ | ❌ |
| Knowledge extraction: definitions/theorems/proofs (`knowledge.py`) | ✅ | ✅ 284 + 131 entries, verified against manual spot-checks | ❌ |
| Assignment-sheet parsing (`assignments.py`) | ✅ | ✅ all 26 example sheets | ❌ |
| Prompt building (`prompts.py`) | ✅ | ✅ multiple use cases, see docs/POC_REPORT.md examples | ❌ |

## Organizer (`assignmentvibe/organizer/`) - NEW this session

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| Classification (filename + content + page-count heuristics) | ✅ | ✅ 28/28 example files correctly classified after two fix-forward iterations | ❌ |
| Move planning (dry run) | ✅ | ✅ | ❌ |
| Apply (copy/move to library layout) | ✅ | ✅ (copy mode; move mode implemented, not separately exercised) | ❌ |
| Auto-ingest after organizing (`--ingest`) | ✅ | ✅ (found + fixed a real bug: course-folding mismatch between file placement and ingestion, see ROADMAP.md changelog) | ❌ |
| Course-name fuzzy-folding across script/sheet guesses | ✅ | ✅ | ❌ |
| Recursive folder scanning | ❌ | - | - |
| Handling a Downloads folder with OTHER (non-course) PDFs mixed in | ⚠️ partial (falls to `_unsorted` on low confidence, not verified against real-world noisy folders) | ⚠️ only tested against clean example_files/ | ❌ |

## Linux/Omarchy integration (`assignmentvibe/integrations/`, `cli.py`)

| Component | Implemented | Tested by Claude | Tested by you |
|---|---|---|---|
| Clipboard fallback chain | ✅ | ✅ fallback path (no wl-copy/xclip in sandbox); real wl-copy/xclip NOT exercised | ❌ |
| Notification fallback chain | ✅ | ✅ fallback path only (no notify-send in sandbox) | ❌ |
| Menu/picker fallback chain | ✅ | ✅ stdin fallback only; Walker/rofi/wofi/fzf NOT exercised live | ❌ |
| `pick` interactive flow end-to-end | ✅ | ✅ via stdin, including a no-picker/no-tty abort test | ❌ |
| Waybar JSON status output | ✅ | ✅ JSON validity + content checked; actual Waybar rendering NOT checked (no compositor) | ❌ |
| Bash entry point (`bin/assignmentvibe`), installed vs. non-installed | ✅ | ✅ both code paths | ❌ |
| OCR for typed/printed text (Tesseract) | ✅ | ✅ error path only (no tesseract binary available, no root in sandbox); recognition quality UNTESTED | ❌ |
| OCR for **handwriting** | ❌ | - | ❌ (no sample material yet) |
| Xournal++ integration | ❌ | - | - |

## Documentation

| Document | Purpose |
|---|---|
| [POC_REPORT.md](POC_REPORT.md) | Original text-pipeline proof of concept: what works, bugs found+fixed, limitations |
| [LINUX_PROTOTYPE.md](LINUX_PROTOTYPE.md) | First installable CLI + Waybar module: Omarchy research, test coverage, known risks |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Current module map, dependency graph, language policy |
| [ROADMAP.md](ROADMAP.md) | Prioritized future work, with a changelog of what happened this session |
| STATUS.md (this file) | The checklist above |

Note: POC_REPORT.md and LINUX_PROTOTYPE.md predate the `core/`/`organizer/`/
`integrations/` restructuring in this session and still reference the old
`pipeline/` module paths in places - the *findings* in them (bugs, test
results, numbers) are all still accurate, only the file paths moved. See
ARCHITECTURE.md for where things actually live now.
