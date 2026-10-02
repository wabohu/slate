#!/usr/bin/env python3
"""Regression test: draws a fixed scene without a screen and compares the image.

    python tests/regress.py            # compare with tests/regress_reference.png
    python tests/regress.py --update   # rewrite the reference (after an intended visual change)

The scene covers all shapes, colors and sizes via keys, a discarded tiny shape, text,
moving text, the select tool (hit only on the edge, recolor, move, drag a handle)
and undo/redo. Runs on Qt's offscreen platform and
with an empty HOME/XDG_CONFIG_HOME: neither your own config nor the Alacritty theme
affect the result (the default palette applies).

Exit code 0 = image identical, 1 = difference (a diff image is saved).
"""
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).resolve().parent / "regress_reference.png"

# Must happen before the first Qt import
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_home = tempfile.mkdtemp(prefix="slate-test-")
os.environ["HOME"] = _home
os.environ["XDG_CONFIG_HOME"] = str(Path(_home) / ".config")
os.environ["XDG_RUNTIME_DIR"] = str(Path(_home) / "run")  # e.g. editable copy (Ctrl+C), never the real one
(Path(_home) / "run").mkdir()
(Path(_home) / ".config" / "slate").mkdir(parents=True)
(Path(_home) / ".config" / "slate" / "config.toml").write_text(
    '[tools]\norder = ["freehand", "line", "arrow", "rect", "ellipse", "text"]\n'
    'default = "freehand"\n[colors]\ndefault = "red"\n'
    '[ui]\nshow_bar = true\n'  # bar in the image, so the reference covers it too
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
            y = p1[1] + (p2[1] - p1[1]) * i // steps + (15 if i % 2 else 0)  # zigzag for freehand
            QTest.mouseMove(view, QPoint(x, y))
        QTest.mouseRelease(view, Qt.LeftButton, pos=QPoint(*p2))

    key = lambda k, mod=Qt.NoModifier: QTest.keyClick(canvas, k, mod)  # noqa: E731
    key(Qt.Key_A); drag((30, 40), (200, 60))                                        # freehand
    key(Qt.Key_S); key(Qt.Key_G, Qt.ShiftModifier); drag((30, 120), (200, 170))     # line
    key(Qt.Key_D); key(Qt.Key_D, Qt.ShiftModifier); drag((250, 170), (400, 60))     # arrow
    key(Qt.Key_F); key(Qt.Key_F, Qt.ShiftModifier); key(Qt.Key_D, Qt.AltModifier)  # rectangle, level 3
    drag((450, 40), (600, 160))
    key(Qt.Key_S, Qt.AltModifier)                                                   # back to level 2
    key(Qt.Key_G); key(Qt.Key_Z, Qt.ShiftModifier); drag((620, 40), (780, 160))     # ellipse
    key(Qt.Key_F); drag((50, 250), (51, 251))                                       # too small
    key(Qt.Key_T)                                                                   # text
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(60, 300))
    QTest.keyClicks(canvas, "Hallo Welt")
    key(Qt.Key_Escape)
    from elements import TextElement
    text = next(i for i in canvas.scene_.items() if isinstance(i, TextElement))
    start = canvas.mapFromScene(text.pos() + text.boundingRect().center())          # move the text
    QTest.mousePress(view, Qt.LeftButton, pos=start)
    QTest.mouseMove(view, start + QPoint(200, 80))
    QTest.mouseRelease(view, Qt.LeftButton, pos=start + QPoint(200, 80))
    key(Qt.Key_W)                                                                   # select:
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(525, 100))                     # the inside does not hit
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(525, 42))                      # the edge hits
    key(Qt.Key_X, Qt.ShiftModifier); key(Qt.Key_A, Qt.AltModifier)                 # recolor, thinner
    drag((525, 42), (845, 202))                                                     # move
    key(Qt.Key_Escape)                                                              # deselect
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(700, 42))                      # ellipse on the edge
    ellipse = canvas.selected_element()
    assert ellipse is not None, "ellipse not hit"
    corner = canvas.mapFromScene(ellipse.mapToScene(ellipse.handle_points()[2]))    # bottom right handle
    drag((corner.x(), corner.y()), (corner.x() + 60, corner.y() + 60), steps=2)     # handle: larger
    key(Qt.Key_Escape)
    key(Qt.Key_S); drag((500, 300), (700, 450))                                     # line …
    key(Qt.Key_R); key(Qt.Key_R); key(Qt.Key_R, Qt.ShiftModifier)                  # … undo, undo, redo


def main():
    app = QApplication(sys.argv)  # noqa: F841  (must exist)
    from canvas import Canvas

    background = QPixmap(1100, 500)
    background.fill(QColor("#3b4261"))
    canvas = Canvas(QGuiApplication.primaryScreen(), background)
    canvas.resize(1100, 500)
    canvas.show_overlay()
    QApplication.processEvents()
    draw_scene(canvas, canvas.viewport())
    image = canvas.grab().toImage()

    stats = f"Objects: {len(canvas.scene_.items()) - 1}, undo stack: {canvas.undo_stack.count()}, Index: {canvas.undo_stack.index()}"
    if "--update" in sys.argv:
        image.save(str(REFERENCE))
        print(f"Reference written: {REFERENCE}\n{stats}")
        return 0

    reference = QImage(str(REFERENCE))
    if reference.isNull():
        print(f"No reference found. Create it first with: python {Path(__file__).name} --update")
        return 1
    image = image.convertToFormat(reference.format())
    if image == reference:
        print(f"OK: image identical to the reference. {stats}")
        return 0

    # Difference: save a diff image (red pixels) for debugging
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
    print(f"DIFFERENCE: {changed} pixels differ (size {image.size().toTuple()} vs. {reference.size().toTuple()}). {stats}")
    print(f"Actual image: {out_dir / 'regress_actual.png'}, diff: {out_dir / 'regress_diff.png'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
