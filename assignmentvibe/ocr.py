"""
OCR fuer ein Foto/einen Screenshot der bisherigen (getippten oder gedruckten)
Teilloesung, ueber Tesseract.

WICHTIG - ehrliche Einschraenkung: Tesseract ist ein Text-OCR-Tool fuer
gedruckte/getippte Schrift. Fuer HANDSCHRIFT (der eigentliche Use-Case aus der
Vision) ist es bekanntermassen schlecht bis unbrauchbar, und fuer
handschriftliche MATHE-FORMELN (Sonderzeichen, hoch-/tiefgestellt, Brueche)
erst recht nicht geeignet. Das hier ist bewusst nur ein Platzhalter/Proof-of-
Concept fuer den Code-Pfad ("Bild -> Text -> Prompt"), getestet mit einem
synthetisch erzeugten, sauber getippten Text-Bild (siehe
docs/LINUX_PROTOTYPE.md). Fuer echte Handschrift ist ein spezialisiertes
Modell noetig (z.B. pix2tex/LaTeX-OCR fuer Formeln) - siehe Roadmap.
"""


class OcrUnavailable(RuntimeError):
    pass


def image_to_text(image_path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise OcrUnavailable(
            "OCR-Abhaengigkeiten fehlen. Installieren mit: "
            "pip install pytesseract pillow  (und auf dem System: tesseract-ocr Paket)"
        ) from e

    try:
        image = Image.open(image_path)
    except Exception as e:
        raise OcrUnavailable(f"Bild konnte nicht geoeffnet werden: {e}") from e

    try:
        text = pytesseract.image_to_string(image, lang="deu+eng")
    except Exception as e:
        raise OcrUnavailable(
            f"Tesseract-Aufruf fehlgeschlagen ({e}). Ist das 'tesseract-ocr' "
            f"Systempaket installiert (nicht nur das Python-Paket)?"
        ) from e

    return text.strip()
