# AssignmentVibe – Proof of Concept: Ergebnisse

**Datum:** 2026-09-08
**Getestet mit:** `Algebra.pdf`, `VO3_Optimierung.pdf` (Skripte) + 14 Algebra-Aufgabenblätter (`A01`–`A14`) + 12 Optimierung-Aufgabenblätter (`01`–`12-Blatt-PS-Optimierung`)

## Kurzfassung

Die Kernidee – Aufgabenblatt + Skript-Wissen automatisch zu einem gezielten LLM-Prompt
zusammenzubauen – **funktioniert bereits als lauffähiger Prototyp**, rein textbasiert
(ohne OCR, da noch keine handschriftlichen Beispiele vorliegen). Drei von vier
Pipeline-Schritten sind solide; der vierte (Kontext-Auswahl) ist ein einfacher
Platzhalter, der zeigt, dass das Prinzip funktioniert, aber noch keine Produktionsqualität hat.

| Baustein | Status | Kommentar |
|---|---|---|
| PDF → Text | ✅ funktioniert gut | PyMuPDF schlägt `pdftotext` und `pymupdf4llm` deutlich |
| Wissens-Extraktion (Sätze/Definitionen) | ✅ funktioniert nach 3 Bugfixes | Font-Stil-Verifikation war notwendig |
| Aufgaben-Parser | ✅ funktioniert für beide Blatt-Formate | Cross-Referenzen ins Skript werden erkannt, aber noch nicht aufgelöst |
| Prompt-Builder / Kontext-Auswahl | ⚠️ Prototyp, verbesserungswürdig | Keyword-Matching statt Embeddings – teils gut, teils daneben |
| Browser-Automation (Prompt einfügen & abschicken) | ⚠️ mechanisch machbar, aber... | braucht eingeloggte Session (z.B. via "Claude in Chrome"), nicht in Sandbox testbar |
| OCR Handschrift → LaTeX | ❌ nicht getestet | keine Beispieldateien vorhanden (siehe Roadmap) |

**Wichtigstes Learning:** Naive Regex-Extraktion auf PDF-Text ist überraschend
fehleranfällig – nicht wegen Mathe-Formeln, sondern wegen Font-Rendering-Details
(Ligaturen, Kerning, Zeilenumbruch-Zufall). Die Fixes dafür sind aber lokal und
robust, sobald man sie einmal kennt (siehe unten).

---

## 1. PDF → Text-Extraktion

Getestet: `pdftotext -layout` (poppler), `pymupdf4llm` (Markdown-Modus), PyMuPDF
`get_text("text")`.

| Tool | Satz-/Definitionsnummern | Formelinhalt | Ergebnis |
|---|---|---|---|
| `pdftotext -layout` | ❌ verstümmelt ("Deﬁnition . . ." statt "Definition 2.1.1.") | teilweise ok | verworfen |
| `pymupdf4llm` (Markdown) | ✅ sehr gut, inkl. Fett/Kursiv | ❌ **verschluckt ganze Formelzeilen** beim Markdown-Rebuild | verworfen |
| PyMuPDF `text`-Modus | ✅ gut | ✅ als lesbarer Unicode-Mathetext (kein LaTeX, aber LLM-verständlich) | **gewählt** |

→ Für getippte (nicht gescannte) Skripte reicht PyMuPDF allein aus. Ein schweres
Tool wie [MinerU](https://github.com/opendatalab/MinerU) (Torch, Layout-Modelle,
OCR) wurde **bewusst nicht** installiert/getestet – der Zusatznutzen gegenüber
PyMuPDF ist für getippte PDFs vermutlich gering, der Aufwand (GPU-nahe Pipeline,
großer Dependency-Baum) hoch. Relevant wird es erst bei gescannten Skripten oder
wenn wirklich sauberes LaTeX (statt Unicode-Mathetext) gebraucht wird.

### Drei Font-Bugs, die die Extraktion sonst kaputt gemacht hätten

1. **Ligaturen:** `Algebra.pdf` kodiert "fi" als ein einzelnes Unicode-Zeichen
   (`ﬁ`, U+FB01). Ohne Fix matcht kein Regex mehr auf "Definition". Fix:
   NFKC-Normalisierung ([extract_text.py](../pipeline/extract_text.py)).
