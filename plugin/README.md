# The AssignmentVibe panel

A plugin for the Omarchy shell (Quickshell, Omarchy 4): a button in the bar
showing the current course and task (`󰷉 Optimierung A3`), and a panel under it
to choose task and context and copy the prompt.

It replaces the Walker menu the bar used to open (`assignmentvibe pick`), which
could only show one list of rows at a time: one button per row, nothing side
by side, a new window for every step.

## Install

```bash
plugin/install.sh
```

links this folder to `~/.config/omarchy/plugins/felix.assignmentvibe`, enables
it, and puts it where the old command widget (`"id": "assignmentvibe"` in
`shell.json`) was - removing that one, with a backup of `shell.json` beside it.
Without the old widget it lands in the right section; move it with
`omarchy bar move felix.assignmentvibe --before omarchy.tray`.

After changing QML here, restart the shell (`omarchy restart shell`): the
plugin lives outside `~/.config`, and hot reload does not reliably pick up
changed files through the link.

## How it is built

```
BarWidget.qml     the pill: course and task, tooltip with what the prompt holds
Popup.qml         the panel: tabs, the banner for messages, the copy footer
Service.qml       runs `assignmentvibe serve` and talks JSON lines with it
Model.js          the context editor's logic - plain JS, tested under node
views/            Task, Context (+ ContextRow), Follow-ups, Setup, Preview
controls/         small pieces: chips, tri-state box, meter, banner, …
```

The Python side does all the work (`assignmentvibe/api.py` on top of
`assignmentvibe/hub.py`); the panel only draws what it answers. The backend is
one process for the whole session, found next to this folder
(`../bin/assignmentvibe`), so panel and backend are always the same version.
Every answer carries the whole state, so a click is one round trip and one
redraw. Only the context editor ticks locally (Model.js) and saves a moment
after the last click - a round trip per tick would lag.

Jev and reading in PDFs take seconds; the backend runs them on a thread and
the panel greys out what would race with them.

Changes made elsewhere - `assignmentvibe jev` in a terminal, say - show up by
themselves: the service watches `~/.local/state/assignmentvibe/context.json`.

## Mouse and keys

| | |
|---|---|
| left click | the panel |
| right click | the panel on the follow-ups |
| middle click | copy the prompt, no panel |

In the panel: `1`–`4` or Tab switch tabs, Enter copies the prompt, Esc
closes. Task tab: ↑↓ task, ←→ sheet, `O` open the sheet, `A` ask Jev, `E`
edit the context, `P` preview. Context tab: ↑↓ move, →/← open/close, Space
tick, `P` tick the proof, `/` search.

For a keybinding, the service is an IPC target:

```bash
qs ipc -p "$OMARCHY_PATH/shell" call assignmentvibe toggle
qs ipc -p "$OMARCHY_PATH/shell" call assignmentvibe open context   # task, context, followups, setup
qs ipc -p "$OMARCHY_PATH/shell" call assignmentvibe copy
```

## Tests

```bash
node plugin/tests/model.test.js
```

The views themselves have no automatic tests; they were checked on a real
Omarchy desktop by screenshot, driven with IPC and `wtype`.
