# The AssignmentVibe panel

A plugin for the Omarchy shell (Quickshell, Omarchy 4): a button in the bar
showing the current course and task (`󰷉 Optimierung A3`), and a panel under it
to choose task and context and copy the prompt.

It replaces the Walker menu the bar used to open (`assignmentvibe pick`), which
could only show one list of rows at a time: one button per row, nothing side
by side, a new window for every step.

## Install

The repository is the plugin: `manifest.json` and the QML sit at its root,
next to the Python backend (`assignmentvibe/`, `bin/`) the panel runs. Either

```bash
omarchy plugin add https://github.com/flitscha/AssignmentVibe.git --enable
```

which clones it into `~/.config/omarchy/plugins/felix.assignmentvibe`, or,
for a checkout you work on,

```bash
./install.sh
```

which links the checkout there instead, enables it, and puts it where the old
command widget (`"id": "assignmentvibe"` in `shell.json`) was - removing that
one, with a backup of `shell.json` beside it. Without the old widget it lands
in the right section; move it with
`omarchy bar move felix.assignmentvibe --before omarchy.tray`.

Either way it needs `python-pymupdf`. After changing QML in a linked
checkout, restart the shell (`omarchy restart shell`): the shell watches the
plugin folder with `inotifywait -r`, which does not follow the link.

## What it does on your machine

Omarchy plugins run unsandboxed, so, plainly:

- Runs `bin/assignmentvibe serve` (Python) for as long as the shell runs; the
  panel talks to it over stdin/stdout. Python's bytecode cache goes to
  `~/.cache/assignmentvibe/pycache`, not into the plugin folder (which the
  shell watches for changes).
- Reads and writes only its own files: `~/.config/assignmentvibe/` (uni.json,
  settings.json, openrouter.key), `~/.local/share/assignmentvibe/` (the
  knowledge base), `~/.local/state/assignmentvibe/` and
  `~/.cache/assignmentvibe/`. Reads the PDFs in the course folders uni.json
  names; `sort --apply` (terminal only) moves downloads there and puts
  replaced files in the trash.
- Network: only with an OpenRouter key in `openrouter.key`, and only when
  you press a Jev button - to `openrouter.ai`, with the task and the
  statements of your notes. Nothing else leaves the machine.
- Starts other programs when asked: the clipboard (`wl-copy`), your PDF viewer
  and browser, your editor for the config files, `tesseract` for
  `assignmentvibe work`.

## How it is built

```
manifest.json     the plugin's manifest (Omarchy wants it at the repo root)
BarWidget.qml     the pill: course and task, tooltip with what the prompt holds
Popup.qml         the panel: tabs, the banner for messages, the copy footer
Service.qml       runs `assignmentvibe serve` and talks JSON lines with it
Model.js          the context editor's logic - plain JS, tested under node
views/            Task, Context (+ ContextRow), Follow-ups, Setup, Preview
controls/         small pieces: chips, tri-state box, meter, banner, …
tests/            Model.js under node
install.sh        link a checkout into the plugin folder
```

The Python side does all the work (`assignmentvibe/api.py` on top of
`assignmentvibe/hub.py`); the panel only draws what it answers. The backend is
one process for the whole session, found in the same checkout
(`bin/assignmentvibe`), so panel and backend are always the same version.
Every answer carries the whole state, so a click is one round trip and one
redraw. Only the context editor ticks locally (Model.js) and saves a moment
after the last click - a round trip per tick would lag.

Jev and reading in PDFs take seconds; the backend runs them on a thread and
the panel greys out what would race with them. Progress shows where the
result will land - a spinner in the context card while Jev picks, beside
"Task" while it plans the sheet - and the result stays there: Jev's pick in
the card (with the proofs it left out for length), its effort estimate as a
bar per task. Only failures come as a message on top.

Effort is Jev's expected level over four (routine … hard), shown as a short
bar: longer and redder for more work. No number - a row already has the
task's and often the exercise's - and since length and colour say the same,
the colour never has to carry it alone. The tooltip has the value (of 10).

Changes made elsewhere - `assignmentvibe jev` in a terminal, say - show up by
themselves: the service watches `~/.local/state/assignmentvibe/context.json`.

## Mouse and keys

| | |
|---|---|
| left click | the panel |
| right click | the panel on the follow-ups |
| middle click | copy the prompt, no panel |

In the panel: `1`–`4` or Tab switch tabs, Enter copies the prompt, Esc
closes. Task tab: ↑↓ task, ←→ sheet, `O` open the sheet, `N` open the
lecture notes (at the page of the exercise the task points at), `A` ask Jev,
`E` edit the context, `P` preview. Context tab: ↑↓ move, →/← open/close, Space
tick, `P` tick the proof, `/` search.

For a keybinding, the service is an IPC target:

```bash
qs ipc -p "$OMARCHY_PATH/shell" call assignmentvibe toggle
qs ipc -p "$OMARCHY_PATH/shell" call assignmentvibe open context   # task, context, followups, setup
qs ipc -p "$OMARCHY_PATH/shell" call assignmentvibe copy
```

## Tests

```bash
node tests/model.test.js
```

The views themselves have no automatic tests; they were checked on a real
Omarchy desktop by screenshot, driven with IPC and `wtype`.
