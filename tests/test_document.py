#!/usr/bin/env python3
"""Test Speichern/Laden: Szene zeichnen, Strg+S, neu laden, pixelgenau vergleichen.

    python tests/test_document.py

Nutzt die Szene und die isolierte Umgebung aus regress.py (leeres HOME,
Offscreen-Plattform). Rückgabewert 0 = alles ok, 1 = Fehler.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regress  # noqa: E402  (setzt HOME, Config und QT_QPA_PLATFORM)

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

failures = []


def check(name, condition):
    print(f"{'OK  ' if condition else 'FEHLER'}  {name}")
    if not condition:
        failures.append(name)


def make_canvas(annotate, pixmap, elements=(), path=None):
    canvas = annotate.Canvas(QGuiApplication.primaryScreen(), pixmap, elements, path)
    canvas.resize(1100, 500)
    canvas.show_overlay()
    QApplication.processEvents()
    return canvas


def main():
    app = QApplication(sys.argv)  # noqa: F841
    import annotate
    from document import load_document
    from export import default_output_dir

    background = QPixmap(1100, 500)
    background.fill(QColor("#3b4261"))
    canvas = make_canvas(annotate, background)
    regress.draw_scene(canvas, canvas.viewport())
    out = Path(default_output_dir())

    def drawings():  # gespeicherte Zeichnungen, ohne Export-PNGs
        return sorted(p for p in out.glob("annotate_*.png") if not p.stem.endswith("_export"))

    QTest.keyClick(canvas, Qt.Key_S, Qt.ControlModifier)
    QTest.keyClick(canvas, Qt.Key_S, Qt.ControlModifier)
    saved = drawings()
    check("Strg+S zweimal = eine Datei", len(saved) == 1)
    QTest.keyClick(canvas, Qt.Key_E, Qt.ControlModifier)
    exports = sorted(out.glob("*_export.png"))
    check("Strg+E = zusätzliches Export-PNG", len(exports) == 1)

    path = saved[0]
    rendered = canvas.render_image()
    check("gespeichertes PNG zeigt die Zeichnung",
          QImage(str(path)).convertToFormat(rendered.format()) == rendered)
    check("Export-PNG ohne Bearbeitungsdaten", not QImage(str(exports[0])).text("annotate"))

    bg, elements, is_drawing, message = load_document(path)
    check(f"als Zeichnung geladen ({message})", is_drawing and len(elements) == len(canvas.elements()))
    check("Elemente identisch",
          [e.to_dict() for e in elements] == [e.to_dict() for e in canvas.elements()])
    reopened = make_canvas(annotate, QPixmap.fromImage(bg), elements, path)
    check("neu geladen = pixelgleich", reopened.render_image() == rendered)
    check("Undo nach dem Laden leer", reopened.undo_stack.count() == 0)

    # Weiterarbeiten: Element verschieben, speichern, wieder laden
    QTest.keyClick(reopened, Qt.Key_W)
    view = reopened.viewport()
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(30, 120))       # blaue Linie
    moved = reopened.selected_element()
    check("Linie nach dem Laden auswählbar", moved is not None)
    QTest.mousePress(view, Qt.LeftButton, pos=QPoint(30, 120))
    QTest.mouseMove(view, QPoint(130, 220))
    QTest.mouseRelease(view, Qt.LeftButton, pos=QPoint(130, 220))
    QTest.keyClick(reopened, Qt.Key_S, Qt.ControlModifier)
    check("Speichern überschreibt dieselbe Datei", drawings() == [path])
    _, again, _, _ = load_document(path)
    match = [e for e in again if e.id == moved.id]
    check("Verschiebung gespeichert", match and match[0].pos() == moved.pos())

    print("\nAlles OK." if not failures else f"\n{len(failures)} Fehler.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
