"""
OCR for a photo/screenshot of the current (typed or printed) partial
solution, via Tesseract.

IMPORTANT - honest limitation: Tesseract is a text-OCR tool for printed/typed
writing. For HANDWRITING (the actual use case from the vision) it is known to
be poor to unusable, and for handwritten MATH FORMULAS (special characters,
sub/superscripts, fractions) even more so. This is deliberately just a
placeholder/proof-of-concept for the code path ("image -> text -> prompt"),
tested with a synthetically generated, cleanly typed text image (see
docs/LINUX_PROTOTYPE.md). Real handwriting needs a specialized model (e.g.
pix2tex/LaTeX-OCR for formulas) - see the roadmap.

No dependency on any other module in this project.
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
