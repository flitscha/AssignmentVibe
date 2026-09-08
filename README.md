# AssignmentVibe

AI assistance for your actual mathematical context.

**Idee:** Wenn der Laptop zugeklappt ist, ist es umständlich, ChatGPT & Co.
etwas zu fragen. AssignmentVibe soll verstehen, welche Aufgabe man gerade
bearbeitet, welchen Lösungsstand man hat (später per OCR aus der Handschrift),
und daraus automatisch einen präzisen, mit dem richtigen Skript-Kontext
angereicherten Prompt bauen – statt jedes Mal alles selbst abzutippen.

## Status

Aktuell ein **Proof of Concept** für den textbasierten Teil der Pipeline
(PDF-Skript → Wissensbasis, Aufgabenblatt → strukturierte Aufgaben,
Use-Case + Aufgabe → fertiger Prompt). OCR für Handschrift und die
Browser-Automation zum automatischen Abschicken sind vorbereitet bzw.
mechanisch getestet, aber mangels Beispielmaterial bzw. eingeloggter Session
noch nicht vollständig durchgespielt.

**→ Ergebnisse, Bugs, Fixes und Empfehlungen: [docs/POC_REPORT.md](docs/POC_REPORT.md)**

## Schnellstart

```bash
pip install -r requirements.txt
python pipeline/run_all.py
```

Das verarbeitet alle PDFs in `example_files/` und legt die Ergebnisse in
`data/` ab (Wissensbasis pro Skript, strukturierte Aufgaben pro Blatt).

Einen fertigen Prompt bauen:

```bash
python pipeline/build_prompt.py data/assignments/07-Blatt-PS-Optimierung.json 3 hint data/knowledge/optimierung.json "PS Optimierung"
```

Verfügbare Use-Cases: `hint`, `explain_concept`, `check_solution`, `why_valid`,
`next_step`, `explain_definition`, `find_mistake`. Optional als letztes
Argument die eigene (bisherige) Teillösung mitgeben.

## Projektstruktur

Siehe [docs/POC_REPORT.md, Abschnitt 7](docs/POC_REPORT.md#7-projektstruktur-poc).
