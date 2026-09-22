# The widget in the Omarchy shell (Quickshell)

Omarchy 4 runs the bar on Quickshell, not Waybar. The widget is a
`"type": "command"` entry there: the bar execs a script and reads its output as
Waybar-style JSON — which is exactly what `assignmentvibe waybar-status` prints.

## Setup

1. Install the script:

   ```bash
   install -Dm755 linux/bar-script ~/.config/omarchy/bar/scripts/assignmentvibe
   ```

2. Add it to `bar.layout.right` in `~/.config/omarchy/shell.json`, at the front
   of the list so it sits leftmost inside the right block:

   ```json
   {
     "id": "assignmentvibe",
     "type": "command",
     "exec": "~/.config/omarchy/bar/scripts/assignmentvibe",
     "interval": 5,
     "onClick": "assignmentvibe pick",
     "onRightClick": "assignmentvibe followup",
     "onMiddleClick": "assignmentvibe context clear",
     "horizontalMargin": 6
   }
   ```

`shell.json` hot-reloads on save, no restart needed. If something does get
stuck: `omarchy restart shell`.

## Mouse buttons

| Button | What it does |
|--------|--------------|
| left   | the hub: pick a task, pick the chapters, copy the prompt |
| right  | straight to the follow-ups — you need those mid-chat, not on the way in |
| middle | forget the context |

## What it shows

`󰷉 Optimierung A4`, with sheet, task and the selected chapters in the tooltip.
The glyph is a Nerd Font codepoint (`nf-md-school`), not an emoji: the bar
renders in a monospace font where a colour emoji is a different size from
everything beside it. For a bar without a Nerd Font:

```bash
ASSIGNMENTVIBE_BAR_ICON=🧮 assignmentvibe waybar-status
```

The widget deliberately sets **no** `active` class. That paints it in the
theme's urgent colour, which has to keep meaning something is wrong — not that
a task is loaded, which is the resting state.

## Speed

The bar asks for the status every few seconds, so `waybar-status` has to be
cheap. It is around 100ms, almost all of it the Python interpreter starting;
pymupdf, which costs ~350ms on its own, is imported only on the paths that
actually open a PDF.

The menu itself is one `omarchy-menu-select` window per step, which is the only
thing that API offers — the menu closes and a new one is summoned between
steps. Keeping the work between them small is what keeps that from looking like
a stutter.

For Waybar itself, the module snippet is still in `linux/waybar-module.jsonc`.
