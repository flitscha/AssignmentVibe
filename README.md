# AssignmentVibe

AI assistance for your actual mathematical context.

**Idee:** Wenn der Laptop zugeklappt ist, ist es umständlich, ChatGPT & Co.
etwas zu fragen. AssignmentVibe soll verstehen, welche Aufgabe man gerade
bearbeitet, welchen Lösungsstand man hat (später per OCR aus der Handschrift),
und daraus automatisch einen präzisen, mit dem richtigen Skript-Kontext
angereicherten Prompt bauen – statt jedes Mal alles selbst abzutippen.
Gedacht für den Einsatz vom Linux-Desktop aus (Omarchy: Hyprland + Shell-Leiste +
Walker), per Klick in der Top-Bar.

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

`pick` ist das Menü hinter dem Klick auf das Widget in der Omarchy-Leiste
(Einrichtung: [linux/omarchy-shell-widget.md](linux/omarchy-shell-widget.md)).
Es zeigt, wo man gerade steht, und ändert eine Sache nach der anderen –
alles unter dem Strich wird pro Kurs gemerkt:

```
Optimierung · task 1
▶  Copy prompt
💬 Copy a follow-up …
🌐 Open chat
───────────────────────────────
   Task      ▸  1  (1.11) Polytop der doppelt stochastischen Matrizen
   Sheet     ▸  3
   Course    ▸  Optimierung
   Chapters  ▸  1 Geometrie linearer Ungleichungen  (20, 7k) · proofs: Satz 1.1.13  (1)
───────────────────────────────
⟳  Read in new sheets
```

- **Aufgaben aus dem Skript:** Sagt ein Blatt nur „Lösen Sie Aufgabe (1.11)
  vom Skriptum“, landet der Text dieser Aufgabe aus dem Skript im Prompt.
- **Kein Kontext ohne Auswahl:** Ist kein Kapitel und kein Satz gewählt,
  enthält der Prompt kein Skript – es wird nichts mehr geraten.
- **Jev** (optional): Liegt ein OpenRouter-Key in
  `~/.config/assignmentvibe/openrouter.key` (`chmod 600`), erscheint im Hub
  unter „Chapters“ die Zeile „✨ Let Jev pick the notes“. Jev fragt pro Satz
  „braucht die Aufgabe das?“ und pro Beweis „hilft der Beweis?“ und ersetzt
  damit die Auswahl; in der Kapitelauswahl lassen sich die einzelnen Sätze
  unter „Single statements“ wieder abwählen. Dieselbe Zeile zeigt die Kosten
  der letzten Auswahl, die Gesamtkosten und die Zahl der Anfragen (Kosten so,
  wie OpenRouter sie meldet). Die genaue Liste der gewählten Sätze steht in
  der Benachrichtigung nach dem Wählen und im Tooltip des Widgets. Im
  Terminal: `assignmentvibe jev`, `jev --usage`.
- **Beweise:** standardmäßig aus (sie verraten oft die Lösung). In der
  Kapitelauswahl schaltet „Proofs: off/all“ alle mit einem Klick an und aus,
  die Zeile darunter öffnet die Liste, um einzelne Beweise der gewählten
  Kapitel auszuwählen. Sind einzelne gewählt, schaltet ein Klick auf die
  obere Zeile alle wieder ab.
- **Nachfragen** („Just a hint“, „Only the next step“, …) liegen auf der
  rechten Maustaste des Widgets, zum Einfügen mitten im Chat.

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
linux/            Widget für die Omarchy-Leiste (+ alte Waybar-Konfiguration)
scripts/          Dev-Hilfsskripte (nicht Teil des installierten Pakets)
data/             eingelesene Beispiel-Skripte/-Blaetter (aus example_files/)
docs/             siehe oben
```

Details/Begründung: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
