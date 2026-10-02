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


def make_canvas(pixmap, elements=(), path=None):
    from canvas import Canvas
    canvas = Canvas(QGuiApplication.primaryScreen(), pixmap, elements, path)
    canvas.resize(1100, 500)
    canvas.show_overlay()
    QApplication.processEvents()
    return canvas


def main():
    app = QApplication(sys.argv)  # noqa: F841
    from canvas import Canvas
    from commands import PropertyCommand
    from elements import TextElement
    from document import load_document
    from export import default_output_dir

    # Mixins der Canvas (docs/plan-aufteilung.md): Keine Methode darf in zwei Klassen
    # stehen, sonst überdeckt die eine still die andere
    parts = [c for c in Canvas.__mro__ if c.__module__ not in ("builtins",) and
             not c.__module__.startswith(("PySide6", "Shiboken"))]
    names = [{n for n in c.__dict__ if not n.startswith("__")} for c in parts]
    clashes = {n for i, a in enumerate(names) for b in names[i + 1:] for n in a & b}
    check(f"Canvas-Mixins ohne doppelte Methoden ({', '.join(c.__name__ for c in parts)})", not clashes)

    background = QPixmap(1100, 500)
    background.fill(QColor("#3b4261"))
    canvas = make_canvas(background)
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
    reopened = make_canvas(QPixmap.fromImage(bg), elements, path)
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

    # Mauszeiger: Fadenkreuz ohne Mittelpunkt, Kreis = Strichbreite, Stiftfarbe; Auswahl/Zeigen: Pfeil
    from tools import Tool
    cur = make_canvas(QPixmap(800, 400))
    cur.set_tool(Tool.FREEHAND)
    cur.set_size(0)
    small_cursor = cur.viewport().cursor().pixmap().toImage()
    cur.set_size(3)
    big_cursor = cur.viewport().cursor().pixmap().toImage()
    center = big_cursor.pixelColor(big_cursor.width() // 2, big_cursor.height() // 2)
    pen = cur.pen_color
    has_pen = any(abs(big_cursor.pixelColor(x, y).red() - pen.red()) < 8
                  and abs(big_cursor.pixelColor(x, y).green() - pen.green()) < 8
                  and abs(big_cursor.pixelColor(x, y).blue() - pen.blue()) < 8 and big_cursor.pixelColor(x, y).alpha() > 200
                  for x in range(big_cursor.width()) for y in range(big_cursor.height()))
    check("Mauszeiger: wächst mit der Strichstärke, Mitte frei, Stiftfarbe",
          big_cursor.width() > small_cursor.width() and center.alpha() == 0 and has_pen)
    cur.set_tool(Tool.SELECT)
    arrow_select = cur.viewport().cursor().shape() == Qt.ArrowCursor
    cur.set_tool(Tool.RECT)
    cur.toggle_pointer("spotlight")
    hidden_pointer = cur.viewport().cursor().shape() == Qt.BlankCursor
    cur.set_tool(Tool.LINE)
    check("Mauszeiger: Pfeil im Auswahl-Werkzeug, beim Zeigen ausgeblendet, Werkzeugwechsel beendet Zeigen",
          arrow_select and hidden_pointer and cur.pointer_mode is None
          and cur.viewport().cursor().shape() == Qt.BitmapCursor)
    cur.close()

    # Unschärfe (z): verpixelt den Screenshot darunter; beim Speichern ins Rohbild eingebrannt
    from PySide6.QtGui import QPainter as _QPainter
    stripes = QImage(800, 400, QImage.Format_RGB32)
    stripes.fill(QColor("white"))
    sp = _QPainter(stripes)
    for x in range(0, 800, 4):  # feine senkrechte Streifen: nach dem Verpixeln einheitlich grau
        sp.fillRect(x, 0, 2, 400, QColor("black"))
    sp.end()
    blur_canvas = make_canvas(QPixmap.fromImage(stripes))
    bview = blur_canvas.viewport()
    QTest.keyClick(blur_canvas, Qt.Key_Z)
    blur_canvas.set_size(2)  # Stufe 3: Klötze 24 px
    QTest.mousePress(bview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(bview, QPoint(300, 250))
    QTest.mouseRelease(bview, Qt.LeftButton, pos=QPoint(300, 250))
    blurs = [e for e in blur_canvas.elements() if e.tool == Tool.BLUR]
    shown = blur_canvas.render_image()

    def stripe_contrast(img, y, x0, x1):
        values = [img.pixelColor(x, y).lightness() for x in range(x0, x1)]
        return max(values) - min(values)
    check("Unschärfe: ein Element, Bereich verpixelt, außerhalb unverändert",
          len(blurs) == 1 and stripe_contrast(shown, 150, 130, 150) < 40 and stripe_contrast(shown, 350, 130, 150) > 200)
    QTest.keyClick(blur_canvas, Qt.Key_S, Qt.ControlModifier)
    saved_bg, saved_elems, _, _ = load_document(blur_canvas.document_path)
    check("Unschärfe: gespeichertes Rohbild ist dort verpixelt (eingebrannt), Element bleibt",
          stripe_contrast(saved_bg, 150, 130, 150) < 40 and stripe_contrast(saved_bg, 350, 130, 150) > 200
          and [e.tool for e in saved_elems] == [Tool.BLUR])
    check("Unschärfe: im laufenden Tool bleibt das Rohbild unverändert",
          stripe_contrast(blur_canvas.background_image, 150, 130, 150) > 200)
    blur_canvas.close()

    # Marker (c): Klick = Kreis, Ziehen = Kreis mit Zeigelinie; neu nummerieren, Buchstaben
    mk = make_canvas(QPixmap(800, 400))
    mview = mk.viewport()

    def click(x, y, x2=None, y2=None):
        QTest.mousePress(mview, Qt.LeftButton, pos=QPoint(x, y))
        if x2 is not None:
            QTest.mouseMove(mview, QPoint(x2, y2))
        QTest.mouseRelease(mview, Qt.LeftButton, pos=QPoint(x2 or x, y2 or y))

    def labels():
        return [e.marker_label() for e in mk.elements() if e.tool == Tool.MARKER]
    QTest.keyClick(mk, Qt.Key_C)
    click(100, 100)
    click(200, 100, 260, 60)
    click(300, 100)
    markers = [e for e in mk.elements() if e.tool == Tool.MARKER]
    check("Marker: 1 2 3, Klick ohne Linie, Ziehen mit Linie",
          labels() == ["1", "2", "3"] and markers[0].points[0] == markers[0].points[1]
          and markers[1].points[0] != markers[1].points[1])
    mk.scene_.clearSelection()
    markers[1].setSelected(True)
    mk.delete_selected()
    after_delete = labels()
    mk.undo_stack.undo()
    check("Marker: Löschen nummeriert neu (1 2), Undo stellt 1 2 3 wieder her",
          after_delete == ["1", "2"] and sorted(labels()) == ["1", "2", "3"] and markers[1].marker_label() == "2")
    QTest.keyClick(mk, Qt.Key_C)  # zweites c: Buchstaben
    click(400, 200)
    click(500, 200)
    letters = [e.marker_label() for e in mk.elements() if e.tool == Tool.MARKER and e.marker_kind == "letter"]
    check("Marker: zweites c schaltet auf A B C, Zahlen zählen getrennt weiter", letters == ["A", "B"]
          and mk.tool == Tool.MARKER)
    QTest.keyClick(mk, Qt.Key_S, Qt.ControlModifier)
    _, loaded, _, _ = load_document(mk.document_path)
    reload_canvas = make_canvas(QPixmap(800, 400), loaded)
    check("Marker: Speichern/Laden behält Art und Nummern",
          sorted(e.marker_label() for e in reload_canvas.elements() if e.tool == Tool.MARKER)
          == ["1", "2", "3", "A", "B"])
    reload_canvas.close()
    mk.close()

    # Bild von einem anderen Monitor: größer -> verkleinert ganz sichtbar, kleiner -> 1:1 mittig;
    # gezeichnet und exportiert wird in voller Auflösung
    big = QPixmap(2200, 1000)
    big.fill(QColor("#3b4261"))
    large = make_canvas(big)
    check("großes Bild: verkleinert", abs(large.zoom() - 0.5) < 0.01)
    lview = large.viewport()
    QTest.keyClick(large, Qt.Key_S)  # Linie
    QTest.mousePress(lview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(lview, QPoint(300, 200))
    QTest.mouseRelease(lview, Qt.LeftButton, pos=QPoint(300, 200))
    line = large.elements()[-1]
    check("großes Bild: Linie in Bildpixeln", abs(line.mapToScene(line.points[1]).x()
                                                  - line.mapToScene(line.points[0]).x() - 400) < 2)
    check("großes Bild: Export in voller Auflösung", large.render_image().size() == big.size())
    small = QPixmap(400, 300)
    small.fill(QColor("#3b4261"))
    little = make_canvas(small)
    center = little.mapFromScene(little.export_rect.center())
    check("kleines Bild: 1:1 und mittig", little.zoom() == 1.0
          and (center - little.viewport().rect().center()).manhattanLength() <= 2)
    large.close()
    little.close()

    # Verlauf (Roadmap 10): jede Sitzung ein Eintrag, mit ← → blättern
    import history

    def draw_rect(c, x):
        view = c.viewport()
        QTest.keyClick(c, Qt.Key_F)
        QTest.mousePress(view, Qt.LeftButton, pos=QPoint(x, 100))
        QTest.mouseMove(view, QPoint(x + 80, 160))
        QTest.mouseRelease(view, Qt.LeftButton, pos=QPoint(x + 80, 160))

    first_bg = QPixmap(1100, 500)
    first_bg.fill(QColor("#224466"))
    first = make_canvas(first_bg)
    hdir = first.settings.history_dir
    first.start_history()
    draw_rect(first, 100)
    first.close()  # beim Beenden gespeichert
    second_bg = QPixmap(900, 400)
    second_bg.fill(QColor("#662244"))
    second = make_canvas(second_bg)
    second.start_history()
    draw_rect(second, 100)
    draw_rect(second, 300)
    second.flush_history()
    files = history.entries(hdir)
    check("Verlauf: zwei Einträge", len(files) == 2 and files[-1] == second.history_path)
    QTest.keyClick(second, Qt.Key_Left)
    check("Verlauf ←: älterer Eintrag geladen", second.history_path == files[0]
          and len(second.elements()) == 1 and second.export_size == first_bg.size()
          and second.undo_stack.count() == 0)
    draw_rect(second, 500)  # älteren Eintrag weiterbearbeiten
    QTest.keyClick(second, Qt.Key_Right)
    _, old_elems, _, _ = load_document(files[0])
    check("Verlauf: Änderung am älteren Eintrag gespeichert", len(old_elems) == 2)
    check("Verlauf →: neuerer Eintrag geladen", second.history_path == files[1]
          and len(second.elements()) == 2 and second.export_size == second_bg.size())
    QTest.keyClick(second, Qt.Key_Right)
    check("Verlauf: am Ende bleibt der neueste", second.history_path == files[1])
    second.close()
    check("Verlauf aufräumen: nur die neuesten bleiben",
          history.prune(hdir, 1) == 1 and history.entries(hdir) == [files[1]])
    empty = make_canvas(first_bg)
    empty.start_history()
    empty.close()  # nichts gezeichnet
    check("Verlauf: Screenshot ohne Änderung bleibt draußen", history.entries(hdir) == [files[1]])
    board_h = Canvas(QGuiApplication.primaryScreen(), None, board=True)
    board_h.start_history()
    check("Verlauf: nie im Whiteboard", board_h.history_path is None)
    board_h.close()

    # Whiteboard: leere Fläche, speichern, als Whiteboard wieder laden
    import export
    export.shutil.which = lambda name: None  # nie die echte Zwischenablage anfassen
    board = Canvas(QGuiApplication.primaryScreen(), None, board=True)
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
    board2 = Canvas(QGuiApplication.primaryScreen(), None, belems, board.document_path,
                             board=True, board_color=bbg)
    board2.show_window()
    check("Whiteboard neu geladen = gleicher Export", board2.render_image() == board_image)

    # Shift+Enter: speichern, absoluten Pfad kopieren; Whiteboard bleibt offen
    QTest.keyClick(board2, Qt.Key_Return, Qt.ShiftModifier)
    copied = QGuiApplication.clipboard().text()
    check("Shift+Enter: absoluter Pfad kopiert",
          copied == str(Path(board2.document_path).resolve()) and Path(copied).is_absolute()
          and board2.undo_stack.isClean() and board2.isVisible())

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
    light = Canvas(QGuiApplication.primaryScreen(), None, board=True, board_color=paper)
    light.resize(900, 500)
    light.show_window()
    QApplication.processEvents()
    lview = light.viewport()
    # Eine Farbe wählen, die auf Papier zu schwach ist (sonst bliebe sie unverändert)
    weak = next(i for i, c in enumerate(light.settings.swatches) if contrast(c, paper.name()) < LIGHT_CONTRAST)
    light.set_color(weak)
    QTest.keyClick(light, Qt.Key_F)
    QTest.mousePress(lview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(lview, QPoint(300, 200))
    QTest.mouseRelease(lview, Qt.LeftButton, pos=QPoint(300, 200))
    rect = light.elements()[0]
    base, shown = rect.color.name(), rect.pen().color().name()
    check("hell: Form abgedunkelt gezeigt", shown != base and contrast(shown, paper.name()) >= LIGHT_CONTRAST)
    check("hell: Grundfarbe gespeichert", rect.to_dict()["color"] == base)
    text = TextElement(QPointF(0, 0), QColor(base), 20, text="x")
    light.scene_.addItem(text)
    check("hell: Text abgedunkelt gezeigt", text.defaultTextColor().name() == shown and text.color.name() == base)
    check("hell: Farbleiste angepasst", light.palette_bar.colors[light.color_index].name() != light.settings.swatches[light.color_index])
    light.undo_stack.push(PropertyCommand(light.set_board_color, QColor(paper), QColor("#24283b")))
    check("dunkel: Grundfarbe gezeigt", rect.pen().color().name() == base and text.defaultTextColor().name() == base)
    light.undo_stack.undo()
    check("Undo: wieder abgedunkelt", rect.pen().color().name() == shown)

    print("\nAlles OK." if not failures else f"\n{len(failures)} Fehler.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
