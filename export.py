"""Ausgabe: Szene als Bild rendern, in die Zwischenablage kopieren, als PNG speichern.

X11-Besonderheit: Der Inhalt der Zwischenablage gehört dem Programm, das kopiert
hat. Beendet es sich, ist er weg. Darum kopieren wir mit xclip: Es läuft nach dem
Kopieren im Hintergrund weiter und liefert das Bild, bis etwas anderes kopiert wird.
"""
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, QStandardPaths
from PySide6.QtGui import QGuiApplication, QImage, QPainter


def render_scene(scene, source_rect, size):
    """Ausschnitt source_rect der Szene als QImage der Größe size (Pixel).

    source_rect ist der Bereich des Screenshots. Würde man die ganze Szene nehmen,
    könnte ein Strich am Rand sie vergrößern, und das Bild würde gestaucht.
    """
    image = QImage(size, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    scene.render(painter, QRectF(image.rect()), source_rect)
    painter.end()
    return image


def png_bytes(image):
    """QImage -> PNG als bytes (über einen Puffer im Speicher)."""
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def copy_to_clipboard(image):
    """Bild in die Zwischenablage. Rückgabe: (ok, Meldung)."""
    if shutil.which("xclip"):
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
                input=png_bytes(image),
                # Ausgaben nicht an uns binden, sonst warten wir auf den Hintergrundprozess
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=True,
            )
            return True, "In die Zwischenablage kopiert"
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[export] xclip fehlgeschlagen: {e}", file=sys.stderr)
    # Fallback: Qt-Zwischenablage. Hält nur, solange das Tool läuft (oder ein Manager übernimmt)
    QGuiApplication.clipboard().setImage(image)
    print("[export] xclip fehlt, Bild nur in der Qt-Zwischenablage", file=sys.stderr)
    return True, "In die Zwischenablage kopiert (ohne xclip, evtl. nicht dauerhaft)"


def copy_text_to_clipboard(text):
    """Text (z. B. einen Pfad) in die Zwischenablage, wie copy_to_clipboard. Rückgabe: ok."""
    if shutil.which("xclip"):
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard", "-i"],
                input=text.encode(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=True,
            )
            return True
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[export] xclip fehlgeschlagen: {e}", file=sys.stderr)
    QGuiApplication.clipboard().setText(text)
    print("[export] xclip fehlt, Text nur in der Qt-Zwischenablage", file=sys.stderr)
    return True


def default_output_dir():
    """~/Pictures/annotate bzw. der XDG-Bilderordner, falls anders benannt."""
    pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
    return Path(pictures or Path.home() / "Pictures") / "annotate"


def new_file_path(directory, suffix=""):
    """Freier Dateiname mit Zeitstempel im Ordner (wird angelegt), z. B.
    annotate_2026-10-01_14-03-22.png; bei Kollision _2, _3 … Kann OSError auslösen."""
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("annotate_%Y-%m-%d_%H-%M-%S") + suffix
    path = directory / f"{stem}.png"
    counter = 2
    while path.exists():  # zweimal Speichern in derselben Sekunde
        path = directory / f"{stem}_{counter}.png"
        counter += 1
    return path


def short_path(path):
    """Pfad zum Anzeigen, Home-Ordner als ~."""
    return str(path).replace(str(Path.home()), "~", 1)


def save_png(image, directory):
    """Sauberes PNG (ohne Bearbeitungsdaten) mit Zeitstempel. Rückgabe: (Pfad oder None, Meldung)."""
    try:
        path = new_file_path(directory, suffix="_export")
        if not image.save(str(path), "PNG"):
            raise OSError("QImage.save hat nicht geklappt")
    except OSError as e:
        print(f"[export] Exportieren fehlgeschlagen: {e}", file=sys.stderr)
        return None, f"Exportieren fehlgeschlagen: {e}"
    return path, f"Exportiert: {short_path(path)}"
