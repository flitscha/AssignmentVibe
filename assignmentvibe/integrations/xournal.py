"""
Read a Xournal++ notebook (.xopp) and draw parts of it.

A .xopp is gzipped XML: pages, each with layers of strokes (pen input, one
polyline per stroke, coordinates in points), pasted images (base64 PNG with a
bounding box) and, rarely, typed text. How the handwritten solutions in
~/Uni look: the task statement pasted in as a screenshot, the handwriting
below it, the next statement below that - so the images are what tells which
task a stretch of handwriting belongs to (core.worklog does that matching).

Here only the file side: parsing into plain dicts, OCR of the pasted images
(Tesseract, cached - they never change), and rendering a vertical stretch of
pages to one PNG with pycairo.

No dependency on any other module in this project besides paths (the cache).
"""

import base64
import gzip
import hashlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


class XournalError(Exception):
    pass


def _floats(text: str | None) -> list[float]:
    return [float(v) for v in (text or "").split()]


def _color(value: str | None) -> tuple[float, float, float, float]:
    """"#3333ccff" -> (r, g, b, a) in 0..1."""
    v = (value or "#000000ff").lstrip("#")
    v = (v + "ff")[:8] if len(v) == 6 else v.ljust(8, "f")
    return tuple(int(v[i:i + 2], 16) / 255 for i in range(0, 8, 2))


def load(path: Path) -> list[dict]:
    """[{"width", "height", "images": [...], "strokes": [...], "texts": [...]}]
    per page. An image is {"box": (l, t, r, b), "png": bytes}; a stroke
    {"points": [(x, y)], "widths": [...], "color": (r, g, b, a), "box": ...,
    "highlighter": bool}; a text {"box": (x, y, x, y), "text": str}."""
    try:
        root = ET.fromstring(gzip.open(path).read())
    except (OSError, ET.ParseError, EOFError) as e:
        raise XournalError(f"{path.name}: {e}") from e

    pages = []
    for page in root.iter("page"):
        out = {"width": float(page.get("width", 595)), "height": float(page.get("height", 842)),
               "images": [], "strokes": [], "texts": []}
        for layer in page.iter("layer"):
            for el in layer:
                if el.tag == "image" and el.text:
                    box = tuple(float(el.get(k, 0)) for k in ("left", "top", "right", "bottom"))
                    out["images"].append({"box": box, "png": base64.b64decode(el.text)})
                elif el.tag == "stroke" and el.text:
                    coords = _floats(el.text)
                    points = list(zip(coords[0::2], coords[1::2]))
                    if not points:
                        continue
                    xs, ys = [p[0] for p in points], [p[1] for p in points]
                    out["strokes"].append({
                        "points": points,
                        "widths": _floats(el.get("width")) or [1.0],
                        "color": _color(el.get("color")),
                        "highlighter": el.get("tool") == "highlighter",
                        "box": (min(xs), min(ys), max(xs), max(ys)),
                    })
                elif el.tag == "text" and el.text:
                    x, y = float(el.get("x", 0)), float(el.get("y", 0))
                    out["texts"].append({"box": (x, y, x, y), "text": el.text})
        pages.append(out)
    return pages


# --- OCR of the pasted images ------------------------------------------------------

def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _languages() -> str:
    """German where its data is installed (tesseract-data-deu), English
    otherwise - which still reads a German statement well enough to match
    it, if with "fiihren" for "führen"."""
    try:
        listed = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                                text=True, timeout=10).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return "eng"
    return "deu+eng" if "deu" in listed else "eng"


def ocr(png: bytes, cache_dir: Path | None = None) -> str:
    """The printed text on a pasted image. Cached by the image's hash: the
    same screenshot is OCRed once, however often the notebook is read."""
    key = hashlib.sha1(png).hexdigest()
    cached = cache_dir / f"{key}.txt" if cache_dir else None
    if cached and cached.exists():
        return cached.read_text(encoding="utf-8")
    try:
        done = subprocess.run(["tesseract", "stdin", "stdout", "-l", _languages()],
                              input=png, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise XournalError(f"tesseract: {e}") from e
    text = done.stdout.decode("utf-8", "replace")
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(text, encoding="utf-8")
    return text


# --- Drawing ---------------------------------------------------------------------

def render(pages: list[dict], slices: list[tuple], out: Path,
           scale: float = 2.0, margin: float = 8.0) -> Path:
    """Draw the given (page, top, bottom[, label]) stretches one below the
    other into one PNG - the handwriting of one task, across a page break. A
    label ("b)") is written above its stretch, where the pasted statement of
    that part was. White background, no ruling: the lines of the paper only
    get in the way of reading it."""
    import cairo

    if not slices:
        raise XournalError("nothing to draw")
    label_height = 16.0
    width = max(pages[s[0]]["width"] for s in slices)
    height = (sum(s[2] - s[1] for s in slices) + margin * (len(slices) + 1)
              + label_height * sum(1 for s in slices if len(s) > 3 and s[3]))
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, int(width * scale), int(height * scale))
    ctx = cairo.Context(surface)
    ctx.scale(scale, scale)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)

    y0 = margin
    for p, top, bottom, *rest in slices:
        page = pages[p]
        if rest and rest[0]:
            ctx.set_source_rgb(0.45, 0.45, 0.45)
            ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            ctx.set_font_size(11)
            ctx.move_to(margin + 4, y0 + 11)
            ctx.show_text(rest[0])
            y0 += label_height
        ctx.save()
        ctx.rectangle(0, y0, width, bottom - top)
        ctx.clip()
        ctx.translate(0, y0 - top)
        for image in page["images"]:
            l, t, r, b = image["box"]
            if b < top or t > bottom:
                continue
            _draw_png(ctx, image["png"], l, t, r - l, b - t)
        for stroke in page["strokes"]:
            if stroke["box"][3] < top or stroke["box"][1] > bottom:
                continue
            _draw_stroke(ctx, stroke)
        ctx.restore()
        y0 += bottom - top + margin

    out.parent.mkdir(parents=True, exist_ok=True)
    surface.write_to_png(str(out))
    return out


def _draw_png(ctx, data: bytes, x: float, y: float, w: float, h: float) -> None:
    import io

    import cairo

    try:
        image = cairo.ImageSurface.create_from_png(io.BytesIO(data))
    except Exception:
        return  # not a PNG (xournal can hold JPEGs); skipped rather than guessed
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(w / max(1, image.get_width()), h / max(1, image.get_height()))
    ctx.set_source_surface(image, 0, 0)
    ctx.paint()
    ctx.restore()


def _draw_stroke(ctx, stroke: dict) -> None:
    r, g, b, a = stroke["color"]
    ctx.set_source_rgba(r, g, b, 0.35 if stroke["highlighter"] else a)
    points, widths = stroke["points"], stroke["widths"]
    if len(widths) > 1:
        # Pressure: the first width is the pen's, then one per segment.
        for i in range(1, len(points)):
            ctx.set_line_width(widths[min(i, len(widths) - 1)])
            ctx.move_to(*points[i - 1])
            ctx.line_to(*points[i])
            ctx.stroke()
        return
    ctx.set_line_width(widths[0])
    ctx.move_to(*points[0])
    for pt in points[1:]:
        ctx.line_to(*pt)
    if len(points) == 1:
        ctx.line_to(points[0][0] + 0.01, points[0][1])
    ctx.stroke()
