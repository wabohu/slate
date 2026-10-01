#!/usr/bin/env python3
"""Regressionstest: zeichnet eine feste Szene ohne Bildschirm und vergleicht das Bild.

    python tests/regress.py            # vergleichen mit tests/regress_reference.png
    python tests/regress.py --update   # Referenz neu schreiben (nach gewollter Optikänderung)

Die Szene deckt alle Formen, Farben und Größen per Taste, eine verworfene Mini-Form, Text,
Verschieben von Text, das Auswahl-Werkzeug (Treffer nur am Rand, umfärben, verschieben)
sowie Undo/Redo ab. Läuft über Qts Offscreen-Plattform und
mit leerem HOME/XDG_CONFIG_HOME: Weder die eigene Config noch das Alacritty-Theme
beeinflussen das Ergebnis (es gilt die Standardpalette).

Rückgabewert 0 = Bild identisch, 1 = Abweichung (Differenzbild wird gespeichert).
"""
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).resolve().parent / "regress_reference.png"

# Muss vor dem ersten Qt-Import passieren
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_home = tempfile.mkdtemp(prefix="annotate-test-")
os.environ["HOME"] = _home
os.environ["XDG_CONFIG_HOME"] = str(Path(_home) / ".config")
(Path(_home) / ".config" / "annotate").mkdir(parents=True)
(Path(_home) / ".config" / "annotate" / "config.toml").write_text(
    '[tools]\norder = ["freehand", "line", "arrow", "rect", "ellipse", "text"]\n'
    'default = "freehand"\n[colors]\ndefault = "red"\n'
)
sys.path.insert(0, str(REPO))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def draw_scene(canvas, view):
    def drag(p1, p2, steps=5):
        QTest.mousePress(view, Qt.LeftButton, pos=QPoint(*p1))
        for i in range(1, steps + 1):
            x = p1[0] + (p2[0] - p1[0]) * i // steps
            y = p1[1] + (p2[1] - p1[1]) * i // steps + (15 if i % 2 else 0)  # Zickzack für Freihand
            QTest.mouseMove(view, QPoint(x, y))
        QTest.mouseRelease(view, Qt.LeftButton, pos=QPoint(*p2))

    key = lambda k, mod=Qt.NoModifier: QTest.keyClick(canvas, k, mod)  # noqa: E731
    key(Qt.Key_A); drag((30, 40), (200, 60))                                        # Freihand
    key(Qt.Key_S); key(Qt.Key_G, Qt.ShiftModifier); drag((30, 120), (200, 170))     # Linie
    key(Qt.Key_D); key(Qt.Key_D, Qt.ShiftModifier); drag((250, 170), (400, 60))     # Pfeil
    key(Qt.Key_F); key(Qt.Key_F, Qt.ShiftModifier); key(Qt.Key_D, Qt.AltModifier)  # Rechteck, Stufe 3
    drag((450, 40), (600, 160))
    key(Qt.Key_S, Qt.AltModifier)                                                   # zurück auf Stufe 2
    key(Qt.Key_G); key(Qt.Key_Z, Qt.ShiftModifier); drag((620, 40), (780, 160))     # Ellipse
    key(Qt.Key_F); drag((50, 250), (51, 251))                                       # zu klein
    key(Qt.Key_T)                                                                   # Text
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(60, 300))
    QTest.keyClicks(canvas, "Hallo Welt")
    key(Qt.Key_Escape)
    from elements import TextElement
    text = next(i for i in canvas.scene_.items() if isinstance(i, TextElement))
    start = canvas.mapFromScene(text.pos() + text.boundingRect().center())          # Text verschieben
    QTest.mousePress(view, Qt.LeftButton, pos=start)
    QTest.mouseMove(view, start + QPoint(200, 80))
    QTest.mouseRelease(view, Qt.LeftButton, pos=start + QPoint(200, 80))
    key(Qt.Key_W)                                                                   # Auswahl:
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(525, 100))                     # Inneres trifft nicht
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(525, 42))                      # Rand trifft
    key(Qt.Key_X, Qt.ShiftModifier); key(Qt.Key_A, Qt.AltModifier)                 # umfärben, dünner
    drag((525, 42), (845, 202))                                                     # verschieben
    key(Qt.Key_Escape)                                                              # abwählen
    key(Qt.Key_S); drag((500, 300), (700, 450))                                     # Linie …
    key(Qt.Key_R); key(Qt.Key_R); key(Qt.Key_R, Qt.ShiftModifier)                  # … Undo, Undo, Redo


def main():
    app = QApplication(sys.argv)  # noqa: F841  (muss existieren)
    import annotate

    background = QPixmap(1100, 500)
    background.fill(QColor("#3b4261"))
    canvas = annotate.Canvas(QGuiApplication.primaryScreen(), background)
    canvas.resize(1100, 500)
    canvas.show_overlay()
    QApplication.processEvents()
    draw_scene(canvas, canvas.viewport())
    image = canvas.grab().toImage()

    stats = f"Objekte: {len(canvas.scene_.items()) - 1}, Undo-Stack: {canvas.undo_stack.count()}, Index: {canvas.undo_stack.index()}"
    if "--update" in sys.argv:
        image.save(str(REFERENCE))
        print(f"Referenz geschrieben: {REFERENCE}\n{stats}")
        return 0

    reference = QImage(str(REFERENCE))
    if reference.isNull():
        print(f"Keine Referenz gefunden. Erst anlegen mit: python {Path(__file__).name} --update")
        return 1
    image = image.convertToFormat(reference.format())
    if image == reference:
        print(f"OK: Bild identisch mit der Referenz. {stats}")
        return 0

    # Abweichung: Differenzbild (rote Pixel) zur Fehlersuche speichern
    diff = QImage(reference)
    changed = 0
    if image.size() == reference.size():
        for y in range(reference.height()):
            for x in range(reference.width()):
                if image.pixel(x, y) != reference.pixel(x, y):
                    diff.setPixelColor(x, y, QColor("red"))
                    changed += 1
    out_dir = Path(tempfile.gettempdir())
    image.save(str(out_dir / "regress_actual.png"))
    diff.save(str(out_dir / "regress_diff.png"))
    print(f"ABWEICHUNG: {changed} Pixel anders (Größe {image.size().toTuple()} vs. {reference.size().toTuple()}). {stats}")
    print(f"Ist-Bild: {out_dir / 'regress_actual.png'}, Differenz: {out_dir / 'regress_diff.png'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
