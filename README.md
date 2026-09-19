# AssignmentVibe

AI assistance for your actual mathematical context.

**Idee:** Wenn der Laptop zugeklappt ist, ist es umständlich, ChatGPT & Co.
etwas zu fragen. AssignmentVibe soll verstehen, welche Aufgabe man gerade
bearbeitet, welchen Lösungsstand man hat (später per OCR aus der Handschrift),
und daraus automatisch einen präzisen, mit dem richtigen Skript-Kontext
angereicherten Prompt bauen – statt jedes Mal alles selbst abzutippen.
Gedacht für den Einsatz vom Linux-Desktop aus (Omarchy: Hyprland + Waybar +
Walker), per Klick in der Top-Bar.

## Dokumentation

- [docs/STATUS.md](docs/STATUS.md) – Checkliste: was ist implementiert, was
  ist von Claude getestet, was ist **von dir** getestet (Stand jetzt: nichts).
- [docs/ROADMAP.md](docs/ROADMAP.md) – priorisierte nächste Schritte,
  checklisten-artig, mit Abhängigkeiten zwischen den Modulen.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) – Modul-Landkarte,
  Abhängigkeitsgraph, Sprach-Policy (Code englisch, Doku/Produkt-Text
  deutsch – siehe dort für die genaue Abgrenzung).
- [docs/POC_REPORT.md](docs/POC_REPORT.md) – der ursprüngliche Proof of
  Concept für die reine Text-Pipeline (PDF → Wissensbasis → Prompt).
- [docs/LINUX_PROTOTYPE.md](docs/LINUX_PROTOTYPE.md) – der erste
  installierbare Prototyp: Omarchy-Recherche, Waybar-Integration, ehrliche
  Testabdeckung.

OCR für Handschrift ist noch nicht getestet (keine Beispieldateien), und
automatisches Einfügen+Abschicken im Browser wurde bewusst NICHT gebaut –
stattdessen landet der Prompt in der Zwischenablage und der Browser öffnet
sich daneben (robuster, kein Login-Automation-Problem).

## Semester einrichten (das Einzige, was du regelmäßig anfasst)

Einmal pro Semester `~/.config/assignmentvibe/uni.json` bearbeiten: welches
Semester gerade läuft, welche Kurse es gibt, und wie deren Dateien heißen.

```jsonc
{
  "active": "m1",
  "uni_root": "~/Uni",
  "downloads": "~/Downloads",
  "pdf_viewer": "firefox",
  "alte_skripte_im_launcher": true,

  "semesters": {
    "m1": {
      "optimierung": {
        "name": "Optimierung",
        "skript":   ["VO*_Optimierung*.pdf"],
        "folien":   ["*Folien*.pdf"],
        "blaetter": ["*-Blatt-PS-Optimierung.pdf"]
      }
    }
  }
}
```

Muster sind Glob-Muster (`*`, `?`, `[0-9]`), Groß-/Kleinschreibung egal.
Keys mit `_` davor sind Notizen und werden ignoriert (JSON kann keine
Kommentare).

**Die einzige Regel:** eine Datei wird einsortiert, wenn sie auf ein Muster
hier passt – sonst nicht. Ein Downloads-Ordner ist voll mit Dingen, die nichts
mit der Uni zu tun haben; alles davon bleibt unberührt liegen. Keine Heuristik,
kein Raten.

Die drei Kategorien entscheiden **nicht**, wohin die Datei kommt (alles landet
flach in `<uni_root>/<semester>/<kurs>/`, so wie deine bestehenden Ordner).
Sie sagen, was die Datei *ist* – und danach richtet sich, was beim erneuten
Download passiert:

| Kategorie | Anzahl | Beim Neu-Download |
|---|---|---|
| `skript` | genau eines | ersetzt das alte Skript, **auch unter anderem Namen** (`VO3_…` → `VO4_…`) |
| `folien` | eines pro Kapitel | ersetzt nur bei **gleichem Namen**, sonst kommt es dazu |
| `blaetter` | viele | ersetzt nur bei **gleichem Namen**, sonst kommt es dazu |