2. **Zerrissene Umlaute:** In `VO3_Optimierung.pdf` wird das Trema als eigenes
   Glyph *vor* dem Buchstaben gezeichnet, teils mit Leerzeichen dazwischen
   (`L¨osungsmenge`, `F ̈ur`). 1436 betroffene Stellen im Optimierung-Skript.
   Fix: Regex, der Trema+Buchstabe wieder zusammenfügt und per NFC komponiert.
3. **Fehlendes Kerning:** In einem Abschnitt von `Algebra.pdf` (Garbentheorie,
   7.4) steht kein Leerzeichen zwischen Typwort und Nummer (`Definition7.4.4`
   statt `Definition 7.4.4`) – dadurch wurden mehrere echte Sätze unsichtbar
   für den Parser. Fix: Regex toleriert jetzt auch fehlenden Whitespace.

**Konsequenz für die Vision:** Jedes neue Skript-PDF kann eigene Font-Eigenheiten
mitbringen. Die Pipeline braucht eine Handvoll generischer Normalisierungsschritte
(jetzt vorhanden) plus im Zweifel eine kurze manuelle Stichprobe pro neuem Skript.

---

## 2. Wissens-Extraktion (Definitionen, Sätze, Lemmata, Beweise)

Beide Skripte nutzen konsequent eine amsthm-artige Nummerierung
`<Kapitel>.<Abschnitt>.<Index>` (z.B. "Satz 1.3.4") – daraus lassen sich Kapitel
und Abschnitt direkt ableiten, ganz ohne separate Überschriften-Erkennung.

### Ergebnis (nach allen Fixes)

| Skript | Definitionen | Sätze | Lemmata | Korollare | Beispiele | Bemerkungen | Sonstige | Gesamt |
|---|---|---|---|---|---|---|---|---|
| Algebra.pdf | 68 | 65 | 28 | 23 | 48 | 32 | 9 Proposition, 7 Konstruktion, 2 Algorithmus | **284** |
| VO3_Optimierung.pdf | 23 | 51 | 2 | 7 | 13 | 24 | 11 Algorithmus | **131** |

### Der zentrale Bug – und warum er wichtig ist

Ein naiver "Zeilenanfang + Regex"-Ansatz (`^Satz \d+\.\d+\.\d+`) erzeugt **False
Positives**: Ein Rückverweis wie "Satz 1.3.3" innerhalb eines *späteren* Beweises
kann durch zufälligen PDF-Zeilenumbruch am Zeilenanfang landen und wird dann als
neuer Wissensblock erkannt. Beobachtet: "Satz 1.3.3" tauchte so mitten in einem
KKT-Beweis in Kapitel 3 auf und riss einen Textblock von über 200 Zeilen mit sich
(Programmieraufgaben aus Kapitel 4 landeten im Textkörper von "Satz 1.3.3").

