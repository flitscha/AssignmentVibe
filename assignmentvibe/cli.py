"""
`assignmentvibe` CLI - Einstiegspunkt fuer Terminal, Waybar-Modul und den
interaktiven "pick"-Flow (der, der letztlich hinter einem Top-Bar-Klick auf
Omarchy haengen soll).

Unterkommandos:
  ingest-script <pdf> --course NAME     Skript einlesen -> Wissensbasis
  ingest-sheet  <pdf> --course NAME     Aufgabenblatt einlesen
  courses                                Kurse auflisten
  sheets [--course SLUG]                 Aufgabenblaetter auflisten
  aufgaben <sheet_id>                    Aufgaben eines Blatts auflisten
  context show|clear                     aktueller Kontext
  build   ...                            Prompt bauen, auf stdout ausgeben
  copy    ...                            Prompt bauen + in Zwischenablage
  pick                                   interaktiver Flow (fuer Top-Bar-Klick)
  waybar-status                          JSON-Status fuers Waybar-Custom-Modul
  open-browser [--provider ...]          Chat-Webseite oeffnen
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.build_prompt import USE_CASES, build_prompt  # noqa: E402

from . import clipboard, context, menu, notify, ocr, store

USE_CASE_LABELS = {key: f"{v['emoji']} {v['label']}" for key, v in USE_CASES.items()}
LABEL_TO_KEY = {v: k for k, v in USE_CASE_LABELS.items()}


def _print(*args):
    print(*args)


def cmd_ingest_script(args):
    result = store.ingest_script(Path(args.pdf), args.course)
    _print(f"'{result['course']}' eingelesen: {result['entries']} Wissenseinheiten "
           f"-> {result['knowledge_path']}")


def cmd_ingest_sheet(args):
    result = store.ingest_sheet(Path(args.pdf), args.course)
    _print(f"'{result['sheet_id']}' ({result['course']}): {result['num_aufgaben']} Aufgaben eingelesen.")


def cmd_courses(args):
    courses = store.list_courses()
    if not courses:
        _print("Keine Kurse eingelesen. Mit 'ingest-script' starten.")
        return
    for slug, name in courses.items():
        _print(f"{slug}\t{name}")


def cmd_sheets(args):
    sheets = store.list_sheets(args.course)
    if not sheets:
        _print("Keine Aufgabenblaetter gefunden.")
        return
    for s in sheets:
        _print(f"{s['sheet_id']}\t{s.get('course_slug', '?')}\t"
               f"{s.get('num_aufgaben', '?')} Aufgaben\t"
               f"Blatt {s.get('blatt_nummer', '?')}")


def cmd_aufgaben(args):
    sheet = store.load_sheet(args.sheet_id)
    for a in sheet["aufgaben"]:
        title = f": {a['title']}" if a.get("title") else ""
        _print(f"{a['number']}{title}")


def cmd_context(args):
    if args.action == "show":
        ctx = context.get()
        _print(json.dumps(ctx, ensure_ascii=False, indent=1) if ctx else "(kein Kontext gesetzt)")
    elif args.action == "clear":
        context.clear()
        _print("Kontext geloescht.")


def _resolve_solution(args) -> str | None:
    if args.solution:
        return args.solution
    if args.solution_file:
        return Path(args.solution_file).read_text(encoding="utf-8")
    if args.solution_image:
        try:
            return ocr.image_to_text(args.solution_image)
        except ocr.OcrUnavailable as e:
            print(f"OCR fehlgeschlagen: {e}", file=sys.stderr)
            sys.exit(1)
    return None


def _build_from_args(args) -> str:
    sheet_id = args.sheet or context.get().get("sheet")
    if not sheet_id:
        print("Kein Aufgabenblatt angegeben (--sheet) und kein aktueller Kontext gesetzt.", file=sys.stderr)
        sys.exit(1)
    sheet = store.load_sheet(sheet_id)

    aufgabe_num = args.aufgabe or context.get().get("aufgabe")
    if not aufgabe_num:
        print("Keine Aufgabe angegeben (--aufgabe).", file=sys.stderr)
        sys.exit(1)
    aufgabe = next((a for a in sheet["aufgaben"] if a["number"] == int(aufgabe_num)), None)
    if aufgabe is None:
        print(f"Aufgabe {aufgabe_num} nicht in Blatt {sheet_id} gefunden.", file=sys.stderr)
        sys.exit(1)

    course_slug = sheet.get("course_slug")
    knowledge = store.load_knowledge(course_slug) if course_slug else []
    course_name = store.list_courses().get(course_slug, course_slug or "")

    use_case = args.use_case or context.get().get("use_case", "hint")
    if use_case not in USE_CASES:
        print(f"Unbekannter Use-Case '{use_case}'. Optionen: {', '.join(USE_CASES)}", file=sys.stderr)
        sys.exit(1)

    solution = _resolve_solution(args)

    context.set(sheet=sheet_id, aufgabe=int(aufgabe_num), use_case=use_case, course=course_slug)

    return build_prompt(use_case, aufgabe, sheet, knowledge, solution, course_name)


def cmd_build(args):
    sys.stdout.reconfigure(encoding="utf-8")
    print(_build_from_args(args))


def cmd_copy(args):
    prompt = _build_from_args(args)
    ok, method = clipboard.copy(prompt)
    if ok:
        notify.send("Prompt kopiert", f"{len(prompt)} Zeichen (via {method})", glyph="📋")
        _print(f"In Zwischenablage kopiert ({method}).")
    else:
        notify.send("Zwischenablage nicht verfuegbar", f"Prompt gespeichert: {method}", glyph="⚠️")
        _print(f"Kein Zwischenablage-Tool gefunden. Prompt gespeichert unter: {method}")


def cmd_waybar_status(args):
    ctx = context.get()
    if not ctx:
        payload = {"text": "🧮", "tooltip": "AssignmentVibe - kein aktiver Kontext", "class": "idle"}
    else:
        uc_label = USE_CASE_LABELS.get(ctx.get("use_case", ""), ctx.get("use_case", "?"))
        text = f"🧮 A{ctx.get('aufgabe', '?')}"
        tooltip = (f"Blatt: {ctx.get('sheet', '?')}\n"
                   f"Aufgabe: {ctx.get('aufgabe', '?')}\n"
                   f"Use-Case: {uc_label}")
        payload = {"text": text, "tooltip": tooltip, "class": "active"}
    print(json.dumps(payload, ensure_ascii=False))


def cmd_open_browser(args):
    import shutil
    import subprocess

    urls = {
        "claude": "https://claude.ai/new",
        "chatgpt": "https://chatgpt.com",
        "gemini": "https://gemini.google.com/app",
    }
    url = urls.get(args.provider, urls["claude"])

    if shutil.which("omarchy-launch-webapp"):
        subprocess.run(["omarchy-launch-webapp", url])
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", url])
    else:
        print(f"Kein Browser-Launcher gefunden. Oeffne manuell: {url}", file=sys.stderr)
        sys.exit(1)


def cmd_pick(args):
    """Der interaktive Flow: Blatt -> Aufgabe -> Use-Case -> (optional Teilloesung)
    -> Prompt bauen -> kopieren -> benachrichtigen -> optional Browser oeffnen.
    Genau das soll hinter dem Top-Bar-Klick haengen."""
    if not menu.any_picker_available():
        # Nur eine Vorab-Warnung, kein harter Abbruch: der stdin-Fallback
        # funktioniert auch ohne TTY (z.B. bei Tests per Pipe), solange
        # tatsaechlich Daten kommen - siehe menu.py.
        notify.send("Kein grafischer Picker gefunden",
                     "Weder Walker/rofi/wofi/fzf verfuegbar - falls kein "
                     "Terminal offen ist, passiert jetzt evtl. nichts.", glyph="⚠️")

    sheets = store.list_sheets()
    if not sheets:
        notify.send("Keine Aufgabenblaetter", "Erst 'assignmentvibe ingest-sheet' ausfuehren.", glyph="⚠️")
        sys.exit(1)

    courses = store.list_courses()
    sheet_labels = {
        f"{s['sheet_id']}  ({courses.get(s.get('course_slug'), '?')}, "
        f"{s.get('num_aufgaben', '?')} Aufgaben)": s
        for s in sheets
    }
    sheet_label = menu.pick("Aufgabenblatt", list(sheet_labels.keys()))
    if not sheet_label:
        notify.send("Abgebrochen", "Kein Aufgabenblatt ausgewaehlt.", glyph="🧮")
        return
    sheet = sheet_labels[sheet_label]

    aufgabe_labels = {
        f"Aufgabe {a['number']}" + (f": {a['title']}" if a.get("title") else ""): a["number"]
        for a in sheet["aufgaben"]
    }
    aufgabe_label = menu.pick("Aufgabe", list(aufgabe_labels.keys()))
    if not aufgabe_label:
        notify.send("Abgebrochen", "Keine Aufgabe ausgewaehlt.", glyph="🧮")
        return
    aufgabe_num = aufgabe_labels[aufgabe_label]

    use_case_label = menu.pick("Use-Case", list(USE_CASE_LABELS.values()))
    if not use_case_label:
        notify.send("Abgebrochen", "Kein Use-Case ausgewaehlt.", glyph="🧮")
        return
    use_case = LABEL_TO_KEY[use_case_label]

    solution_choice = menu.pick(
        "Teilloesung",
        ["Keine", "Aus Zwischenablage uebernehmen", "Aus Bild (OCR)"],
    )
    solution = None
    if solution_choice == "Aus Zwischenablage uebernehmen":
        solution = _read_clipboard_text()
    elif solution_choice == "Aus Bild (OCR)":
        img_path = menu.pick("Bildpfad eingeben (dann Enter)", [""])
        if img_path:
            try:
                solution = ocr.image_to_text(img_path)
            except ocr.OcrUnavailable as e:
                notify.send("OCR fehlgeschlagen", str(e), glyph="⚠️")

    class _Args:
        pass

    fake_args = _Args()
    fake_args.sheet = sheet["sheet_id"]
    fake_args.aufgabe = aufgabe_num
    fake_args.use_case = use_case
    fake_args.solution = solution
    fake_args.solution_file = None
    fake_args.solution_image = None

    prompt = _build_from_args(fake_args)
    ok, method = clipboard.copy(prompt)
    if ok:
        notify.send(f"Aufgabe {aufgabe_num} - {USE_CASE_LABELS[use_case]}",
                     "Prompt in Zwischenablage kopiert.", glyph="📋")
    else:
        notify.send("Prompt erstellt", f"Zwischenablage nicht verfuegbar, gespeichert: {method}", glyph="⚠️")

    open_choice = menu.pick("Chat oeffnen?", ["Ja - claude.ai", "Ja - chatgpt.com", "Nein"])
    if open_choice and open_choice.startswith("Ja"):
        provider = "claude" if "claude" in open_choice else "chatgpt"
        args.provider = provider
        cmd_open_browser(args)


def _read_clipboard_text() -> str | None:
    import shutil
    import subprocess

    for cmd in (["wl-paste"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard"]):
        if shutil.which(cmd[0]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                continue
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="assignmentvibe")
    sub = p.add_subparsers(dest="command", required=True)

    p_is = sub.add_parser("ingest-script", help="Skript-PDF -> Wissensbasis")
    p_is.add_argument("pdf")
    p_is.add_argument("--course", required=True)
    p_is.set_defaults(func=cmd_ingest_script)

    p_ish = sub.add_parser("ingest-sheet", help="Aufgabenblatt-PDF einlesen")
    p_ish.add_argument("pdf")
    p_ish.add_argument("--course", required=True)
    p_ish.set_defaults(func=cmd_ingest_sheet)

    p_courses = sub.add_parser("courses", help="Kurse auflisten")
    p_courses.set_defaults(func=cmd_courses)

    p_sheets = sub.add_parser("sheets", help="Aufgabenblaetter auflisten")
    p_sheets.add_argument("--course", default=None, help="Kurs-Slug filtern")
    p_sheets.set_defaults(func=cmd_sheets)

    p_auf = sub.add_parser("aufgaben", help="Aufgaben eines Blatts auflisten")
    p_auf.add_argument("sheet_id")
    p_auf.set_defaults(func=cmd_aufgaben)

    p_ctx = sub.add_parser("context", help="Aktueller Kontext")
    p_ctx.add_argument("action", choices=["show", "clear"])
    p_ctx.set_defaults(func=cmd_context)

    for name, fn in (("build", cmd_build), ("copy", cmd_copy)):
        pb = sub.add_parser(name)
        pb.add_argument("--sheet", default=None)
        pb.add_argument("--aufgabe", type=int, default=None)
        pb.add_argument("--use-case", default=None, choices=list(USE_CASES))
        pb.add_argument("--solution", default=None)
        pb.add_argument("--solution-file", default=None)
        pb.add_argument("--solution-image", default=None)
        pb.set_defaults(func=fn)

    p_pick = sub.add_parser("pick", help="Interaktiver Auswahl-Flow (fuer Top-Bar-Klick)")
    p_pick.set_defaults(func=cmd_pick)

    p_wb = sub.add_parser("waybar-status", help="JSON-Status fuers Waybar-Custom-Modul")
    p_wb.set_defaults(func=cmd_waybar_status)

    p_ob = sub.add_parser("open-browser", help="Chat-Webseite oeffnen")
    p_ob.add_argument("--provider", default="claude", choices=["claude", "chatgpt", "gemini"])
    p_ob.set_defaults(func=cmd_open_browser)

    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