„Gleicher Name" wird nach Abziehen des Browser-Suffixes verglichen:
`Folien_Kapitel2(1).pdf` gilt als neue Version von `Folien_Kapitel2.pdf` und
landet unter dem sauberen Namen. Ein `-1`/`_1` am Ende wird bewusst **nicht**
so behandelt – `Blatt_1.pdf` und `Blatt_2.pdf` sind verschiedene Blätter.

Ersetzte Dateien und überflüssige Downloads werden nie gelöscht, sondern via
`gio trash` in den Papierkorb gelegt.

Im Launcher landen: das Skript, **jeder** Foliensatz einzeln (nach Kapitel
auswählbar), das **neueste** Blatt, und der Kurs-Ordner. PDFs öffnen mit
`pdf_viewer` (Standard Firefox), der Ordner mit dem Dateimanager.
Mit `alte_skripte_im_launcher` bleiben Skripten vergangener Semester
auffindbar – als „Analysis Skript (s4)". Deren Folien, Blätter und Ordner
nicht, sonst wird die Suche unbrauchbar.

```bash
assignmentvibe config show     # zeigt, was die Config gerade bedeutet
assignmentvibe sort            # Vorschau: was würde wohin
assignmentvibe sort --apply    # verschieben + Launcher-Einträge aktualisieren
assignmentvibe launcher        # nur die Super+Space-Einträge neu bauen
```

`Super+Shift+U` öffnet ein Terminal mit der Vorschau und fragt nach, bevor
etwas bewegt wird (`bin/uni-sort`).

Die erzeugten `.desktop`-Dateien heißen `assignmentvibe-*.desktop` und tragen
`X-AssignmentVibe=true`. Nur solche Dateien werden beim Neu-Synchronisieren
aufgeräumt – handgeschriebene Einträge bleiben unangetastet.

## Schnellstart (Linux/Omarchy)

Sortierer und Launcher brauchen nur Python – die Wissensbasis (`ingest-*`,
`pick`) zusätzlich pymupdf:

```bash
ln -s "$PWD/bin/assignmentvibe" ~/.local/bin/assignmentvibe   # ohne Installation
sudo pacman -S python-pymupdf                                  # nur für ingest/pick

assignmentvibe config init     # Vorlage anlegen
assignmentvibe sort            # Vorschau

# Wissensbasis füllen:
assignmentvibe ingest-script Algebra.pdf --course "Algebra I"
assignmentvibe ingest-sheet  A03.pdf     --course "Algebra I"

assignmentvibe pick
```

`pick` ist der interaktive Flow (Blatt → Aufgabe → Use-Case → optionale
Teillösung → Prompt in Zwischenablage → Browser öffnen) – das soll hinter
einem Klick auf das Waybar-Modul hängen, siehe
[linux/waybar-module.jsonc](linux/waybar-module.jsonc) und
[docs/LINUX_PROTOTYPE.md](docs/LINUX_PROTOTYPE.md).

Verfügbare Use-Cases: `hint`, `explain_concept`, `check_solution`, `why_valid`,
`next_step`, `explain_definition`, `find_mistake`.

## Nur die Verarbeitungs-Pipeline (plattformunabhängig)

```bash
pip install -r requirements.txt
python scripts/rebuild_example_data.py
```

Verarbeitet alle PDFs in `example_files/` und legt die Ergebnisse in `data/`
ab (Dev-Skript zum Regressionstesten der `core/`-Module).

## Projektstruktur

```
assignmentvibe/
  core/            PDF -> Text/Wissen/Aufgaben/Prompt (reine Engine, keine Seiteneffekte)
  organizer/        sort.py = Config-gesteuertes Einsortieren; organize.py = alte Heuristik
  integrations/      Clipboard/Notify/Menu/OCR (je unabhaengig, mit Fallback-Ketten)
  uniconfig.py      Semester-Config (~/.config/assignmentvibe/uni.json)
  paths.py, store.py, context.py, cli.py    App-Schicht / Orchestrierung
bin/              assignmentvibe (Einstiegspunkt), uni-sort (Super+Shift+U)
linux/            Waybar-Modul-Konfiguration
scripts/          Dev-Hilfsskripte (nicht Teil des installierten Pakets)
data/             eingelesene Beispiel-Skripte/-Blaetter (aus example_files/)
docs/             siehe oben
```

Details/Begründung: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
