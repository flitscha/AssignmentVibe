# AssignmentVibe

AI assistance for your actual mathematical context.

**Idee:** Wenn der Laptop zugeklappt ist, ist es umständlich, ChatGPT & Co.
etwas zu fragen. AssignmentVibe soll verstehen, welche Aufgabe man gerade
bearbeitet, welchen Lösungsstand man hat (später per OCR aus der Handschrift),
und daraus automatisch einen präzisen, mit dem richtigen Skript-Kontext
angereicherten Prompt bauen – statt jedes Mal alles selbst abzutippen.
Gedacht für den Einsatz vom Linux-Desktop aus (Omarchy: Hyprland + Shell-Leiste),
per Klick in der Top-Bar.

## Dokumentation

- [docs/STATUS.md](docs/STATUS.md) – Checkliste: was ist implementiert, was
  ist von Claude getestet, was ist **von dir** getestet.
- [docs/ROADMAP.md](docs/ROADMAP.md) – priorisierte nächste Schritte,
  checklisten-artig, mit Abhängigkeiten zwischen den Modulen.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) – Modul-Landkarte,
  Abhängigkeitsgraph, Sprach-Policy (Code und Oberfläche englisch, das
  Kursmaterial im Prompt in seiner Originalsprache).
- [docs/POC_REPORT.md](docs/POC_REPORT.md) – der ursprüngliche Proof of
  Concept für die reine Text-Pipeline (PDF → Wissensbasis → Prompt).
- [docs/LINUX_PROTOTYPE.md](docs/LINUX_PROTOTYPE.md) – der erste
  installierbare Prototyp (historisch, noch mit Waybar statt Shell-Leiste).

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
| `skript` | eines **pro Muster** | ersetzt das alte Skript, **auch unter anderem Namen** (`VO3_…` → `VO4_…`) |
| `folien` | eines pro Kapitel | ersetzt nur bei **gleichem Namen**, sonst kommt es dazu |
| `blaetter` | viele | ersetzt nur bei **gleichem Namen**, sonst kommt es dazu |

Bei `skript` gilt: **ein Muster = ein Platz.** `"skript": ["VO*_Optimierung.pdf"]`
lässt `VO4_…` das alte `VO3_…` ablösen. Zwei Muster sind zwei Plätze – so
koexistieren `lecture-notes-modeling.pdf` und `lecture-notes-modeling-annotated.pdf`,
statt sich gegenseitig zu überschreiben.

„Gleicher Name" wird nach Abziehen des Browser-Zählers verglichen (Firefox
hängt `-1` an, Chrome ` (1)`): `Folien-1.pdf` gilt als neue Version von
`Folien.pdf` und landet unter dem sauberen Namen.

Das Abschneiden passiert aber **nur, wenn es den Namen ohne Zähler wirklich
gibt** – schon einsortiert oder ebenfalls in Downloads. Sonst wäre
`04x1-1.pdf` (ein echter Foliensatz) fälschlich ein Duplikat von `04x1.pdf`.
`_1` wird nie abgeschnitten, `Blatt_1.pdf` und `Blatt_2.pdf` sind
verschiedene Blätter.

Konkurrieren mehrere Downloads um denselben Namen (`Folien.pdf`, `Folien-1.pdf`,
`Folien-2.pdf`), gewinnt die **zuletzt heruntergeladene** (nach Änderungszeit),
der Rest kommt in den Papierkorb.

Ersetzte Dateien und überflüssige Downloads werden nie gelöscht, sondern via
`gio trash` in den Papierkorb gelegt.

### Unterordner

Standard ist flach: alles direkt in `<uni_root>/<semester>/<kurs>/`. Wenn ein
Kurs-Ordner von Hand unterteilt ist, sagt `unterordner` pro Kategorie, wohin:

```jsonc
"parallele_programmierung": {
  "name": "Parallele Programmierung",
  "folien": ["[0-9][0-9]_*.pdf", "part?_*.pdf"],
  "unterordner": { "folien": "vo" }
}
```

Gesucht wird darunter **rekursiv**. Liegt schon eine gleichnamige Datei
irgendwo tiefer (`vo/Kapitel 5 - …/SE Kapitel 5 Teil 1.pdf`), ersetzt der
Download genau sie – statt eine zweite Kopie eine Ebene höher anzulegen.

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

Sortierer und Launcher brauchen nur Python – die Wissensbasis (`ingest-*`) und
das Panel zusätzlich pymupdf:

```bash
ln -s "$PWD/bin/assignmentvibe" ~/.local/bin/assignmentvibe   # ohne Installation
sudo pacman -S python-pymupdf                                  # für die Wissensbasis

assignmentvibe config init     # Vorlage anlegen
assignmentvibe sort            # Vorschau

plugin/install.sh              # das Panel in die Omarchy-Leiste
```

## Das Panel

Ein Klick auf `󰷉 Optimierung A3` in der Leiste öffnet ein Panel mit vier Tabs
(Details und Einrichtung: [plugin/README.md](plugin/README.md)):

- **Task** – Kurs, Blatt und Aufgabe nebeneinander als Knöpfe, darunter der
  Text der gewählten Aufgabe und eine Karte „In the prompt“: was an Skript im
  Prompt landet, mit *Edit context*, *Let Jev pick* und *Clear*. Alles wird
  pro Kurs gemerkt – der übliche Fall ist ein einziger Klick auf **Copy
  prompt** (oder Enter). *Preview* zeigt den Prompt genau so, wie er kopiert
  wird.
