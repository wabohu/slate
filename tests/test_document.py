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

    # Ausschnitt (y): nur der Ausschnitt wird ausgegeben, gespeichert bleibt alles + Rahmen
    cr = make_canvas(QPixmap(800, 400))
    cview = cr.viewport()

    def at(x, y):  # Bildpixel -> Mausposition (das Bild steht mittig im größeren Fenster)
        return cr.mapFromScene(QPointF(x, y))
    QTest.keyClick(cr, Qt.Key_Y)
    QTest.mousePress(cview, Qt.LeftButton, pos=at(100, 50))
    QTest.mouseMove(cview, at(400, 250))
    QTest.mouseRelease(cview, Qt.LeftButton, pos=at(400, 250))
    check("Ausschnitt: Ausgabe nur der Ausschnitt (300x200), Auswahl danach beendet",
          cr.render_image().size().toTuple() == (300, 200) and not cr.cropping and cr.crop_rect is not None)
    QTest.keyClick(cr, Qt.Key_S, Qt.ControlModifier)
    saved_png = QImage(str(cr.document_path))
    bg_full, _, _, _, saved_crop = load_document(cr.document_path, with_crop=True)
    check("Ausschnitt: Datei zeigt den Ausschnitt, enthält ganzen Screenshot und Rahmen",
          saved_png.size().toTuple() == (300, 200) and bg_full.size().toTuple() == (800, 400)
          and saved_crop is not None and saved_crop.size().toTuple() == (300.0, 200.0))
    QTest.keyClick(cr, Qt.Key_Y)
    QTest.keyClick(cr, Qt.Key_Escape)  # Esc während der Auswahl: Ausschnitt aufheben
    removed = cr.crop_rect is None and cr.render_image().size().toTuple() == (800, 400)
    cr.undo_stack.undo()
    check("Ausschnitt: Esc in der Auswahl hebt auf, Undo stellt ihn wieder her",
          removed and cr.crop_rect is not None)
    QTest.keyClick(cr, Qt.Key_Y)
    QTest.mousePress(cview, Qt.LeftButton, pos=at(10, 10))
    QTest.mouseRelease(cview, Qt.LeftButton, pos=at(12, 11))  # winzig: gilt als Klick
    check("Ausschnitt: winziger Rahmen ändert nichts",
          cr.crop_rect is not None and cr.crop_rect.width() == 300 and not cr.cropping)

    def crop_drag(x1, y1, x2, y2):  # y, dann in Bildpixeln ziehen
        QTest.keyClick(cr, Qt.Key_Y)
        QTest.mousePress(cview, Qt.LeftButton, pos=at(x1, y1))
        QTest.mouseMove(cview, at(x2, y2))
        QTest.mouseRelease(cview, Qt.LeftButton, pos=at(x2, y2))
        r = cr.crop_rect
        return (round(r.x()), round(r.y()), round(r.width()), round(r.height()))
    # Ausschnitt ist jetzt (100, 50, 300, 200)
    corner = crop_drag(400, 250, 500, 300)   # Griff unten rechts
    edge = crop_drag(100, 175, 150, 175)     # Griff linke Kante (nur waagerecht)
    moved = crop_drag(300, 150, 320, 170)    # innen: verschieben
    fresh = crop_drag(600, 320, 700, 380)    # außen: neu aufziehen
    check(f"Ausschnitt anpassen: Ecke, Kante, verschieben, außen neu ({corner} {edge} {moved} {fresh})",
          corner == (100, 50, 400, 250) and edge == (150, 50, 350, 250) and moved == (170, 70, 350, 250)
          and fresh == (600, 320, 100, 60))
    cr.undo_stack.undo()
    check("Ausschnitt anpassen: Undo geht schrittweise zurück",
          (round(cr.crop_rect.x()), round(cr.crop_rect.width())) == (170, 350))
    cr.close()

    # Mehrfachauswahl: Strg+A, Shift+Klick, Auswahlrahmen; Farbe, Größe, Verschieben, Löschen
    # wirken auf alle, jeweils ein Undo-Schritt
    ms = make_canvas(QPixmap(800, 400))
    mv = ms.viewport()

    def mp(x, y):
        return ms.mapFromScene(QPointF(x, y))

    def drag(x1, y1, x2, y2, mods=Qt.NoModifier):
        QTest.mousePress(mv, Qt.LeftButton, mods, mp(x1, y1))
        QTest.mouseMove(mv, mp(x2, y2))
        QTest.mouseRelease(mv, Qt.LeftButton, mods, mp(x2, y2))
    ms.set_tool(Tool.RECT)
    for x in (50, 250, 450):
        drag(x, 50, x + 100, 150)
    rects = ms.elements()
    QTest.keyClick(ms, Qt.Key_A, Qt.ControlModifier)
    check("Strg+A wählt alles aus", ms.tool == Tool.SELECT and len(ms.selected_elements()) == 3)
    steps_before = ms.undo_stack.count()
    ms.set_color((ms.color_index + 1) % len(ms.settings.colors))
    all_colored = len({r.color.name() for r in rects}) == 1 and rects[0].color == ms.pen_color
    ms.undo_stack.undo()
    check("Farbe auf alle, ein Undo-Schritt", all_colored and ms.undo_stack.count() == steps_before + 1
          and rects[0].color != ms.pen_color)
    ms.undo_stack.redo()
    ms.set_size(3)
    check("Größe auf alle", all(r.width == ms.pen_width for r in rects))
    QTest.mouseClick(mv, Qt.LeftButton, Qt.NoModifier, mp(50, 100))  # Klick auf Rand: nur dieses
    QTest.mouseClick(mv, Qt.LeftButton, Qt.ShiftModifier, mp(450, 100))  # Shift: dazu
    check("Klick wählt eins, Shift+Klick nimmt dazu", ms.selected_elements() == [rects[0], rects[2]])
    QTest.mouseClick(mv, Qt.LeftButton, Qt.ShiftModifier, mp(450, 100))  # Shift: wieder heraus
    check("Shift+Klick nimmt wieder heraus", ms.selected_elements() == [rects[0]])
    drag(20, 20, 400, 200)  # Rahmen um die ersten beiden
    check("Auswahlrahmen wählt, was ganz darin liegt", ms.selected_elements() == rects[:2])
    before = [QPointF(r.pos()) for r in rects]
    drag(250, 100, 280, 120)  # eins der ausgewählten anfassen: beide wandern
    moved = [r.pos() - b for r, b in zip(rects, before)]
    check("Ziehen verschiebt alle ausgewählten", moved[0] == moved[1] == QPointF(30, 20) and moved[2] == QPointF(0, 0))
    ms.undo_stack.undo()
    check("Verschieben: ein Undo-Schritt für alle", all(r.pos() == b for r, b in zip(rects, before)))
    QTest.keyClick(ms, Qt.Key_L)
    QTest.keyClick(ms, Qt.Key_L)
    hjkl = [r.pos().x() - b.x() for r, b in zip(rects, before)]
    ms.undo_stack.undo()
    check("hjkl verschiebt alle, Schritte zusammengefasst", hjkl[0] == hjkl[1] > 0 and hjkl[2] == 0
          and all(r.pos() == b for r, b in zip(rects, before)))
    ms.delete_selected()
    gone = len(ms.elements()) == 1
    ms.undo_stack.undo()
    check("Löschen aller ausgewählten, ein Undo-Schritt", gone and len(ms.elements()) == 3)
    ms.close()

    # Vorder-/Hintergrund: Strg+↑/↓ ein Schritt, Strg+Shift+↑/↓ ganz; Undo; Löschen+Undo behält Platz
    zo = make_canvas(QPixmap(800, 400))
    zv = zo.viewport()
    zo.set_tool(Tool.RECT)
    for x in (50, 150, 250, 350):
        QTest.mousePress(zv, Qt.LeftButton, Qt.NoModifier, zo.mapFromScene(QPointF(x, 50)))
        QTest.mouseMove(zv, zo.mapFromScene(QPointF(x + 200, 250)))
        QTest.mouseRelease(zv, Qt.LeftButton, Qt.NoModifier, zo.mapFromScene(QPointF(x + 200, 250)))
    a, b, c, d = zo.elements()

    def order():
        return "".join("abcd"[[a, b, c, d].index(e)] for e in zo.elements())
    zo.set_tool(Tool.SELECT)
    a.setSelected(True)
    QTest.keyClick(zo, Qt.Key_Up, Qt.ControlModifier)
    one_up = order()
    QTest.keyClick(zo, Qt.Key_Up, Qt.ControlModifier | Qt.ShiftModifier)
    top = order()
    zo.undo_stack.undo()
    zo.undo_stack.undo()
    check(f"Strg+↑ ein Schritt ({one_up}), Strg+Shift+↑ ganz nach vorne ({top}), Undo",
          one_up == "bacd" and top == "bcda" and order() == "abcd")
    zo.scene_.clearSelection()
    c.setSelected(True)
    d.setSelected(True)
    QTest.keyClick(zo, Qt.Key_Down, Qt.ControlModifier | Qt.ShiftModifier)
    check(f"Mehrere ganz nach hinten, Reihenfolge untereinander bleibt ({order()})", order() == "cdab")
    zo.undo_stack.undo()
    zo.scene_.clearSelection()
    b.setSelected(True)
    zo.delete_selected()
    zo.undo_stack.undo()
    check(f"Gelöschtes per Undo zurück an seinen Platz ({order()})", order() == "abcd")
    QTest.keyClick(zo, Qt.Key_S, Qt.ControlModifier)
    b.setSelected(True)
    QTest.keyClick(zo, Qt.Key_Up, Qt.ControlModifier | Qt.ShiftModifier)
    QTest.keyClick(zo, Qt.Key_S, Qt.ControlModifier)
    _, saved, _, _ = load_document(zo.document_path)
    check("Reihenfolge wird gespeichert", [e.id for e in saved] == [a.id, c.id, d.id, b.id])
    zo.close()

    # Kopieren/Einfügen/Duplizieren (Qt-Zwischenablage, nie die echte: xclip abgeschaltet)
    import export as _export
    _export.shutil.which = lambda name: None
    cp = make_canvas(QPixmap(800, 400))
    cpv = cp.viewport()
    cp.set_tool(Tool.RECT)
    for x in (50, 300):
        QTest.mousePress(cpv, Qt.LeftButton, Qt.NoModifier, cp.mapFromScene(QPointF(x, 50)))
        QTest.mouseMove(cpv, cp.mapFromScene(QPointF(x + 100, 150)))
        QTest.mouseRelease(cpv, Qt.LeftButton, Qt.NoModifier, cp.mapFromScene(QPointF(x + 100, 150)))
    cp.set_tool(Tool.MARKER)
    QTest.mouseClick(cpv, Qt.LeftButton, Qt.NoModifier, cp.mapFromScene(QPointF(500, 300)))
    originals = cp.elements()
    QTest.keyClick(cp, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClick(cp, Qt.Key_C, Qt.ControlModifier)
    QTest.keyClick(cp, Qt.Key_V, Qt.ControlModifier)
    pasted = [e for e in cp.elements() if e not in originals]
    check("Strg+C/Strg+V: Kopien mit neuen IDs, danach ausgewählt, Marker zählt weiter",
          len(pasted) == 3 and not {e.id for e in pasted} & {e.id for e in originals}
          and cp.selected_elements() == pasted
          and [e.marker_label() for e in pasted if e.tool == Tool.MARKER] == ["2"])
    cp.undo_stack.undo()
    check("Einfügen: ein Undo-Schritt", cp.elements() == originals)
    cp.scene_.clearSelection()
    originals[0].setSelected(True)
    QTest.keyClick(cp, Qt.Key_D, Qt.ControlModifier)
    dup = [e for e in cp.elements() if e not in originals]
    offset = dup[0].pos() - originals[0].pos() if dup else QPointF()
    check("Strg+D: verdoppelt, leicht versetzt", len(dup) == 1 and offset.x() > 0 and offset == QPointF(offset.x(), offset.x()))
    wb = Canvas(QGuiApplication.primaryScreen(), None, board=True)
    wb.resize(900, 500)
    wb.show_window()
    QApplication.processEvents()
    blur_dict = dict(originals[0].to_dict(), tool="blur")
    wb.insert_copies([originals[0].to_dict(), blur_dict], target=QPointF(0, 0))
    check("Einfügen im Whiteboard: Unschärfe wird weggelassen",
          [e.tool for e in wb.elements()] == [Tool.RECT])
    wb.undo_stack.setClean()  # sonst fragt das Whiteboard beim Schließen nach (Dialog ohne Bildschirm)
    wb.close()
    cp.close()

    # Bild-Elemente: Ausschnitt mit Markierungen bearbeitbar ins Whiteboard, fremde Bilder einfügen
    from PySide6.QtCore import QByteArray, QMimeData, QRectF
    from elements import ImageElement
    from export import png_bytes
    shot = make_canvas(QPixmap(800, 400))
    sv = shot.viewport()
    shot.set_tool(Tool.MARKER)
    QTest.mouseClick(sv, Qt.LeftButton, Qt.NoModifier, shot.mapFromScene(QPointF(200, 150)))
    QTest.mouseClick(sv, Qt.LeftButton, Qt.NoModifier, shot.mapFromScene(QPointF(700, 350)))  # außerhalb
    shot.set_crop(QRectF(100, 50, 300, 200))
    shot.copy_image()  # Strg+C ohne Auswahl / Enter
    # Wie xclip: die PNG-Bytes unverändert in der Zwischenablage (Qt allein kodiert neu)
    clip = QMimeData()
    clip.setData("image/png", QByteArray(png_bytes(shot.render_image())))
    QGuiApplication.clipboard().setMimeData(clip)
    wb2 = Canvas(QGuiApplication.primaryScreen(), None, board=True)
    wb2.resize(900, 500)
    wb2.show_window()
    QApplication.processEvents()
    wb2.paste_elements()
    kinds = [type(e).__name__ for e in wb2.elements()]
    image = next((e for e in wb2.elements() if isinstance(e, ImageElement)), None)
    check(f"Ausschnitt ins Whiteboard: Bild unten, Marker darin bearbeitbar ({kinds})",
          kinds == ["ImageElement", "ShapeElement"] and image.size.toTuple() == (300.0, 200.0))
    foreign = QImage(120, 80, QImage.Format_RGB32)
    foreign.fill(QColor("orange"))
    QGuiApplication.clipboard().setImage(foreign)
    wb2.paste_elements()
    pasted = wb2.selected_elements()
    check("fremdes Bild: ein Bild-Element in Originalgröße",
          len(pasted) == 1 and isinstance(pasted[0], ImageElement) and pasted[0].size.toTuple() == (120.0, 80.0))
    start = pasted[0].geometry()
    corner = pasted[0].mapToScene(pasted[0].handle_points()[2])
    pasted[0].drag_handle(2, corner + QPointF(60, 0), start)
    check("Bild: Griff ändert die Größe, Seitenverhältnis bleibt",
          abs(pasted[0].size.width() / pasted[0].size.height() - 1.5) < 0.01 and pasted[0].size.width() > 120)
    QTest.keyClick(wb2, Qt.Key_S, Qt.ControlModifier)
    _, saved_board, _, _ = load_document(wb2.document_path)
    check("Bild-Elemente werden gespeichert und geladen",
          sum(isinstance(e, ImageElement) for e in saved_board) == 2)
    wb2.undo_stack.setClean()
    wb2.close()
    shot.close()

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
    check("Whiteboard gespeichert (_board)", board.document_path and "_board" in board.document_path.stem)  # auch _board_2 bei gleicher Sekunde
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
