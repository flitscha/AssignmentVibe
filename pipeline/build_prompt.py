"""
Schritt 4: Use-Case + Aufgabe + (simulierte) Teilloesung + Wissenskontext
-> fertiger LLM-Prompt.

Kontext-Auswahl (Prototyp): simples Keyword-Scoring zwischen Aufgabentext und
den Wissenseinheiten (Definition/Satz/...) - kein Embedding-Retrieval, aber
zeigt, dass automatische Kapitel/Satz-Auswahl grundsaetzlich funktioniert.
Fuer den echten Prototyp spaeter durch Embedding-Suche ersetzen.
"""

import json
import re
import sys
from pathlib import Path

USE_CASES = {
    "hint": {
        "emoji": "\U0001F4A1",
        "label": "Hint",
        "instruction": (
            "Gib mir einen kleinen Hinweis, wie ich an diese Aufgabe herangehen "
            "koennte. Verrate NICHT die Loesung oder den naechsten Rechenschritt "
            "direkt, sondern hilf mir, selbst auf die Idee zu kommen."
        ),
    },
    "explain_concept": {
        "emoji": "\U0001F9E0",
        "label": "Explain concept",
        "instruction": (
            "Erklaere mir das zugrunde liegende Konzept dieser Aufgabe allgemein "
            "verstaendlich, bevor ich die Aufgabe selbst loese."
        ),
    },
    "check_solution": {
        "emoji": "✓",
        "label": "Check solution",
        "instruction": (
            "Ueberpruefe meine Teilloesung unten auf Korrektheit. Sag mir klar, "
            "ob sie stimmt, und falls nicht, an welcher Stelle der Fehler liegt "
            "(ohne die Aufgabe komplett fuer mich zu loesen)."
        ),
    },
    "why_valid": {
        "emoji": "❓",
        "label": "Why is this valid?",
        "instruction": (
            "Ich verstehe nicht, warum der Schritt in meiner Teilloesung "
            "mathematisch gerechtfertigt ist. Erklaere mir, welcher Satz/welche "
            "Definition das rechtfertigt und warum."
        ),
    },
    "next_step": {
        "emoji": "➡️",
        "label": "What should I do next?",
        "instruction": (
            "Basierend auf meiner Teilloesung: was ist ein sinnvoller naechster "
            "Schritt? Gib mir nur den naechsten Schritt, nicht die ganze weitere "
            "Loesung."
        ),
    },
    "explain_definition": {
        "emoji": "\U0001F4D6",
        "label": "Explain definition",
        "instruction": (
            "Erklaere mir die unten angegebene(n) Definition(en)/Saetze aus dem "
            "Skriptum in eigenen, einfachen Worten mit einem kleinen Beispiel."
        ),
    },
    "find_mistake": {
        "emoji": "\U0001F50D",
        "label": "Find mistake",
        "instruction": (
            "In meiner Teilloesung unten ist (vermutlich) ein Fehler. Finde ihn "
            "und erklaere, warum es ein Fehler ist - ohne die Aufgabe komplett "
            "neu zu loesen."
        ),
    },
}

STOPWORDS = set(
    "der die das ein eine einer einem einen und oder ist sei seien sind man "
    "wir sie es zu von mit fuer auf im in an als dass wenn falls genau also "
    "nicht auch bzw etc oben unten sowie oft oder wie oben also nach vom "
    "zum zur bei aus dem den des"
    .split()
)


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def score_entry(aufgabe_tokens: set[str], entry: dict) -> int:
    entry_tokens = tokenize(entry["text"])
    return len(aufgabe_tokens & entry_tokens)


def select_context(aufgabe_text: str, knowledge_entries: list[dict], top_k: int = 3) -> list[dict]:
    aufgabe_tokens = tokenize(aufgabe_text)
    scored = [(score_entry(aufgabe_tokens, e), e) for e in knowledge_entries]
    scored = [t for t in scored if t[0] > 0]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [e for _, e in scored[:top_k]]


def format_knowledge_entry(e: dict) -> str:
    header = f"{e['type']} {e['number']}"
    if e.get("name"):
        header += f" ({e['name']})"
    out = f"{header}:\n{e['text']}"
    if e.get("proof"):
        out += f"\nBeweis: {e['proof']}"
    return out


def build_prompt(
    use_case: str,
    aufgabe: dict,
    blatt_meta: dict,
    knowledge_entries: list[dict],
    partial_solution: str | None = None,
    course_name: str = "",
) -> str:
    uc = USE_CASES[use_case]
    context = select_context(aufgabe["text"], knowledge_entries, top_k=3)

    lines = []
    lines.append(f"Use-Case: {uc['emoji']} {uc['label']}")
    lines.append("")
    lines.append(uc["instruction"])
    lines.append("")
    lines.append(f"# Kontext: {course_name}")
    if blatt_meta.get("besprechungstermin"):
        lines.append(f"Aufgabenblatt {blatt_meta.get('blatt_nummer', '?')}, "
                      f"Besprechung: {blatt_meta['besprechungstermin']}")
    lines.append("")
    lines.append(f"# Aufgabe {aufgabe['number']}"
                  + (f": {aufgabe['title']}" if aufgabe.get("title") else ""))
    lines.append(aufgabe["text"])
    lines.append("")

    if context:
        lines.append("# Relevante Definitionen/Saetze aus dem Skriptum")
        lines.append("(automatisch per Keyword-Ueberschneidung ausgewaehlt - bei Bedarf ignorieren)")
        for e in context:
            lines.append("")
            lines.append(format_knowledge_entry(e))
        lines.append("")

    lines.append("# Meine bisherige Teilloesung")
    lines.append(partial_solution.strip() if partial_solution else "(noch nichts probiert)")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    blatt_path = Path(sys.argv[1])
    aufgabe_num = int(sys.argv[2])
    use_case = sys.argv[3]
    knowledge_path = Path(sys.argv[4])
    course_name = sys.argv[5] if len(sys.argv) > 5 else ""
    partial_solution = sys.argv[6] if len(sys.argv) > 6 else None

    blatt = json.loads(blatt_path.read_text(encoding="utf-8"))
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))["entries"]
    aufgabe = next(a for a in blatt["aufgaben"] if a["number"] == aufgabe_num)

    prompt = build_prompt(use_case, aufgabe, blatt, knowledge, partial_solution, course_name)
    print(prompt)
