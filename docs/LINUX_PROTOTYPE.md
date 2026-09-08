# AssignmentVibe – Linux/Omarchy-Prototyp

**Datum:** 2026-09-08
**Ziel:** Aus dem textbasierten POC ([POC_REPORT.md](POC_REPORT.md)) ein tatsächlich
lauffähiges Tool machen, das auf Omarchy Linux (Hyprland + Waybar + Walker) in
die Top-Bar integriert werden kann.

**Wie getestet:** Ich habe hier kein echtes Omarchy/Hyprland zur Verfügung
(Windows-Umgebung), aber Zugriff auf **WSL Ubuntu 22.04 – echtes Linux, echter
Python-Interpreter, echtes Dateisystem**. Alles, was *ohne* eine laufende
Wayland-Compositor-Session/Walker/root-Rechte testbar war, habe ich dort
tatsächlich ausgeführt (nicht nur gelesen/behauptet). Was nicht testbar war,
ist unten explizit als solches markiert – siehe Abschnitt 4.

---

## 1. Sprachwahl: Python (Engine/CLI) + Bash (OS-Kleber)

Kurz begründet, weil das explizit gefragt war:

- **Python fürs Kernstück** (PDF-Verarbeitung, Wissens-Extraktion, Prompt-Bau,
  State-Verwaltung): Das ist bereits erprobter Code aus dem POC (PyMuPDF-
  basiert), Neuschreiben in einer anderen Sprache hätte nur Risiko ohne
  Gegenwert gebracht. PyMuPDF, spätere OCR-Anbindung (Tesseract/pix2tex) –
  das Python-Ökosystem ist hier konkurrenzlos.
- **Bash für die Omarchy-Integration** (Waybar-Modul, Klick-Handler): Omarchy
  selbst ist komplett so gebaut – alle `bin/omarchy-*`-Helfer sind Bash-
  Skripte, die andere Programme aufrufen (siehe `omarchy-menu-select`,
  `omarchy-notification-send`, unten). Sich in diese Konvention einzufügen
  statt eine eigene zu erfinden, macht das Tool für jemanden, der Omarchy
  kennt, sofort lesbar und wartbar.
- **Kein Rust/Go-Rewrite für ein "leichtes" Bar-Modul:** Der Python-
  Interpreter-Start (~50-100ms) ist für ein Waybar-Modul mit 15s-Intervall
  irrelevant. Eine zweite Sprache hätte hier nur Komplexität ohne spürbaren
  Nutzen hinzugefügt.

Ergebnis: `assignmentvibe` ist ein pip-installierbares Python-Paket mit
CLI-Einstiegspunkt; ein `bin/assignmentvibe`-Bash-Wrapper lässt es aber auch
ganz ohne `pip install` direkt aus dem geklonten Repo laufen (Omarchy-typisch).

## 2. Was recherchiert wurde: Omarchys tatsächliche Konventionen

