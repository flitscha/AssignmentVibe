# Widget in der Omarchy-Shell (Quickshell)

Omarchy 4 fährt die Leiste über Quickshell, nicht mehr über Waybar. Das Widget
ist dort ein `"type": "command"`-Eintrag: die Leiste ruft ein Skript auf und
liest dessen Ausgabe als Waybar-JSON — also genau das, was
`assignmentvibe waybar-status` schon druckt.

## Einrichten

1. Skript ablegen und ausführbar machen:

   ```bash
   install -Dm755 linux/bar-script ~/.config/omarchy/bar/scripts/assignmentvibe
   ```

2. In `~/.config/omarchy/shell.json` unter `bar.layout.right` eintragen — an
   den Anfang der Liste, dann sitzt es im rechten Block ganz links:

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

`shell.json` lädt beim Speichern neu, ein Neustart ist nicht nötig. Falls doch
etwas hängt: `omarchy restart shell`.

## Maustasten

| Taste  | Wirkung |
|--------|---------|
| links  | Hub-Menü: Aufgabe wählen, Kapitel wählen, Prompt kopieren |
| rechts | direkt die Nachfragen — die braucht man mitten im Chat, nicht auf dem Hinweg |
| mitte  | Kontext vergessen |

## Anzeige

`󰷉 Optimierung A4`, im Tooltip Blatt, Aufgabe und die gewählten Kapitel. Das
Glyph ist ein Nerd-Font-Codepoint (`nf-md-school`), kein Emoji — die Leiste
rendert in einer Monospace-Schrift, in der ein Farb-Emoji eine andere Größe hat
als alles daneben. Für eine Leiste ohne Nerd Font:

```bash
ASSIGNMENTVIBE_BAR_ICON=🧮 assignmentvibe waybar-status
```

Das Widget setzt bewusst **keine** Klasse `active`. Die färbt es in der
Omarchy-Shell in der Urgent-Farbe des Themes, und die muss weiter bedeuten,
dass etwas nicht stimmt — nicht, dass eine Aufgabe geladen ist.

Für Waybar selbst liegt der Modul-Ausschnitt weiterhin in
`linux/waybar-module.jsonc`.