**Fix:** Verifikation jedes Regex-Treffers gegen die tatsächliche Schriftauszeichnung
im PDF ([bold_headers.py](../pipeline/bold_headers.py)). Echte Überschriften sind
im LaTeX-Theorem-Package immer besonders gesetzt (fett *oder* kursiv, je nach
Skript), Zitate im Fließtext dagegen immer regulär. Das ist ein zuverlässiges,
PDF-übergreifendes Signal – getestet an zwei Skripten mit komplett
unterschiedlichen Font-Setups (Computer Modern vs. Alegreya) und unterschiedlicher
Konvention (in Optimierung sind Bemerkung/Beispiel/Beweis kursiv, in Algebra
teils fett – die Erkennung ist bewusst stilagnostisch: „irgendeine Auszeichnung"
statt „genau Fettschrift").

Ein zweiter, verwandter Bug: Kapitel enden mit unmarkierten Abschnitten
("4.4 Aufgaben", "4.3 Literatur und Ausblick", ganze Literaturverzeichnis- und
Übungsaufgaben-Anhänge) ohne eigene Fett-Überschrift. Ohne Sonderbehandlung
hängt sich der komplette Rest des Kapitels an den letzten erkannten Satz. Fix:
diese Abschnittstitel werden als Blockgrenze (ohne eigenen Wissenseintrag)
behandelt.

### Bekannte verbleibende Einschränkung

Matrizen/Tabellen verlieren beim Textextrahieren ihre 2D-Struktur (jede Zelle
wird eine eigene Zeile) – ein `Beispiel`-Eintrag mit einer 4×7-Matrix wird dadurch
auf ~10.000 Zeichen aufgebläht, ohne dass der Inhalt falsch wäre. Für den
Prompt-Kontext ist das nicht ideal (viel Token-Verbrauch, wenig Informationsgehalt
in Textform), aber kein Extraktionsfehler. Ebenso: sehr generische
Subsection-Überschriften ohne Typwort (z.B. "4.1.2 Subgradientenverfahren")
werden nicht immer als Blockgrenze erkannt, wodurch gelegentlich ein Absatz
Fließtext an den vorherigen Eintrag "leckt".

---

## 3. Aufgaben-Parser

Getestet an zwei strukturell unterschiedlichen Blatt-Formaten:

- **Algebra** (`A01`–`A14`): "Aufgabe N" auf eigener Zeile, Unterpunkte als
  römische Ziffern `(i)`, `(ii)`, ...
- **PS Optimierung** (`01`–`12-Blatt-PS-Optimierung`): "Aufgabe N: Titel.",
  Unterpunkte als `a)`, `b)`, ...; **viele Aufgaben verweisen nur auf das
  Skriptum** ("Lösen Sie Aufgabe (2.9) vom Skriptum") statt den Text zu wiederholen.

Alle 26 Blätter wurden erfolgreich geparst (4–5 Aufgaben pro Blatt, korrekt
erkannt), inkl. Metadaten (Besprechungstermin, Blattnummer) und Unterpunkten.

**Wichtiger offener Punkt:** Die "vom Skriptum"-Referenzen (`references_skript`
im JSON) werden zwar *erkannt*, aber die eigentliche Aufgabenstellung liegt dann
im Skript selbst, in dessen unmarkierten "X.Y Aufgaben"-Abschnitten – die aktuell
nur als Blockgrenze behandelt, aber nicht extrahiert werden (siehe Abschnitt 2).
Für Blätter dieser Art fehlt dem Prompt-Builder aktuell der eigentliche
Aufgabentext (siehe Beispiel-Prompt-Diskussion unten). Das ist der wichtigste
konkrete Folgeschritt für die Pipeline.

---

## 4. Prompt-Builder (Use-Case + Aufgabe + Wissen → Prompt)

Alle sieben Use-Cases aus der Vision sind als Vorlage implementiert (💡 Hint,
🧠 Explain concept, ✓ Check solution, ❓ Why is this valid?, ➡️ What should I do
next?, 📖 Explain definition, 🔍 Find mistake). Die Kontext-Auswahl (welche
Sätze/Definitionen dem Prompt beigefügt werden) ist im Prototyp ein **simples
Keyword-Scoring** (Wortüberschneidung Aufgabentext ↔ Wissenseintrag) – bewusst
kein Embedding-Retrieval, um zuerst zu prüfen, ob das Grundprinzip überhaupt
brauchbare Treffer liefert.

### Guter Fall ([Beispiel](example_prompts/algebra_explain_concept.txt))

Aufgabe: *"Bestimmen Sie (bis auf Isomorphie) sämtliche Gruppen mit 1,2,3 und 4
Elementen."* → automatisch ausgewählt: Beispiel 2.1.3 (kleine abelsche Gruppen),
Bemerkung 2.1.14 (Untergruppenordnung / Satz von Lagrange), Korollar 2.4.12
(Klassifikation aller Gruppen der Ordnung 15 via Sylow – ein direkt analoges,
vorgerechnetes Beispiel). **Das ist tatsächlich der Kontext, den man einer KI
mitgeben möchte.**

### Guter Fall 2 ([Beispiel](example_prompts/optimierung_hint.txt))

Aufgabe zu Konvexität von Funktionen und Epigraphen → automatisch ausgewählt:
Definition 3.1.1 (Definition von "konvex"), Beispiel 3.1.2 (Beispiele konvexer
Funktionen). Direkt treffend.

### Schlechter Fall ([Beispiel](example_prompts/algebra_find_mistake.txt))

Aufgabe zum Chinesischen Restsatz (Kongruenzsysteme) → ausgewählt wurde u.a.
"Beispiel 1.2.1" über die Lösungsformel für quadratische/kubische Gleichungen –
inhaltlich **nicht** einschlägig, nur zufällige Wortüberschneidung ("Lösung",
"erhält", "gilt" u.ä.). Bei kurzen/generischen Aufgabentexten (insbesondere den
"vom Skriptum"-Verweisen ohne echten Aufgabentext, siehe Abschnitt 3) hat das
Keyword-Matching praktisch nichts, worauf es sich stützen kann.

**Fazit:** Das Prinzip trägt, die Umsetzung der Kontext-Auswahl ist der Teil mit
dem größten Verbesserungspotenzial. Naheliegender nächster Schritt: Embeddings
(z.B. über die Definitions-/Satz-Texte) statt Wortüberlappung, plus Fallback auf
manuelle Kapitel-/Abschnittsauswahl durch den Nutzer (wie in der ursprünglichen
Vision beschrieben) für Fälle mit wenig Kontext im Aufgabentext.

---

## 5. Browser-Automation (Prompt einfügen & abschicken)

In der Sandbox getestet: `claude.ai` ohne Login öffnen und die Seite inspizieren.
Ergebnis: Ohne authentifizierte Session landet man auf der Login-Seite – das war
zu erwarten und wurde **nicht** umgangen (Zugangsdaten einzugeben ist mir generell
nicht erlaubt, unabhängig vom Kontext).

**Erkenntnis für die Architektur:** Der "Prompt automatisch einfügen und abschicken"-
Schritt braucht die *echte, eingeloggte* Browser-Session des Nutzers – dafür ist
ein Tool wie "Claude in Chrome" (Automation im echten, bereits eingeloggten
Chrome-Profil des Nutzers) der richtige Ansatz, nicht eine frische Sandbox-Session.
Die reine DOM-Mechanik (Textfeld finden, Text einfügen, Button klicken) ist
technisch unproblematisch – das ist Standard-Browser-Automation und keine
offene Frage mehr. Das Abfangen der Antwort ist danach im Prinzip genauso machbar
(Seite auslesen), wurde aber mangels eingeloggter Session nicht live getestet.

---

## 6. Nicht getestet: OCR Handschrift → LaTeX

Wie besprochen liegen noch keine handschriftlichen Beispiele vor. Kurzer
Hinweis für später: Für Formel-OCR gibt es leichtgewichtige, spezialisierte
Modelle (z.B. `pix2tex`/LaTeX-OCR), die deutlich weniger Aufwand bedeuten als
eine volle MinerU-Pipeline und vermutlich der richtige erste Test sind, sobald
Beispielfotos/-scans vorliegen.

---

## 7. Projektstruktur (POC)

```
AssignmentVibe/
  example_files/          # Beispiel-PDFs (Skripte + Aufgabenblätter), unverändert
  pipeline/                # die vier Verarbeitungsschritte
    extract_text.py        # Schritt 1: PDF -> normalisierter Rohtext (+ Font-Fixes)
    bold_headers.py         # Hilfsmodul: echte Ueberschriften per Schriftstil erkennen
    extract_knowledge.py    # Schritt 2: Rohtext -> Definitionen/Saetze/... (JSON)
    extract_assignments.py  # Schritt 3: Aufgabenblatt -> strukturierte Aufgaben (JSON)
    build_prompt.py          # Schritt 4: Use-Case + Aufgabe + Wissen -> Prompt
    run_all.py               # fuehrt 1-3 fuer alle example_files/ aus
  data/
    _raw_text/              # Zwischenergebnis von Schritt 1 (Cache)
    knowledge/               # Ergebnis von Schritt 2, pro Skript
    assignments/              # Ergebnis von Schritt 3, pro Blatt
  docs/
    POC_REPORT.md            # dieser Bericht
    example_prompts/          # Beispiel-Outputs von Schritt 4 (gute + ein schlechter Fall)
  requirements.txt
```

Ausführen: `pip install -r requirements.txt && python pipeline/run_all.py`

---

## 8. Empfehlung / nächste Schritte

1. **Skript-eigene "Aufgaben"-Abschnitte parsen** und mit den Blatt-Referenzen
   ("vom Skriptum") verknüpfen – schließt die größte inhaltliche Lücke.
2. **Kontext-Auswahl auf Embeddings umstellen** statt Keyword-Overlap – größter
   Qualitätshebel für den Prompt-Builder.
3. **Handschriftliche Beispiele besorgen** und OCR (erst `pix2tex`, dann ggf. mehr)
   testen – einziger komplett ungetesteter Kernbaustein der Vision.
4. **Browser-Automation mit echter Session** (Claude in Chrome o.ä.) einmal live
   durchspielen, inkl. Antwort-Abfangen.
5. Tabellen/Matrizen in der Wissens-Extraktion entweder kürzen/zusammenfassen
   oder mit einem Hinweis versehen ("enthält Matrix, ggf. Bild statt Text
   verwenden"), damit sie den Prompt nicht unnötig aufblähen.
