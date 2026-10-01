"""Zeichnungen speichern und laden: ein normales PNG mit eingebetteten Bearbeitungsdaten.

Das PNG zeigt die Zeichnung mit allen Markierungen, so wie jeder Bildbetrachter sie
anzeigt. Zusätzlich steckt in einem PNG-Text-Chunk (Metadaten, Schlüssel "annotate")
ein JSON-Dokument:

    {
      "format": "annotate", "version": 1,
      "background": {"type": "image", "png": "<Base64 des rohen Screenshots>"}
                 oder {"type": "color", "color": "#24283b"}   (Whiteboard),
      "elements": [ {"type": "shape", ...}, {"type": "text", ...} ]   # von unten nach oben
    }

Öffnet man so ein PNG mit annotate, ist alles wieder bearbeitbar. Ein PNG ohne diese
Daten öffnet sich als Hintergrund. Programme, die das Bild neu speichern, verwerfen
die Metadaten oft; die eigene Datei bleibt davon unberührt.

Qt-Konzept: QImage.setText(key, text) schreibt Text-Chunks beim Speichern als PNG,
QImage.text(key) liest sie nach dem Laden wieder aus.
"""
import base64
import json
import os
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QImageReader

from elements import ShapeElement, TextElement
from export import png_bytes, short_path

FORMAT = "annotate"
VERSION = 1
PNG_KEY = "annotate"
ELEMENT_TYPES = {"shape": ShapeElement, "text": TextElement}

# Große eingebettete Bilder erlauben (Qt begrenzt Bildgrößen sonst auf 256 MB Speicher)
QImageReader.setAllocationLimit(1024)


def build_document(background, elements):
    """Dokument-Daten aus Hintergrund und Elementen (unten -> oben).

    background: QImage (roher Screenshot) oder QColor (Whiteboard).
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
    }


def save_document(path, rendered, document):
    """rendered (QImage mit Markierungen) samt Dokument-Daten als PNG speichern.

    Erst in eine Hilfsdatei schreiben und dann umbenennen: Geht etwas schief,
    bleibt eine vorhandene Datei unbeschädigt. Rückgabe: (ok, Meldung).
    """
    image = QImage(rendered)
    image.setText(PNG_KEY, json.dumps(document, separators=(",", ":")))
    tmp = Path(path).with_suffix(".tmp.png")
    try:
        if not image.save(str(tmp), "PNG"):
            raise OSError("QImage.save hat nicht geklappt")
        os.replace(tmp, path)  # ersetzt atomar, auch eine vorhandene Datei
    except OSError as e:
        tmp.unlink(missing_ok=True)
        print(f"[document] Speichern fehlgeschlagen: {e}", file=sys.stderr)
        return False, f"Speichern fehlgeschlagen: {e}"
    return True, f"Gespeichert: {short_path(path)}"


def load_document(path):
    """PNG laden. Rückgabe: (Hintergrund oder None, Elemente, ist_zeichnung, Meldung).

    Hintergrund ist ein QImage (Screenshot) oder eine QColor (Whiteboard).

    ist_zeichnung = True: eigene Zeichnung mit Bearbeitungsdaten, Strg+S darf sie
    überschreiben. Sonst ist es ein fremdes Bild (Hintergrund, Speichern als neue Datei).
    """
    image = QImageReader(str(path)).read()
    if image.isNull():
        return None, [], False, f"Kann {path} nicht als Bild öffnen"
    raw = image.text(PNG_KEY)
    if not raw:
        return image, [], False, f"Bild geöffnet: {short_path(path)}"
    try:
        document = json.loads(raw)
        if document.get("format") != FORMAT:
            raise ValueError("kein annotate-Dokument")
        if document.get("version", 0) > VERSION:
            print(f"[document] Version {document['version']} ist neuer als dieses Tool ({VERSION}), "
                  "versuche es trotzdem", file=sys.stderr)
        spec = document["background"]
        if spec.get("type") == "color":
            background = QColor(spec["color"])
            if not background.isValid():
                raise ValueError(f"ungültige Hintergrundfarbe {spec['color']!r}")
        else:
            background = QImage.fromData(base64.b64decode(spec["png"]))
            if background.isNull():
                raise ValueError("eingebetteter Hintergrund unlesbar")
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"[document] Bearbeitungsdaten unbrauchbar ({e}), öffne als Bild", file=sys.stderr)
        return image, [], False, "Bearbeitungsdaten fehlerhaft, als Bild geöffnet"
    elements = elements_from_dicts(document.get("elements", []))
    return background, elements, True, f"Geöffnet: {short_path(path)}"


def elements_from_dicts(dicts):
    """Elemente erzeugen; unbekannte oder fehlerhafte Einträge überspringen (mit Warnung)."""
    result = []
    for data in dicts:
        try:
            result.append(ELEMENT_TYPES[data["type"]].from_dict(data))
        except (KeyError, ValueError, TypeError) as e:
            print(f"[document] Element übersprungen ({type(e).__name__}: {e}): {str(data)[:80]}",
                  file=sys.stderr)
    return result
