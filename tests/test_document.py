#!/usr/bin/env python3
"""Test Speichern/Laden: Szene zeichnen, Strg+S, neu laden, pixelgenau vergleichen;
dazu das Whiteboard (speichern, als Whiteboard laden, Export des benutzten Bereichs).

    python tests/test_document.py

Nutzt die Szene und die isolierte Umgebung aus regress.py (leeres HOME,
Offscreen-Plattform). Rückgabewert 0 = alles ok, 1 = Fehler.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regress  # noqa: E402  (setzt HOME, Config und QT_QPA_PLATFORM)

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
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

    # Whiteboard: leere Fläche, speichern, als Whiteboard wieder laden
    import export
    export.shutil.which = lambda name: None  # nie die echte Zwischenablage anfassen
    board = annotate.Canvas(QGuiApplication.primaryScreen(), None, board=True)
    board.resize(900, 500)
    board.show_window()
    QApplication.processEvents()
    bview = board.viewport()
    QTest.keyClick(board, Qt.Key_F)
    QTest.mousePress(bview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(bview, QPoint(300, 200))
    QTest.mouseRelease(bview, Qt.LeftButton, pos=QPoint(300, 200))
    QTest.keyClick(board, Qt.Key_Escape)
    QTest.keyClick(board, Qt.Key_Return)
    check("Whiteboard: Esc und Enter schließen nicht", board.isVisible())
    check("Whiteboard: ungespeichert erkannt", not board.undo_stack.isClean())
    board_image = board.render_image()
    check("Whiteboard-Export = benutzter Bereich", board_image.width() < 400 and board_image.height() < 300)
    QTest.keyClick(board, Qt.Key_S, Qt.ControlModifier)
    check("Whiteboard gespeichert (_board)", board.document_path and board.document_path.stem.endswith("_board"))
    check("nach dem Speichern sauber", board.undo_stack.isClean())
    bbg, belems, _, _ = load_document(board.document_path)
    check("als Whiteboard geladen", isinstance(bbg, QColor) and bbg == board.board_color and len(belems) == 1)
    board2 = annotate.Canvas(QGuiApplication.primaryScreen(), None, belems, board.document_path,
                             board=True, board_color=bbg)
    board2.show_window()
    check("Whiteboard neu geladen = gleicher Export", board2.render_image() == board_image)

    # Hintergrund wechseln (Strg+B): Undo-Schritt, wird mitgespeichert
    old_bg = QColor(board2.board_color)
    QTest.keyClick(board2, Qt.Key_B, Qt.ControlModifier)
    new_bg = QColor(board2.board_color)
    check("Strg+B wechselt den Hintergrund", new_bg != old_bg and not board2.undo_stack.isClean())
    QTest.keyClick(board2, Qt.Key_R)
    check("Hintergrund: Undo", board2.board_color == old_bg and board2.undo_stack.isClean())
    QTest.keyClick(board2, Qt.Key_B, Qt.ControlModifier | Qt.ShiftModifier)
    QTest.keyClick(board2, Qt.Key_S, Qt.ControlModifier)
    bbg2, _, _, _ = load_document(board2.document_path)
    check("Hintergrund gespeichert", bbg2 == board2.board_color != old_bg)

    # Heller Hintergrund: Farben werden abgedunkelt gezeigt, gespeichert bleibt die Grundfarbe
    from colors import LIGHT_CONTRAST, contrast
    paper = QColor("#f8f6f0")
    light = annotate.Canvas(QGuiApplication.primaryScreen(), None, board=True, board_color=paper)
    light.resize(900, 500)
    light.show_window()
    QApplication.processEvents()
    lview = light.viewport()
    # Eine Farbe wählen, die auf Papier zu schwach ist (sonst bliebe sie unverändert)
    weak = next(i for i, c in enumerate(light.swatches) if contrast(c, paper.name()) < LIGHT_CONTRAST)
    light.set_color(weak)
    QTest.keyClick(light, Qt.Key_F)
    QTest.mousePress(lview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(lview, QPoint(300, 200))
    QTest.mouseRelease(lview, Qt.LeftButton, pos=QPoint(300, 200))
    rect = light.elements()[0]
    base, shown = rect.color.name(), rect.pen().color().name()
    check("hell: Form abgedunkelt gezeigt", shown != base and contrast(shown, paper.name()) >= LIGHT_CONTRAST)
    check("hell: Grundfarbe gespeichert", rect.to_dict()["color"] == base)
    text = annotate.TextElement(QPointF(0, 0), QColor(base), 20, text="x")
    light.scene_.addItem(text)
    check("hell: Text abgedunkelt gezeigt", text.defaultTextColor().name() == shown and text.color.name() == base)
    check("hell: Farbleiste angepasst", light.palette_bar.colors[light.color_index].name() != light.swatches[light.color_index])
    light.undo_stack.push(annotate.PropertyCommand(light.set_board_color, QColor(paper), QColor("#24283b")))
    check("dunkel: Grundfarbe gezeigt", rect.pen().color().name() == base and text.defaultTextColor().name() == base)
    light.undo_stack.undo()
    check("Undo: wieder abgedunkelt", rect.pen().color().name() == shown)

    print("\nAlles OK." if not failures else f"\n{len(failures)} Fehler.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