- **Context** – die Gliederung des Skripts als Baum: ein Kästchen pro Kapitel
  und Abschnitt (✓ alle Sätze, – einige), aufklappbar bis zum einzelnen Satz,
  jeder mit eigenem Kästchen und daneben einem für seinen Beweis. Darunter die
  Aufgaben früherer Blätter. Suche über alle Sätze, „Chosen“ zeigt nur das
  Gewählte, der Balken unten die Länge gegen das Limit aus `settings.json`.
- **Follow-ups** – die Nachfragen („Just a hint“, „Only the next step“, …),
  ein Klick kopiert eine. Rechtsklick auf die Leiste öffnet direkt diesen Tab.
- **Setup** – neue PDFs einlesen, die Config-Dateien im Editor öffnen,
  Jev-Kosten, Tastenkürzel.

Mittelklick auf die Leiste kopiert den Prompt sofort, ohne Panel.

- **Aufgaben aus dem Skript:** Sagt ein Blatt nur „Lösen Sie Aufgabe (1.11)
  vom Skriptum“, landet der Text dieser Aufgabe aus dem Skript im Prompt.
- **Kein Kontext ohne Auswahl:** Ist nichts gewählt, enthält der Prompt kein
  Skript – es wird nichts geraten. Beweise sind standardmäßig aus (sie verraten
  oft die Lösung), Algorithmen an; den Schalter „Algorithms“ gibt es nur in
  Kursen, deren Skript welche hat.
- **Jev** (optional): Liegt ein OpenRouter-Key in
  `~/.config/assignmentvibe/openrouter.key` (`chmod 600`), erscheint „Let Jev
  pick“. Jev fragt pro Satz „braucht die Lösung das?“, pro Beweis „hilft genau
  dieser Beweis (gleiche Idee, gleiche Technik, oder die Aufgabe verweist
  darauf)?“ und pro Aufgabe früherer Blätter „baut die Aufgabe darauf auf?“,
  und ersetzt damit die Auswahl, die sich danach im Context-Tab weiter
  anpassen lässt. Jev sieht dabei nur die Sätze, nicht die Beweise (genauer
  und billiger, siehe ROADMAP). Frühere Aufgaben kommen nur als
  Aufgabenstellung in den Prompt. Wird die Auswahl länger als
  `max_context_chars`, fallen Beweise heraus, die unsichersten zuerst – Sätze
  bleiben immer drin. Kosten der letzten Auswahl und insgesamt stehen über der
  Karte und im Setup-Tab. Im Terminal: `assignmentvibe jev`, `jev --usage`.
- **Blatt planen:** „Plan with Jev“ neben den Blättern fragt Jev **einmal für
  das ganze Blatt**, was jede Aufgabe an Sätzen, Beweisen und früheren
  Aufgaben braucht, schätzt den Aufwand (▮▯▯▯ Routine bis ▮▮▮▮ schwer – mit
  diesem Kontext, denn wie schwer eine Aufgabe ist, hängt davon ab, was das
  Skript liefert) und erkennt, welche Aufgabe auf welcher aufbaut („after 2“
  in der Liste). Danach ist beim Wechsel auf eine Aufgabe ihr Kontext
  **automatisch gewählt**, ohne neue Jev-Anfrage; was man von Hand ändert,
  bleibt pro Aufgabe gemerkt, und die Karte sagt „Picked by Jev, changed by
  hand“. Eine Reihenfolge wird nicht vorgeschlagen. Im Terminal:
  `assignmentvibe plan [--show]`.
- **Config files** (Setup-Tab): `uni.json`, `settings.json`,
  `openrouter.key`, `jev_usage.json` – öffnet die Datei im Standard-Editor.
  Fehlt eine, wird sie mit erklärender Vorlage angelegt, der Key gleich mit
  `chmod 600`. `settings.json` kennt `max_context_chars` (15000),
  `jev_statement_threshold` und `jev_proof_threshold` (0.5; höher = Jev nimmt
  weniger) und `algorithms_by_default` (true).

Im Terminal gibt es dasselbe ohne Panel: `assignmentvibe build|copy
[--task N] [--sections 3.1] [--jev]`, `followup [N]`, `context show`.

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
  integrations/      Clipboard/Notify/OCR/Editor/Jev/Launcher (je unabhaengig, mit Fallback-Ketten)
  uniconfig.py      Semester-Config (~/.config/assignmentvibe/uni.json)
  settings.py       Verhalten (~/.config/assignmentvibe/settings.json)
  paths.py, store.py, context.py    App-Schicht
  hub.py            wo man steht und was es ändert - geteilt von Panel und CLI
  api.py            das Backend des Panels (`assignmentvibe serve`, JSON-Zeilen)
  cli.py            die Terminal-Befehle
plugin/           das Panel in der Omarchy-Leiste (QML, Quickshell)
bin/              assignmentvibe (Einstiegspunkt), uni-sort (Super+Shift+U)
scripts/          Dev-Hilfsskripte (nicht Teil des installierten Pakets)
data/             eingelesene Beispiel-Skripte/-Blaetter (aus example_files/)
docs/             siehe oben
```

Details/Begründung: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
