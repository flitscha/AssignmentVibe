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

## Schnellstart (Linux/Omarchy)

```bash
pip install --user -e .

# 1. Downloads-Ordner sortieren (Vorschau zuerst, siehe --help)
assignmentvibe organize ~/Downloads --apply --ingest

# ...oder manuell:
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
  organizer/        Downloads-Ordner klassifizieren & sortieren
  integrations/      Clipboard/Notify/Menu/OCR (je unabhaengig, mit Fallback-Ketten)
  paths.py, store.py, context.py, cli.py    App-Schicht / Orchestrierung
bin/              Bash-Einstiegspunkt (laeuft auch ohne pip install)
linux/            Waybar-Modul-Konfiguration
scripts/          Dev-Hilfsskripte (nicht Teil des installierten Pakets)
data/             eingelesene Beispiel-Skripte/-Blaetter (aus example_files/)
docs/             siehe oben
```

Details/Begründung: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