Statt zu raten, wie Omarchy strukturiert ist, habe ich das echte Repo
([basecamp/omarchy](https://github.com/basecamp/omarchy)) durchsucht:

- **Launcher:** Omarchy nutzt standardmäßig **Walker** (nicht rofi/wofi) als
  Launcher/dmenu-Ersatz.
- **Bar:** **Waybar**, pro Theme individuell gestylt.
- **Menü-Konvention:** `bin/omarchy-menu-select "<Prompt>" <Option>...` –
  pipet die Optionen an `omarchy-launch-walker --dmenu` und gibt die Auswahl
  auf stdout aus. Das ist exakt das Interface, das `assignmentvibe` als
  primären Picker anspricht (`assignmentvibe/menu.py`).
- **Notifications:** `bin/omarchy-notification-send <glyph> <headline>
  [beschreibung]` – ein Wrapper um `notify-send` mit Omarchy-Formatierung.
  Ebenfalls als erster Kanal in `assignmentvibe/notify.py` genutzt.
- **Web-Apps:** `bin/omarchy-launch-webapp <url>` öffnet eine URL als
  eigenständige Browser-App-Instanz – wird für "Chat öffnen" genutzt.

Alle drei (`omarchy-menu-select`, `omarchy-notification-send`,
`omarchy-launch-webapp`) werden nur **optional** genutzt (via `shutil.which`-
Check) – ist Omarchy nicht die Zielumgebung, greift eine Fallback-Kette
(rofi → wofi → fzf → Terminal-Eingabe, bzw. notify-send → stderr). Das Tool
ist also nicht *nur* auf Omarchy beschränkt, nutzt dessen Konventionen aber,
wo verfügbar, zuerst.

## 3. Architektur

```
assignmentvibe/            Python-Paket (die Anwendung)
  paths.py        XDG-Verzeichnisse (~/.local/share|state|cache/assignmentvibe)
  store.py         Skripte/Blaetter einlesen & verwalten (nutzt pipeline/)
  context.py        "woran arbeite ich gerade" (fuer Waybar-Tooltip)
  clipboard.py        Kopieren: wl-copy -> xclip -> xsel -> Datei-Fallback
  notify.py             Benachrichtigung: omarchy -> notify-send -> stderr
  menu.py                 Auswahl: omarchy-menu-select -> rofi -> wofi -> fzf -> stdin
  ocr.py                    Tesseract-Anbindung fuer Bild-Teilloesungen (Platzhalter)
  cli.py                      Kommandos, siehe unten

pipeline/                  die POC-Engine von vorher (PDF -> Text/Wissen/Prompt), unveraendert

bin/assignmentvibe          Bash-Shim: laeuft auch ohne pip install
linux/waybar-module.jsonc    fertiger Config-Ausschnitt fuer ~/.config/waybar/
```

### CLI-Kommandos

| Kommando | Zweck |
|---|---|
| `ingest-script <pdf> --course NAME` | Skript einlesen -> Wissensbasis |
| `ingest-sheet <pdf> --course NAME` | Aufgabenblatt einlesen |
| `courses` / `sheets` / `aufgaben <id>` | Eingelesenes auflisten |
| `context show\|clear` | aktueller Arbeits-Kontext |
| `build --sheet .. --aufgabe .. --use-case ..` | Prompt bauen, auf stdout |
| `copy ...` | Prompt bauen + in Zwischenablage kopieren |
| `pick` | **der volle interaktive Flow** (Blatt -> Aufgabe -> Use-Case -> optionale Teillösung -> kopieren -> Browser?) |
| `waybar-status` | JSON-Status fürs Waybar-Custom-Modul |
| `open-browser --provider claude\|chatgpt\|gemini` | Chat-Webseite öffnen |

`pick` ist das, was hinter dem Top-Bar-Klick hängen soll.

## 4. Testabdeckung – ehrlich aufgeschlüsselt

### ✅ Echt getestet (WSL Ubuntu 22.04, reales Linux)

| Was | Wie getestet | Ergebnis |
|---|---|---|
| Paket-Installation (`pip install -e .`) | frisches venv, `pyproject.toml` | funktioniert, identisch zu Windows |
| PDF-Pipeline auf echtem Linux | beide Skripte + alle 26 Blätter eingelesen | **identische Zahlen wie unter Windows** (284 / 131 Wissenseinheiten) – keine Plattform-Abweichung bei Encoding/Pfaden |
| `build` / `copy` / `context` / `waybar-status` | end-to-end via CLI | korrekte Prompts, Kontext wird persistiert, JSON valide |
| Clipboard-Fallback-Kette | kein `wl-copy`/`xclip`/`xsel` in WSL vorhanden | fällt sauber auf Datei zurück, klare Fehlermeldung statt Absturz |
| Notification-Fallback-Kette | kein `notify-send`/`omarchy-notification-send` vorhanden | fällt sauber auf stderr-Ausgabe zurück |
| `pick`-Flow, stdin-Fallback (kein Walker/rofi/wofi/fzf) | kompletter Durchlauf per Pipe simuliert | alle 5 Auswahlschritte funktionieren, Prompt wird gebaut & "kopiert" |
| `pick` ohne jede Eingabe (`< /dev/null`, simuliert Klick ohne Picker) | echter Test | **kein Hang**, sauberer Abbruch mit Benachrichtigung |
| Bash-Wrapper `bin/assignmentvibe` | beide Zweige (installiert / nicht installiert) einzeln getestet | beide funktionieren |
| OCR-Fehlerpfad (kein `tesseract`-Systempaket, kein root) | `pytesseract` installiert, `tesseract`-Binary fehlt absichtlich | klare Fehlermeldung statt Traceback |
| Bash-Syntax | `bash -n` | fehlerfrei |

### ⚠️ Nicht (voll) testbar in dieser Sandbox – Risiko-Einschätzung

| Was | Warum nicht testbar | Einschätzung |
|---|---|---|
| Tatsächliches Waybar-Rendering des Moduls | kein Wayland-Compositor in WSL | Das JSON-Format (`text`/`tooltip`/`class`) ist Standard-Waybar-Custom-Modul-Protokoll, keine Omarchy-Spezialität – sollte funktionieren. Nicht geprüft: ob Omarchy-Themes das `class`-Feld (`idle`/`active`) besonders stylen oder ob es eigenes CSS braucht. |
| `omarchy-menu-select` / Walker real aufrufen | Tool existiert nur auf echtem Omarchy | Interface aus dem Quellcode des Skripts abgelesen (Argumente = Optionen, stdout = Auswahl), nicht live verifiziert. Größtes Restrisiko: falls Walker bei leerer Eingabe/Abbruch einen anderen Exit-Code oder leere/andere Ausgabe liefert als angenommen. |
| `wl-copy`/`wl-paste` echt (Wayland-Zwischenablage) | kein Wayland-Display | Standardtool aus `wl-clipboard`, Interface ist stabil/dokumentiert – Fallback-Kette greift ohnehin, falls doch nicht vorhanden. |
| `notify-send` mit echtem Notification-Daemon | kein D-Bus-Session-Bus mit Daemon in WSL | Standard-Freedesktop-Spec, sollte auf jedem Omarchy-System mit `mako` (Omarchys Notification-Daemon) funktionieren. |
| Tesseract-OCR **Ergebnisqualität** (nicht nur Fehlerpfad) | kein root in WSL, `tesseract-ocr`-Systempaket nicht installierbar | Nur der Code-Pfad ist verifiziert (Bibliothek wird korrekt aufgerufen, Fehler sauber behandelt). Die tatsächliche Erkennungsqualität – erst recht bei **Handschrift** – ist komplett ungetestet, siehe unten. |
| Reales Anklicken in der Top-Bar (Hyprland-Bindings, Maus-Events) | keine grafische Session verfügbar | Nicht mein Testfeld hier – das ist reine Waybar-Mechanik, keine assignmentvibe-Logik. |

### ❌ Bewusst nicht gebaut/getestet

- **Handschrift-OCR:** wie besprochen, noch keine Beispieldateien. `ocr.py`
  ist ein austauschbarer Platzhalter (Tesseract für getippten/gedruckten
  Text) – für Handschrift (erst recht handschriftliche Mathe-Formeln)
  bräuchte es ein spezialisiertes Modell (z.B. pix2tex/LaTeX-OCR).
- **Automatisches Einfügen+Abschicken im Browser:** bewusst NICHT gebaut.
  Stattdessen: Prompt landet in der Zwischenablage, Browser öffnet sich
  parallel (`open-browser`) – der Nutzer drückt selbst Strg+V. Das ist
  simpler, robuster (keine fragile DOM-Automation, die bei jedem ChatGPT-UI-
  Update bricht) und umgeht das Login-Problem aus dem letzten POC komplett
  (siehe [POC_REPORT.md](POC_REPORT.md), Abschnitt 5).

## 5. Bekannte Risiken / Dinge, die beim ersten Test auf echtem Omarchy
   wahrscheinlich Probleme machen

1. **`omarchy-menu-select`-Verhalten bei Abbruch (Esc):** Ich gehe davon aus,
   dass leere stdout-Ausgabe = "abgebrochen" ist (mein Code behandelt das
   so), aber das ist aus dem Quellcode abgeleitet, nicht live verifiziert.
2. **Waybar `on-click` und fehlendes Terminal:** `pick` braucht *irgendeinen*
   Picker (Walker o.ä.) oder ein Terminal - auf echtem Omarchy ist Walker
   immer da, also unkritisch. Nur relevant, falls jemand das Tool auf einem
   Nicht-Omarchy-Hyprland-Setup ohne Launcher nutzen will.
3. **Emoji in Walker/dmenu-Fenstern:** Die Use-Case-Labels enthalten Emoji
   (💡🧠✓❓➡️📖🔍). Ob Walkers dmenu-Modus die sauber rendert, ist ungetestet -
   im schlimmsten Fall werden sie als Kästchen/Tofu angezeigt (kosmetisch,
   keine Funktionsstörung, da die Auswahl über den vollen String inkl. Emoji
   erfolgt).
4. **`context.py`-Race-Condition:** Kein Locking beim Schreiben von
   `context.json`. Bei sehr schnellen Doppelklicks auf das Waybar-Modul
   könnten zwei `pick`-Prozesse gleichzeitig laufen und sich überschreiben.
   Für ein Einzelnutzer-Tool mit menschlicher Klickgeschwindigkeit
   vernachlässigbar, aber nicht formal ausgeschlossen.
5. **Xournal++ nicht angebunden:** Die ursprüngliche Vision nennt
   "Xournal++AI" als Ziel (auch im Omarchy-Repo als mitgeliefertes Tool
   gefunden, `config/xournalpp`). Eine echte Anbindung (z.B. automatisch das
   aktuell offene `.xopp`-Dokument als Bild exportieren -> OCR) ist noch
   nicht gebaut - aktuell nur der manuelle "Bild angeben"-Weg in `pick`.

## 6. Installation auf einem echten Omarchy-System

```bash
git clone <repo-url> ~/assignmentvibe && cd ~/assignmentvibe
pip install --user -e .        # oder: pipx install .
# Optional fuer Bild-OCR-Teilloesungen:
sudo pacman -S tesseract tesseract-data-deu tesseract-data-eng
pip install --user pytesseract pillow

# Skripte/Blaetter einmalig einlesen:
assignmentvibe ingest-script ~/Downloads/Algebra.pdf --course "Algebra I"
assignmentvibe ingest-sheet  ~/Downloads/A03.pdf      --course "Algebra I"

# Waybar-Modul: Inhalt von linux/waybar-module.jsonc in
# ~/.config/waybar/config.jsonc uebernehmen (Modul-Namen in "modules-right"
# eintragen), dann Waybar neu laden.
```

## 7. Nächste Schritte (Reihenfolge nach Aufwand/Nutzen)

1. **Auf echtem Omarchy einmal live durchklicken** – das ist der mit Abstand
   wichtigste nächste Schritt, da er alle "⚠️"-Punkte aus Abschnitt 4 auf
   einen Schlag verifiziert oder falsifiziert.
2. Skript-eigene "Aufgaben"-Abschnitte parsen + Kontext-Auswahl auf
   Embeddings umstellen (siehe [POC_REPORT.md](POC_REPORT.md), Abschnitt 8 –
   unverändert gültig, hier nicht nochmal wiederholt).
3. Xournal++-Anbindung: aktives `.xopp`-Dokument erkennen/exportieren, statt
   manuell einen Bildpfad einzutippen.
4. Handschrift-Beispiele besorgen, `ocr.py` gegen pix2tex o.ä. testen.
