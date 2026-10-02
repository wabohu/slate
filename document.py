"""Save and load drawings: a normal PNG with embedded editing data.

The PNG shows the drawing with all markings, just as any image viewer
displays it. In addition, a PNG text chunk (metadata, key "slate") holds
a JSON document:

    {
      "format": "slate", "version": 1,
      "background": {"type": "image", "png": "<Base64 of the raw screenshot>"}
                 or {"type": "color", "color": "#24283b"}   (whiteboard),
      "elements": [ {"type": "shape", ...}, {"type": "text", ...} ],  # bottom to top
      "crop": [x, y, width, height]   (optional: crop in scene coordinates, key y)
    }

Opening such a PNG with slate makes everything editable again. A PNG without this
data opens as a background. Programs that save the image again often discard
the metadata; the own file stays untouched by that.

Qt concept: QImage.setText(key, text) writes text chunks when saving as PNG,
QImage.text(key) reads them again after loading.
"""
import base64
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QImageReader

from elements import ImageElement, ShapeElement, TextElement
from export import png_bytes, short_path

FORMAT = "slate"
VERSION = 1
PNG_KEY = "slate"
ELEMENT_TYPES = {"shape": ShapeElement, "text": TextElement, "image": ImageElement}

# Allow large embedded images (otherwise Qt limits image sizes to 256 MB of memory)
QImageReader.setAllocationLimit(1024)


def build_document(background, elements, crop=None):
    """Document data from background and elements (bottom -> top).

    background: QImage (raw screenshot) or QColor (whiteboard); crop: QRectF or None.
    """
    if isinstance(background, QColor):
        background_data = {"type": "color", "color": background.name()}
    else:
        background_data = {"type": "image", "png": base64.b64encode(png_bytes(background)).decode("ascii")}
    return {
        "format": FORMAT,
        "version": VERSION,
        "background": background_data,
        "elements": [item.to_dict() for item in elements],
        **({"crop": [crop.x(), crop.y(), crop.width(), crop.height()]} if crop is not None else {}),
    }


def crop_from_data(value):
    """[x, y, w, h] -> QRectF; missing or unusable -> None (with a warning, no crash)."""
    if value is None:
        return None
    try:
        x, y, w, h = (float(v) for v in value)
        if w <= 0 or h <= 0:
            raise ValueError("width/height must be positive")
    except (TypeError, ValueError) as e:
        print(f"[document] crop ignored ({e}): {value!r}", file=sys.stderr)
        return None
    return QRectF(x, y, w, h)


def save_document(path, rendered, document):
    """Save rendered (QImage with markings) together with the document data as PNG.

    Write to a temporary file first and then rename it: if something goes wrong,
    an existing file stays intact. Returns: (ok, message).
    """
    image = QImage(rendered)
    image.setText(PNG_KEY, json.dumps(document, separators=(",", ":")))
    tmp = Path(path).with_suffix(".tmp.png")
    try:
        if not image.save(str(tmp), "PNG"):
            raise OSError("QImage.save did not work")
        os.replace(tmp, path)  # replaces atomically, including an existing file
    except OSError as e:
        tmp.unlink(missing_ok=True)
        print(f"[document] Saving failed: {e}", file=sys.stderr)
        return False, f"Saving failed: {e}"
    return True, f"Saved: {short_path(path)}"


def load_document(path, with_crop=False):
    """Load a PNG. Returns: (background or None, elements, is_drawing, message),
    with with_crop=True also the saved crop (QRectF or None).

    The background is a QImage (screenshot) or a QColor (whiteboard).

    is_drawing = True: own drawing with editing data, Ctrl+S may
    overwrite it. Otherwise it is a foreign image (background, saved as a new file).
    """
    image = QImageReader(str(path)).read()
    if image.isNull():
        result = None, [], False, f"Cannot open {path} as an image"
        return result + (None,) if with_crop else result
    raw = image.text(PNG_KEY)
    if not raw:
        result = image, [], False, f"Image opened: {short_path(path)}"
        return result + (None,) if with_crop else result
    try:
        document = json.loads(raw)
        if document.get("format") != FORMAT:
            raise ValueError("not a slate document")
        if document.get("version", 0) > VERSION:
            print(f"[document] Version {document['version']} is newer than this tool ({VERSION}), "
                  "trying anyway", file=sys.stderr)
        spec = document["background"]
        if spec.get("type") == "color":
            background = QColor(spec["color"])
            if not background.isValid():
                raise ValueError(f"invalid background color {spec['color']!r}")
        else:
            background = QImage.fromData(base64.b64decode(spec["png"]))
            if background.isNull():
                raise ValueError("embedded background unreadable")
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"[document] Editing data unusable ({e}), opening as an image", file=sys.stderr)
        result = image, [], False, "Editing data broken, opened as an image"
        return result + (None,) if with_crop else result
    elements = elements_from_dicts(document.get("elements", []))
    result = background, elements, True, f"Opened: {short_path(path)}"
    return result + (crop_from_data(document.get("crop")),) if with_crop else result


def elements_from_dicts(dicts):
    """Create elements; skip unknown or broken entries (with a warning)."""
    result = []
    for data in dicts:
        try:
            result.append(ELEMENT_TYPES[data["type"]].from_dict(data))
        except (KeyError, ValueError, TypeError) as e:
            print(f"[document] Element skipped ({type(e).__name__}: {e}): {str(data)[:80]}",
                  file=sys.stderr)
    return result
