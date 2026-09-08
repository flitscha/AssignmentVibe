# AssignmentVibe

AI assistance for your actual mathematical context.

**Idee:** Wenn der Laptop zugeklappt ist, ist es umständlich, ChatGPT & Co.
etwas zu fragen. AssignmentVibe soll verstehen, welche Aufgabe man gerade
bearbeitet, welchen Lösungsstand man hat (später per OCR aus der Handschrift),
und daraus automatisch einen präzisen, mit dem richtigen Skript-Kontext
angereicherten Prompt bauen – statt jedes Mal alles selbst abzutippen.
Gedacht für den Einsatz vom Linux-Desktop aus (Omarchy: Hyprland + Waybar +
Walker), per Klick in der Top-Bar.

## Status

- [docs/POC_REPORT.md](docs/POC_REPORT.md) – der ursprüngliche Proof of
  Concept für die reine Text-Pipeline (PDF → Wissensbasis → Prompt): Ergebnisse,
  gefundene Bugs, Fixes, Grenzen.
- [docs/LINUX_PROTOTYPE.md](docs/LINUX_PROTOTYPE.md) – **der lauffähige
  Prototyp** darauf aufbauend: installierbares CLI-Tool (`assignmentvibe`),
  Waybar-Modul, Omarchy-Integration (Walker/Notifications), Sprachwahl-
  Begründung und eine ehrliche Aufschlüsselung, was wirklich auf echtem Linux
  getestet wurde und was (mangels Hyprland-Session in der Sandbox) noch auf
  einem echten Omarchy-Rechner verifiziert werden muss.

OCR für Handschrift ist noch nicht getestet (keine Beispieldateien), und
automatisches Einfügen+Abschicken im Browser wurde bewusst NICHT gebaut –
stattdessen landet der Prompt in der Zwischenablage und der Browser öffnet
sich daneben (robuster, kein Login-Automation-Problem).

## Schnellstart (Linux/Omarchy)

```bash
pip install --user -e .
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
python pipeline/run_all.py
```

Verarbeitet alle PDFs in `example_files/` und legt die Ergebnisse in `data/`
ab. Details: [docs/POC_REPORT.md, Abschnitt 7](docs/POC_REPORT.md#7-projektstruktur-poc).

## Projektstruktur

```
pipeline/        PDF -> Text/Wissen/Aufgaben/Prompt (die Engine, plattformunabhaengig)
assignmentvibe/   CLI, State-Verwaltung, Linux-Integration (Clipboard/Notify/Menu/OCR)
bin/              Bash-Einstiegspunkt (laeuft auch ohne pip install)
linux/            Waybar-Modul-Konfiguration
data/             eingelesene Beispiel-Skripte/-Blaetter (aus example_files/)
docs/             POC-Report + Linux-Prototyp-Report
```
