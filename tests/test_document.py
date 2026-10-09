#!/usr/bin/env python3
"""Save/load test: draw a scene, Ctrl+S, load again, compare pixel by pixel;
plus the whiteboard (save, load as whiteboard, export of the used area).

    python tests/test_document.py

Uses the scene and the isolated environment from regress.py (empty HOME,
offscreen platform). Exit code 0 = all ok, 1 = failures.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regress  # noqa: E402  (sets HOME, config and QT_QPA_PLATFORM)

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFontMetricsF, QGuiApplication, QImage, QPainter, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

failures = []


def check(name, condition):
    print(f"{'OK  ' if condition else 'FAIL  '}  {name}")
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

    # Mixins of the Canvas (docs/plan-aufteilung.md): no method may be in two classes,
    # otherwise one silently hides the other
    parts = [c for c in Canvas.__mro__ if c.__module__ not in ("builtins",) and
             not c.__module__.startswith(("PySide6", "Shiboken"))]
    names = [{n for n in c.__dict__ if not n.startswith("__")} for c in parts]
    clashes = {n for i, a in enumerate(names) for b in names[i + 1:] for n in a & b}
    check(f"Canvas mixins without duplicate methods ({', '.join(c.__name__ for c in parts)})", not clashes)

    background = QPixmap(1100, 500)
    background.fill(QColor("#3b4261"))
    canvas = make_canvas(background)
    regress.draw_scene(canvas, canvas.viewport())
    out = Path(default_output_dir())

    def drawings():  # saved drawings, without export PNGs
        return sorted(p for p in out.glob("slate_*.png") if not p.stem.endswith("_export"))

    QTest.keyClick(canvas, Qt.Key_S, Qt.ControlModifier)
    QTest.keyClick(canvas, Qt.Key_S, Qt.ControlModifier)
    saved = drawings()
    check("Ctrl+S twice = one file", len(saved) == 1)
    QTest.keyClick(canvas, Qt.Key_E, Qt.ControlModifier)
    exports = sorted(out.glob("*_export.png"))
    check("Ctrl+E = additional export PNG", len(exports) == 1)

    path = saved[0]
    rendered = canvas.render_image()
    check("saved PNG shows the drawing",
          QImage(str(path)).convertToFormat(rendered.format()) == rendered)
    check("export PNG without editing data", not QImage(str(exports[0])).text("slate"))

    bg, elements, is_drawing, message = load_document(path)
    check(f"loaded as a drawing ({message})", is_drawing and len(elements) == len(canvas.elements()))
    check("elements identical",
          [e.to_dict() for e in elements] == [e.to_dict() for e in canvas.elements()])
    reopened = make_canvas(QPixmap.fromImage(bg), elements, path)
    check("loaded again = pixel identical", reopened.render_image() == rendered)
    check("undo empty after loading", reopened.undo_stack.count() == 0)

    # Keep working: move an element, save, load again
    QTest.keyClick(reopened, Qt.Key_W)
    view = reopened.viewport()
    QTest.mouseClick(view, Qt.LeftButton, pos=QPoint(30, 120))       # blue line
    moved = reopened.selected_element()
    check("line selectable after loading", moved is not None)
    QTest.mousePress(view, Qt.LeftButton, pos=QPoint(30, 120))
    QTest.mouseMove(view, QPoint(130, 220))
    QTest.mouseRelease(view, Qt.LeftButton, pos=QPoint(130, 220))
    QTest.keyClick(reopened, Qt.Key_S, Qt.ControlModifier)
    check("saving overwrites the same file", drawings() == [path])
    _, again, _, _ = load_document(path)
    match = [e for e in again if e.id == moved.id]
    check("move saved", match and match[0].pos() == moved.pos())

    # Mouse pointer: crosshair without center, circle = stroke width, pen color; select/pointing: arrow
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
    check("pointer: grows with the stroke width, center free, pen color",
          big_cursor.width() > small_cursor.width() and center.alpha() == 0 and has_pen)
    cur.set_tool(Tool.SELECT)
    select_cursor = cur.viewport().cursor()
    arrow_select = select_cursor.shape() == Qt.BitmapCursor and select_cursor.hotSpot().x() > 0
    cur.set_tool(Tool.RECT)
    cur.toggle_pointer("spotlight")
    hidden_pointer = cur.viewport().cursor().shape() == Qt.BlankCursor
    cur.set_tool(Tool.LINE)
    check("pointer: own arrow in the select tool, hidden while pointing, tool change ends pointing",
          arrow_select and hidden_pointer and cur.pointer_mode is None
          and cur.viewport().cursor().shape() == Qt.BitmapCursor)
    cur.close()

    # Blur (z): pixelates the screenshot below; burned into the raw image when saving
    from PySide6.QtGui import QPainter as _QPainter
    stripes = QImage(800, 400, QImage.Format_RGB32)
    stripes.fill(QColor("white"))
    sp = _QPainter(stripes)
    for x in range(0, 800, 4):  # fine vertical stripes: uniformly gray after pixelating
        sp.fillRect(x, 0, 2, 400, QColor("black"))
    sp.end()
    blur_canvas = make_canvas(QPixmap.fromImage(stripes))
    bview = blur_canvas.viewport()
    QTest.keyClick(blur_canvas, Qt.Key_Z)
    blur_canvas.set_size(2)  # level 3: 24 px blocks
    QTest.mousePress(bview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(bview, QPoint(300, 250))
    QTest.mouseRelease(bview, Qt.LeftButton, pos=QPoint(300, 250))
    blurs = [e for e in blur_canvas.elements() if e.tool == Tool.BLUR]
    shown = blur_canvas.render_image()

    def stripe_contrast(img, y, x0, x1):
        values = [img.pixelColor(x, y).lightness() for x in range(x0, x1)]
        return max(values) - min(values)
    check("blur: one element, area pixelated, outside unchanged",
          len(blurs) == 1 and stripe_contrast(shown, 150, 130, 150) < 40 and stripe_contrast(shown, 350, 130, 150) > 200)
    QTest.keyClick(blur_canvas, Qt.Key_S, Qt.ControlModifier)
    saved_bg, saved_elems, _, _ = load_document(blur_canvas.document_path)
    check("blur: saved raw image is pixelated there (burned in), element stays",
          stripe_contrast(saved_bg, 150, 130, 150) < 40 and stripe_contrast(saved_bg, 350, 130, 150) > 200
          and [e.tool for e in saved_elems] == [Tool.BLUR])
    check("blur: in the running tool the raw image stays unchanged",
          stripe_contrast(blur_canvas.background_image, 150, 130, 150) > 200)
    blur_canvas.close()

    # Marker (c): click = circle, drag = circle with pointer line; renumber, letters
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
    check("marker: 1 2 3, click without line, drag with line",
          labels() == ["1", "2", "3"] and markers[0].points[0] == markers[0].points[1]
          and markers[1].points[0] != markers[1].points[1])
    mk.scene_.clearSelection()
    markers[1].setSelected(True)
    mk.delete_selected()
    after_delete = labels()
    mk.undo_stack.undo()
    check("marker: deleting renumbers (1 2), undo restores 1 2 3",
          after_delete == ["1", "2"] and sorted(labels()) == ["1", "2", "3"] and markers[1].marker_label() == "2")
    QTest.keyClick(mk, Qt.Key_C)  # second c: letters
    click(400, 200)
    click(500, 200)
    letters = [e.marker_label() for e in mk.elements() if e.tool == Tool.MARKER and e.marker_kind == "letter"]
    check("marker: second c switches to A B C, numbers count separately", letters == ["A", "B"]
          and mk.tool == Tool.MARKER)
    QTest.keyClick(mk, Qt.Key_S, Qt.ControlModifier)
    _, loaded, _, _ = load_document(mk.document_path)
    reload_canvas = make_canvas(QPixmap(800, 400), loaded)
    check("marker: save/load keeps kind and numbers",
          sorted(e.marker_label() for e in reload_canvas.elements() if e.tool == Tool.MARKER)
          == ["1", "2", "3", "A", "B"])
    reload_canvas.close()
    mk.close()

    # Crop (x): only the crop is output, everything + frame is saved
    gray = QPixmap(800, 400)
    gray.fill(QColor("#808080"))  # not white: clearing (Del) must be visible
    cr = make_canvas(gray)
    cview = cr.viewport()

    def at(x, y):  # image pixels -> mouse position (the image is centered in the larger window)
        return cr.mapFromScene(QPointF(x, y))
    QTest.keyClick(cr, Qt.Key_X)
    QTest.mousePress(cview, Qt.LeftButton, pos=at(100, 50))
    QTest.mouseMove(cview, at(400, 250))
    QTest.mouseRelease(cview, Qt.LeftButton, pos=at(400, 250))
    check("crop: output only the crop (300x200), selection ended afterwards",
          cr.render_image().size().toTuple() == (300, 200) and not cr.cropping and cr.crop_rect is not None)
    QTest.keyClick(cr, Qt.Key_S, Qt.ControlModifier)
    saved_png = QImage(str(cr.document_path))
    bg_full, _, _, _, saved_crop = load_document(cr.document_path, with_crop=True)
    check("crop: file shows the crop, contains the whole screenshot and the frame",
          saved_png.size().toTuple() == (300, 200) and bg_full.size().toTuple() == (800, 400)
          and saved_crop is not None and saved_crop.size().toTuple() == (300.0, 200.0))
    QTest.keyClick(cr, Qt.Key_X)
    QTest.keyClick(cr, Qt.Key_Escape)  # Esc during the selection: remove the crop
    removed = cr.crop_rect is None and cr.render_image().size().toTuple() == (800, 400)
    cr.undo_stack.undo()
    check("crop: Esc in the selection removes it, undo restores it",
          removed and cr.crop_rect is not None)
    QTest.keyClick(cr, Qt.Key_X)
    QTest.mousePress(cview, Qt.LeftButton, pos=at(10, 10))
    QTest.mouseRelease(cview, Qt.LeftButton, pos=at(12, 11))  # tiny: counts as a click
    check("crop: tiny frame changes nothing",
          cr.crop_rect is not None and cr.crop_rect.width() == 300 and not cr.cropping)

    def crop_drag(x1, y1, x2, y2):  # x, then drag in image pixels
        QTest.keyClick(cr, Qt.Key_X)
        QTest.mousePress(cview, Qt.LeftButton, pos=at(x1, y1))
        QTest.mouseMove(cview, at(x2, y2))
        QTest.mouseRelease(cview, Qt.LeftButton, pos=at(x2, y2))
        r = cr.crop_rect
        return (round(r.x()), round(r.y()), round(r.width()), round(r.height()))
    # Crop is now (100, 50, 300, 200)
    corner = crop_drag(400, 250, 500, 300)   # bottom right handle
    edge = crop_drag(100, 175, 150, 175)     # left edge handle (horizontal only)
    moved = crop_drag(300, 150, 320, 170)    # inside: move
    fresh = crop_drag(600, 320, 700, 380)    # outside: draw a new one
    check(f"adjust crop: corner, edge, move, new outside ({corner} {edge} {moved} {fresh})",
          corner == (100, 50, 400, 250) and edge == (150, 50, 350, 250) and moved == (170, 70, 350, 250)
          and fresh == (600, 320, 100, 60))
    cr.undo_stack.undo()
    check("adjust crop: undo goes back step by step",
          (round(cr.crop_rect.x()), round(cr.crop_rect.width())) == (170, 350))

    # Select tool: a click on the edge selects the crop, then adjust it as often as needed
    def select_drag(x1, y1, x2, y2):
        QTest.mousePress(cview, Qt.LeftButton, pos=at(x1, y1))
        QTest.mouseMove(cview, at(x2, y2))
        QTest.mouseRelease(cview, Qt.LeftButton, pos=at(x2, y2))
        r = cr.crop_rect
        return (round(r.x()), round(r.y()), round(r.width()), round(r.height()))
    QTest.keyClick(cr, Qt.Key_W)  # crop is (170, 70, 350, 250)
    by_edge = select_drag(170, 200, 190, 210)        # left edge: move
    first = select_drag(540, 330, 560, 340)          # bottom right handle
    second = select_drag(560, 340, 580, 350)         # and once more
    check(f"select tool: edge selects and moves the crop, handles adjust it repeatedly "
          f"({by_edge} {first} {second})",
          by_edge == (190, 80, 350, 250) and first == (190, 80, 370, 260) and second == (190, 80, 390, 270)
          and cr.crop_selected)
    select_drag(300, 200, 301, 200)  # click inside: belongs to the elements, deselects the crop
    inside_free = not cr.crop_selected and cr.crop_rect.width() == 390
    select_drag(190, 200, 190, 200)
    QTest.keyClick(cr, Qt.Key_Escape)  # Esc on the selected crop: remove it, do not quit
    esc_ok = cr.crop_rect is None and not cr.crop_selected and cr.isVisible()
    cr.undo_stack.undo()
    inside, outside = QPointF(300, 200), QPointF(50, 30)  # image pixels (no scaling here)
    before = (cr.background_image.pixel(inside.toPoint()), cr.background_image.pixel(outside.toPoint()))
    # Del clears in the color around the area: gray page, some "text" inside, a stripe of
    # another color on the edge must not win
    painter = QPainter(cr.background_image)
    painter.fillRect(QRectF(250, 150, 100, 20), QColor("black"))   # content inside
    painter.fillRect(QRectF(185, 100, 10, 60), QColor("#2040c0"))  # crosses the left edge
    painter.end()
    cr.set_background_image(cr.background_image)
    before = (cr.background_image.pixel(inside.toPoint()), cr.background_image.pixel(outside.toPoint()))
    select_drag(190, 200, 190, 200)
    QTest.keyClick(cr, Qt.Key_Delete)  # Del: clear the area, crop gone, one undo step
    saved = cr.background_to_save()
    gray_fill = QColor(saved.pixel(inside.toPoint())) == QColor("#808080") \
        and QColor(saved.pixel(QPoint(260, 160))) == QColor("#808080")
    cleared = cr.crop_rect is None and gray_fill and saved.pixel(outside.toPoint()) == before[1]
    cr.undo_stack.undo()
    restored = cr.crop_rect is not None and cr.background_image.pixel(inside.toPoint()) == before[0]
    QTest.keyClick(cr, Qt.Key_X)  # x shows the same handles: Del clears there too
    QTest.keyClick(cr, Qt.Key_Delete)
    cleared_in_x = cr.crop_rect is None and not cr.cropping \
        and QColor(cr.background_image.pixel(QPoint(260, 160))) == QColor("#808080")
    cr.undo_stack.undo()
    cr.set_tool(Tool.FREEHAND)  # another tool, crop not selected, nothing selected: Del clears too
    QTest.keyClick(cr, Qt.Key_Backspace)
    cleared_unselected = cr.crop_rect is None \
        and QColor(cr.background_image.pixel(QPoint(260, 160))) == QColor("#808080")
    check("select tool: inside stays free, Esc removes the crop, Del clears the area "
          "(also with x and without selecting the crop; one undo step restores both)",
          inside_free and esc_ok and cleared and restored and cleared_in_x and cleared_unselected)
    cr.close()

    # Multi-selection: Ctrl+A, Shift+click, rubber band; color, size, move, delete
    # apply to all, one undo step each
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
    check("Ctrl+A selects everything", ms.tool == Tool.SELECT and len(ms.selected_elements()) == 3)
    steps_before = ms.undo_stack.count()
    ms.set_color((ms.color_index + 1) % len(ms.settings.colors))
    all_colored = len({r.color.name() for r in rects}) == 1 and rects[0].color == ms.pen_color
    ms.undo_stack.undo()
    check("color on all, one undo step", all_colored and ms.undo_stack.count() == steps_before + 1
          and rects[0].color != ms.pen_color)
    ms.undo_stack.redo()
    ms.set_size(3)
    check("size on all", all(r.width == ms.pen_width for r in rects))
    QTest.mouseClick(mv, Qt.LeftButton, Qt.NoModifier, mp(50, 100))  # click on the edge: only this one
    QTest.mouseClick(mv, Qt.LeftButton, Qt.ShiftModifier, mp(450, 100))  # Shift: add
    check("click selects one, Shift+click adds", ms.selected_elements() == [rects[0], rects[2]])
    QTest.mouseClick(mv, Qt.LeftButton, Qt.ShiftModifier, mp(450, 100))  # Shift: remove again
    check("Shift+click removes again", ms.selected_elements() == [rects[0]])
    drag(20, 20, 400, 200)  # rubber band around the first two
    check("rubber band selects what lies completely inside", ms.selected_elements() == rects[:2])
    before = [QPointF(r.pos()) for r in rects]
    drag(250, 100, 280, 120)  # grab one of the selected: both move
    moved = [r.pos() - b for r, b in zip(rects, before)]
    check("dragging moves all selected", moved[0] == moved[1] == QPointF(30, 20) and moved[2] == QPointF(0, 0))
    ms.undo_stack.undo()
    check("move: one undo step for all", all(r.pos() == b for r, b in zip(rects, before)))
    QTest.keyClick(ms, Qt.Key_L)
    QTest.keyClick(ms, Qt.Key_L)
    hjkl = [r.pos().x() - b.x() for r, b in zip(rects, before)]
    ms.undo_stack.undo()
    check("hjkl moves all, steps merged", hjkl[0] == hjkl[1] > 0 and hjkl[2] == 0
          and all(r.pos() == b for r, b in zip(rects, before)))
    ms.delete_selected()
    gone = len(ms.elements()) == 1
    ms.undo_stack.undo()
    check("deleting all selected, one undo step", gone and len(ms.elements()) == 3)
    ms.close()

    # Rotate (Q / Shift+Q): around the middle, presses merged into one undo step, groups together,
    # blur and markers left out, handles on rotated elements, saving keeps the rotation
    from elements import ImageElement as _ImageElement
    plain_bg = QPixmap(800, 400)
    plain_bg.fill(QColor("#3b4261"))  # unfilled pixmaps contain random memory
    ro = make_canvas(plain_bg)
    rv = ro.viewport()

    def rdrag(x1, y1, x2, y2):
        QTest.mousePress(rv, Qt.LeftButton, Qt.NoModifier, ro.mapFromScene(QPointF(x1, y1)))
        QTest.mouseMove(rv, ro.mapFromScene(QPointF(x2, y2)))
        QTest.mouseRelease(rv, Qt.LeftButton, Qt.NoModifier, ro.mapFromScene(QPointF(x2, y2)))

    def mid(item):
        return item.mapToScene(item.boundingRect().center())

    def near(a, b, tol=0.5):
        return abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol
    ro.set_tool(Tool.RECT)
    rdrag(100, 100, 200, 160)
    rdrag(300, 100, 400, 160)
    first, second = ro.elements()
    ro.set_tool(Tool.SELECT)
    first.setSelected(True)
    center_before, steps_before = mid(first), ro.undo_stack.count()
    for _ in range(3):
        QTest.keyClick(ro, Qt.Key_Q, Qt.ShiftModifier)
    check(f"Shift+Q x3: 15° clockwise around the middle, one undo step ({first.rotation()})",
          abs(first.rotation() - 15) < 1e-6 and near(mid(first), center_before)
          and ro.undo_stack.count() == steps_before + 1)
    ro.undo_stack.undo()
    QTest.keyClick(ro, Qt.Key_Q)
    check(f"undo back to 0°, then Q: 5° counterclockwise ({first.rotation()})",
          abs(first.rotation() - 355) < 1e-6 and near(mid(first), center_before))
    ro.undo_stack.undo()
    first.setSelected(True)
    second.setSelected(True)
    group_mid = (mid(first) + mid(second)) / 2
    ro.rotate_selected(90)
    check("group: turns around the common middle, both rotated",
          near((mid(first) + mid(second)) / 2, group_mid) and near(mid(first), QPointF(group_mid.x(), group_mid.y() - 100))
          and first.rotation() == second.rotation() == 90)
    ro.undo_stack.undo()
    ro.scene_.clearSelection()
    ro.set_tool(Tool.MARKER)
    QTest.mouseClick(rv, Qt.LeftButton, Qt.NoModifier, ro.mapFromScene(QPointF(600, 300)))
    marker = ro.elements()[-1]
    ro.set_tool(Tool.SELECT)
    marker.setSelected(True)
    ro.rotate_selected(30)
    check("marker is left out", marker.rotation() == 0)
    pixels = QImage(120, 60, QImage.Format_RGB32)
    pixels.fill(QColor("orange"))
    image = _ImageElement(QPointF(100, 250), pixels)
    ro.scene_.addItem(image)
    image.setRotation(90)
    fixed = image.mapToScene(image.handle_points()[0])
    start = image.geometry()
    image.drag_handle(2, image.mapToScene(QPointF(240, 120)), start)
    check(f"rotated image: handle doubles the size, opposite corner stays ({image.size.toTuple()})",
          image.size.toTuple() == (240.0, 120.0) and near(image.mapToScene(image.handle_points()[0]), fixed))
    label = TextElement(QPointF(500, 100), QColor("red"), 20, text="rotated")
    ro.scene_.addItem(label)
    label.setRotation(45)
    fixed = label.mapToScene(label.handle_points()[0])
    corner = label.mapToScene(label.handle_points()[2])
    label.drag_handle(2, fixed + (corner - fixed) * 2, label.geometry(), (6, 300))
    check(f"rotated text: handle scales the font, opposite corner stays ({label.font_size})",
          label.font_size > 30 and near(label.mapToScene(label.handle_points()[0]), fixed, 1.0))
    first.setSelected(True)
    ro.rotate_selected(30)
    rotated_image = ro.render_image()
    QTest.keyClick(ro, Qt.Key_S, Qt.ControlModifier)
    rbg, relems, _, _ = load_document(ro.document_path)
    reloaded = make_canvas(QPixmap.fromImage(rbg), relems, ro.document_path)
    check("rotation is saved and loaded (pixel identical)",
          sorted(round(e.rotation()) for e in relems) == [0, 0, 30, 45, 90]
          and reloaded.render_image() == rotated_image)
    reloaded.close()
    ro.close()

    # Rotate handle: drag it a quarter turn around the middle, one undo step; lines have none
    rh = make_canvas(plain_bg)
    hv = rh.viewport()
    rh.set_tool(Tool.RECT)
    QTest.mousePress(hv, Qt.LeftButton, Qt.NoModifier, rh.mapFromScene(QPointF(100, 100)))
    QTest.mouseMove(hv, rh.mapFromScene(QPointF(300, 200)))
    QTest.mouseRelease(hv, Qt.LeftButton, Qt.NoModifier, rh.mapFromScene(QPointF(300, 200)))
    box = rh.elements()[0]
    rh.set_tool(Tool.SELECT)
    box.setSelected(True)
    knob = rh.rotate_handle(box)[0]
    middle, steps = mid(box), rh.undo_stack.count()
    QTest.mousePress(hv, Qt.LeftButton, Qt.NoModifier, rh.mapFromScene(knob))
    QTest.mouseMove(hv, rh.mapFromScene(middle + QPointF(100, -100)))
    QTest.mouseMove(hv, rh.mapFromScene(middle + QPointF(150, 0)))  # from above to the right: +90°
    QTest.mouseRelease(hv, Qt.LeftButton, Qt.NoModifier, rh.mapFromScene(middle + QPointF(150, 0)))
    turned_by_mouse = box.rotation()
    check(f"rotate handle: dragged to the right = 90° around the middle, one undo step ({turned_by_mouse})",
          abs(turned_by_mouse - 90) < 1 and near(mid(box), middle) and rh.undo_stack.count() == steps + 1)
    rh.undo_stack.undo()
    check("rotate handle: undo back to 0°", box.rotation() == 0 and near(mid(box), middle))
    rh.set_tool(Tool.LINE)
    QTest.mousePress(hv, Qt.LeftButton, Qt.NoModifier, rh.mapFromScene(QPointF(400, 300)))
    QTest.mouseMove(hv, rh.mapFromScene(QPointF(600, 350)))
    QTest.mouseRelease(hv, Qt.LeftButton, Qt.NoModifier, rh.mapFromScene(QPointF(600, 350)))
    check("rotate handle: none for lines (they turn via their end points)",
          rh.rotate_handle(rh.elements()[-1]) is None and rh.rotate_handle(box) is not None)
    rh.close()

    # Labels (text in shapes, step 1: data model): child of the shape, wraps at its width,
    # centered, color of the shape, moves/resizes/rotates along, saved with the shape
    from elements import LABEL_PADDING, ShapeElement as _Shape, is_label
    lb = make_canvas(plain_bg)
    lv = lb.viewport()
    lb.set_tool(Tool.RECT)
    QTest.mousePress(lv, Qt.LeftButton, Qt.NoModifier, lb.mapFromScene(QPointF(100, 100)))
    QTest.mouseMove(lv, lb.mapFromScene(QPointF(300, 220)))
    QTest.mouseRelease(lv, Qt.LeftButton, Qt.NoModifier, lb.mapFromScene(QPointF(300, 220)))
    box = lb.elements()[0]
    label = TextElement(QPointF(0, 0), QColor("white"), 20, text="a label long enough to wrap twice")
    box.set_label(label)

    def box_mid():
        return box.mapToScene(box.box(box.points).center())

    def label_mid():
        return label.mapToScene(label.boundingRect().center())
    one_line = QFontMetricsF(label.font()).height()
    check("label: not an element of its own, wraps at the width of the shape, centered",
          lb.elements() == [box] and abs(label.textWidth() - (200 - 2 * LABEL_PADDING)) < 0.5
          and label.boundingRect().height() > 1.5 * one_line and near(label_mid(), box_mid(), 1.0))
    check("label: has the color of the shape, also after recoloring",
          label.color == box.color and (box.set_color(QColor("#00ff00")) or label.color.name() == "#00ff00"))
    check("label: a click on it counts as the shape", lb.element_at(label_mid()) is box)
    start = box.geometry()
    box.drag_handle(2, box.mapToScene(QPointF(400, 200)), start)
    resized_ok = abs(label.textWidth() - (400 - 2 * LABEL_PADDING)) < 0.5 and near(label_mid(), box_mid(), 1.0)
    box.setSelected(True)
    lb.set_tool(Tool.SELECT)
    lb.rotate_selected(30)
    check("label: rewraps after resizing, stays in the middle after rotating",
          resized_ok and near(label_mid(), box_mid(), 1.0))
    labeled = lb.render_image()
    QTest.keyClick(lb, Qt.Key_S, Qt.ControlModifier)
    lbg, lelems, _, _ = load_document(lb.document_path)
    lreloaded = make_canvas(QPixmap.fromImage(lbg), lelems, lb.document_path)
    check("label: saved and loaded with the shape (text, size, pixel identical)",
          len(lelems) == 1 and lelems[0].label is not None
          and lelems[0].label.toPlainText() == label.toPlainText() and lelems[0].label.font_size == 20
          and lreloaded.render_image() == labeled)
    broken = dict(box.to_dict(), label={"text": "x", "font_size": "big"})
    try:
        _Shape.from_dict(broken)
        broken_rejected = False
    except ValueError:
        broken_rejected = True
    plain = dict(box.to_dict())
    plain.pop("label")
    check("label: broken label data is rejected, missing label = no label (older files)",
          broken_rejected and _Shape.from_dict(plain).label is None)
    lreloaded.close()
    lb.close()

    # Labels, step 2: double click into a rectangle/ellipse (select tool) labels it; undo,
    # emptying removes it, color keys while typing recolor the shape, the text tool leaves it alone
    lc = make_canvas(plain_bg)
    lcv = lc.viewport()

    def at_scene(x, y):
        return lc.mapFromScene(QPointF(x, y))

    def ldrag(tool, x1, y1, x2, y2):
        lc.set_tool(tool)
        QTest.mousePress(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(x1, y1))
        QTest.mouseMove(lcv, at_scene(x2, y2))
        QTest.mouseRelease(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(x2, y2))
    ldrag(Tool.RECT, 100, 100, 300, 220)
    ldrag(Tool.ELLIPSE, 400, 100, 600, 220)
    rect, oval = lc.elements()
    lc.set_tool(Tool.SELECT)
    steps = lc.undo_stack.count()
    QTest.mouseDClick(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(200, 160))  # empty inside
    opened = lc.editing_text is rect.label and rect.label is not None and lc.undo_stack.count() == steps
    QTest.keyClicks(lc, "Server")
    QTest.keyClick(lc, Qt.Key_Escape)
    check("double click inside a rectangle: type a label, Esc = one undo step",
          opened and rect.label.toPlainText() == "Server" and lc.undo_stack.count() == steps + 1
          and lc.elements() == [rect, oval])
    lc.undo_stack.undo()
    undone = rect.label is None
    lc.undo_stack.redo()
    check("label: undo removes it, redo brings it back", undone and rect.label.toPlainText() == "Server")
    QTest.mouseDClick(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(200, 160))  # on the label itself
    QTest.keyClick(lc, Qt.Key_End)
    QTest.keyClicks(lc, " 1")
    other = (lc.color_index + 2) % len(lc.settings.colors)
    lc.set_color(other)  # like a click on the color bar while typing: recolors the shape
    QTest.keyClick(lc, Qt.Key_Escape)
    check("label: edited again, a color chosen while typing recolors shape and label together",
          rect.label.toPlainText() == "Server 1" and rect.color == lc.settings.colors[other]
          and rect.label.color == rect.color)
    QTest.mouseDClick(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(200, 160))
    QTest.keyClick(lc, Qt.Key_A, Qt.ControlModifier)  # in the editor: select all text
    QTest.keyClick(lc, Qt.Key_Backspace)
    QTest.keyClick(lc, Qt.Key_Escape)
    emptied = rect.label is None
    lc.undo_stack.undo()
    check("label: emptied = removed, one undo brings back the text",
          emptied and rect.label is not None and rect.label.toPlainText() == "Server 1")
    steps = lc.undo_stack.index()  # position, not count: after an undo a new step drops the redo
    QTest.mouseDClick(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(500, 160))
    QTest.keyClick(lc, Qt.Key_Escape)  # nothing typed
    QTest.mouseDClick(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(500, 160))
    QTest.keyClicks(lc, "DB")
    QTest.keyClick(lc, Qt.Key_Escape)
    check("ellipse: labeled too; opening and leaving without text leaves nothing",
          oval.label is not None and oval.label.toPlainText() == "DB" and lc.undo_stack.index() == steps + 1)
    lc.set_tool(Tool.TEXT)
    QTest.mouseClick(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(200, 160))  # T on the label
    loose = lc.editing_text
    check("text tool on a label: starts a loose text, the label stays in its shape",
          loose is not None and not is_label(loose) and rect.label.toPlainText() == "Server 1")
    QTest.keyClick(lc, Qt.Key_Escape)
    lc.set_tool(Tool.SELECT)
    QTest.mouseDClick(lcv, Qt.LeftButton, Qt.NoModifier, at_scene(200, 300))  # empty spot outside
    check("double click outside of shapes: loose text as before",
          lc.editing_text is not None and not is_label(lc.editing_text))
    QTest.keyClick(lc, Qt.Key_Escape)
    # Copy/paste/duplicate (Qt clipboard, never the real one) and into the whiteboard:
    # the label comes along as an independent copy
    import export as _exp
    _exp.shutil.which = lambda name: None
    lc.scene_.clearSelection()
    rect.setSelected(True)
    QTest.keyClick(lc, Qt.Key_C, Qt.ControlModifier)
    QTest.keyClick(lc, Qt.Key_V, Qt.ControlModifier)
    QTest.keyClick(lc, Qt.Key_D, Qt.ControlModifier)
    copies = [e for e in lc.elements() if e not in (rect, oval)]
    edited_copy = copies[0].label if copies and copies[0].label else None
    if edited_copy:
        edited_copy.setPlainText("changed")
    check("label: comes along when pasting and duplicating, as an independent copy",
          len(copies) == 2 and all(c.label is not None for c in copies)
          and copies[1].label.toPlainText() == "Server 1" and rect.label.toPlainText() == "Server 1")
    board_l = Canvas(QGuiApplication.primaryScreen(), None, board=True)
    board_l.resize(900, 500)
    board_l.show_window()
    QApplication.processEvents()
    board_l.paste_elements()
    pasted_l = board_l.elements()
    check("label: pasted into the whiteboard with its shape",
          len(pasted_l) == 1 and pasted_l[0].label is not None and pasted_l[0].label.toPlainText() == "Server 1")
    board_l.undo_stack.setClean()  # otherwise the whiteboard asks on close (dialog without a screen)
    board_l.close()
    lc.close()

    # Connectors, step 1 (data model, no mouse yet): a docked arrow aims at the middle of its
    # targets and ends at their outline; it follows moving/rotating/resizing, a deleted target
    # leaves the end free, undo docks it again; saved with the arrow
    import connectors
    from commands import AddItemCommand as _Add, MoveItemCommand, RemoveItemCommand as _Remove
    cn = make_canvas(plain_bg)

    def new_shape(tool, a, b):
        item = _Shape(tool, QPointF(*a), QColor("#7aa2f7"), 4)
        item.points[1] = QPointF(b[0] - a[0], b[1] - a[1])
        item.rebuild()
        cn.undo_stack.push(_Add(cn.scene_, item))
        return item
    box_a = new_shape(Tool.RECT, (100, 100), (200, 180))
    oval_b = new_shape(Tool.ELLIPSE, (450, 250), (570, 330))
    arrow = _Shape(Tool.ARROW, QPointF(0, 0), QColor("white"), 4)
    arrow.ends = [box_a.id, oval_b.id]
    cn.undo_stack.push(_Add(cn.scene_, arrow))

    def ends_ok():
        """Both ends just outside the outline of their target (within the gap), and the
        line runs through both middles."""
        start, end = (arrow.mapToScene(p) for p in arrow.points)
        gap = connectors.GAP + arrow.width / 2
        result = True
        for point, target, other in ((start, box_a, end), (end, oval_b, start)):
            area = connectors.outline(target)
            inward = connectors.middle(target) - point
            step = inward / math.hypot(inward.x(), inward.y())
            result &= not area.contains(point) and area.contains(point + step * (gap + 0.5))
        a_mid, b_mid = connectors.middle(box_a), connectors.middle(oval_b)
        cross = (b_mid - a_mid).x() * (start - a_mid).y() - (b_mid - a_mid).y() * (start - a_mid).x()
        return bool(result) and abs(cross) / math.hypot((b_mid - a_mid).x(), (b_mid - a_mid).y()) < 0.5
    check("connector: aims at both middles, ends at both outlines", ends_ok())
    cn.undo_stack.push(MoveItemCommand([box_a], [QPointF(box_a.pos())], [box_a.pos() + QPointF(60, 120)]))
    moved_ok = ends_ok()
    cn.scene_.clearSelection()
    oval_b.setSelected(True)
    cn.rotate_selected(45)
    rotated_ok = ends_ok()
    cn.undo_stack.push(PropertyCommand(box_a.set_geometry, box_a.geometry(),
                                       (QPointF(box_a.pos()), [QPointF(0, 0), QPointF(40, 200)], (None, None))))
    check("connector: follows moving, rotating and resizing its targets (also hjkl/undo: same path)",
          moved_ok and rotated_ok and ends_ok())
    before_delete = [QPointF(arrow.mapToScene(p)) for p in arrow.points]
    cn.undo_stack.push(_Remove(cn.scene_, box_a))
    after_delete = [arrow.mapToScene(p) for p in arrow.points]
    cn.undo_stack.undo()
    cn.undo_stack.push(MoveItemCommand([box_a], [QPointF(box_a.pos())], [box_a.pos() + QPointF(-50, 0)]))
    check("connector: deleted target leaves the end free in place, undo docks it again",
          near(after_delete[0], before_delete[0]) and arrow.ends[0] == box_a.id and ends_ok())
    note = TextElement(QPointF(600, 60), QColor("white"), 20, text="note")
    cn.undo_stack.push(_Add(cn.scene_, note))
    arrow.ends = [arrow.ends[0], note.id]
    cn.update_connectors()
    note_area = connectors.outline(note)
    end = arrow.mapToScene(arrow.points[1])
    check("connector: docks onto loose text too (its box)",
          not note_area.contains(end) and note_area.contains(end + (connectors.middle(note) - end) * 0.5))
    arrow.ends = [box_a.id, oval_b.id]
    cn.update_connectors()
    docked = cn.render_image()
    QTest.keyClick(cn, Qt.Key_S, Qt.ControlModifier)
    cbg, celems, _, _ = load_document(cn.document_path)
    creloaded = make_canvas(QPixmap.fromImage(cbg), celems, cn.document_path)
    loaded_arrow = next(e for e in celems if getattr(e, "tool", None) == Tool.ARROW)
    check("connector: saved and loaded docked (pixel identical)",
          loaded_arrow.ends == [box_a.id, oval_b.id] and creloaded.render_image() == docked)
    old_style = dict(arrow.to_dict())
    old_style.pop("ends")
    try:
        _Shape.from_dict(dict(arrow.to_dict(), ends=[1, 2]))
        rejected = False
    except ValueError:
        rejected = True
    check("connector: older files without ends = free, broken ends are rejected",
          _Shape.from_dict(old_style).ends == [None, None] and rejected)
    creloaded.close()
    cn.close()

    # Connectors, step 2 (mouse): drawing on/near an outline docks, deep inside stays free,
    # the target is highlighted while drawing, dragging a shape moves docked arrows live,
    # an end handle re-docks/undocks (one undo step). Whiteboard only: on a screenshot nothing docks
    cs = make_canvas(plain_bg)
    cs.set_tool(Tool.RECT)
    for event, at in ((QTest.mousePress, QPointF(100, 100)), (QTest.mouseRelease, QPointF(300, 220))):
        event(cs.viewport(), Qt.LeftButton, Qt.NoModifier, cs.mapFromScene(at))
    cs.set_tool(Tool.ARROW)
    for event, at in ((QTest.mousePress, QPointF(305, 160)), (QTest.mouseRelease, QPointF(495, 165))):
        event(cs.viewport(), Qt.LeftButton, Qt.NoModifier, cs.mapFromScene(at))
    check("screenshot mode: an arrow drawn from a rectangle's outline stays free",
          cs.elements()[-1].ends == [None, None] and cs.dock_hint is None)
    cs.close()
    from canvas import Canvas
    cm = Canvas(QGuiApplication.primaryScreen(), None, board=True)
    cm.resize(1100, 500)
    cm.show_window()
    QApplication.processEvents()
    cm.centerOn(400, 250)
    cmv = cm.viewport()

    def cpress(x, y):
        QTest.mousePress(cmv, Qt.LeftButton, Qt.NoModifier, cm.mapFromScene(QPointF(x, y)))

    def cmove(x, y):
        QTest.mouseMove(cmv, cm.mapFromScene(QPointF(x, y)))

    def crelease(x, y):
        QTest.mouseRelease(cmv, Qt.LeftButton, Qt.NoModifier, cm.mapFromScene(QPointF(x, y)))

    def cdraw(tool, x1, y1, x2, y2):
        cm.set_tool(tool)
        cpress(x1, y1)
        cmove((x1 + x2) / 2, (y1 + y2) / 2)
        cmove(x2, y2)
        crelease(x2, y2)
        return cm.elements()[-1]
    left = cdraw(Tool.RECT, 100, 100, 300, 220)
    right = cdraw(Tool.ELLIPSE, 500, 100, 700, 220)
    cm.set_tool(Tool.ARROW)
    cpress(305, 160)  # just outside the right edge of the rectangle
    cmove(400, 160)
    cmove(495, 165)  # near the left of the ellipse
    hint_while_drawing = cm.dock_hint is right
    crelease(495, 165)
    docked_arrow = cm.elements()[-1]
    check("drawing near both outlines docks both ends, the target is highlighted meanwhile",
          docked_arrow.ends == [left.id, right.id] and hint_while_drawing and cm.dock_hint is None)
    deep = cdraw(Tool.ARROW, 200, 160, 400, 330)  # starts deep inside the rectangle
    same = cdraw(Tool.LINE, 150, 100, 250, 102)   # both ends on the top edge of the rectangle
    check("deep inside stays free; both ends on the same shape: the second stays free",
          deep.ends == [None, None] and same.ends == [left.id, None])
    cm.set_tool(Tool.SELECT)
    start_before = docked_arrow.mapToScene(docked_arrow.points[0]).y()
    cpress(100, 160)  # left edge of the rectangle: drag it down
    cmove(100, 210)
    start_live = docked_arrow.mapToScene(docked_arrow.points[0]).y()  # mouse still pressed
    cmove(100, 260)
    crelease(100, 260)
    start_after = docked_arrow.mapToScene(docked_arrow.points[0]).y()
    check(f"dragging a shape: the docked arrow follows live and after releasing "
          f"({start_before:.0f} -> {start_live:.0f} -> {start_after:.0f})",
          start_before < start_live < start_after and docked_arrow.ends == [left.id, right.id])
    cm.scene_.clearSelection()
    docked_arrow.setSelected(True)
    end_handle = docked_arrow.mapToScene(docked_arrow.points[1])
    steps = cm.undo_stack.index()
    cpress(end_handle.x(), end_handle.y())
    cmove(450, 350)
    crelease(450, 350)
    undocked = docked_arrow.ends == [left.id, None] and near(docked_arrow.mapToScene(docked_arrow.points[1]),
                                                              QPointF(450, 350), 1)
    cm.undo_stack.undo()
    check("end handle into the empty: undocked; one undo docks it again",
          undocked and cm.undo_stack.index() == steps and docked_arrow.ends == [left.id, right.id])

    # Connectors, step 3: moving/rotating the arrow itself undocks it (unless its shapes move
    # along); copying keeps copies docked to each other, a copied arrow alone is free
    def select_only(*items):
        cm.scene_.clearSelection()
        for item in items:
            item.setSelected(True)
    cm.set_tool(Tool.SELECT)
    middle_of_arrow = (docked_arrow.mapToScene(docked_arrow.points[0])
                       + docked_arrow.mapToScene(docked_arrow.points[1])) / 2
    select_only(docked_arrow)
    steps = cm.undo_stack.index()
    cpress(middle_of_arrow.x(), middle_of_arrow.y())
    cmove(middle_of_arrow.x(), middle_of_arrow.y() + 40)
    cmove(middle_of_arrow.x(), middle_of_arrow.y() + 80)
    crelease(middle_of_arrow.x(), middle_of_arrow.y() + 80)
    dragged_free = docked_arrow.ends == [None, None] and cm.undo_stack.index() == steps + 1
    cm.undo_stack.undo()
    check("dragging the arrow itself undocks both ends; one undo docks it again",
          dragged_free and docked_arrow.ends == [left.id, right.id])
    select_only(left, docked_arrow)
    QTest.keyClick(cm, Qt.Key_L)
    check("hjkl with the rectangle selected too: that end stays docked, the other lets go",
          docked_arrow.ends == [left.id, None])
    cm.undo_stack.undo()
    select_only(docked_arrow)
    QTest.keyClick(cm, Qt.Key_Q)
    rotated_free = docked_arrow.ends == [None, None]
    cm.undo_stack.undo()
    check("Q on the arrow alone undocks it; undo docks it again",
          rotated_free and docked_arrow.ends == [left.id, right.id])
    import export as _exp2
    _exp2.shutil.which = lambda name: None  # never the real clipboard
    select_only(left, right, docked_arrow)
    before = set(cm.elements())
    QTest.keyClick(cm, Qt.Key_D, Qt.ControlModifier)
    copies = {e.tool: e for e in cm.elements() if e not in before}
    copy_arrow = copies.get(Tool.ARROW)
    check("duplicating shapes with their arrow: the copy is docked to the copies",
          copy_arrow is not None and copy_arrow.ends == [copies[Tool.RECT].id, copies[Tool.ELLIPSE].id])
    select_only(docked_arrow)
    before = set(cm.elements())
    QTest.keyClick(cm, Qt.Key_C, Qt.ControlModifier)
    QTest.keyClick(cm, Qt.Key_V, Qt.ControlModifier)
    lone = [e for e in cm.elements() if e not in before]
    check("copying the arrow alone: the pasted arrow is free (does not jump to the originals)",
          len(lone) == 1 and lone[0].ends == [None, None] and docked_arrow.ends == [left.id, right.id])

    # Connectors, step 4: text on lines/arrows: double click on the arrow, text in the middle of
    # the line, upright, in a small box; follows when the docked shapes move; saved
    from elements import LABEL_BOX_PADDING
    from PySide6.QtWidgets import QGraphicsTextItem  # the rectangle Qt would use without the box

    def arrow_mid():
        return (docked_arrow.mapToScene(docked_arrow.points[0]) + docked_arrow.mapToScene(docked_arrow.points[1])) / 2

    def text_mid():
        lab = docked_arrow.label
        return lab.mapToScene(lab.boundingRect().center())
    cm.scene_.clearSelection()
    on_line = arrow_mid()
    QTest.mouseDClick(cmv, Qt.LeftButton, Qt.NoModifier, cm.mapFromScene(on_line))
    QTest.keyClicks(cm, "SQL")
    QTest.keyClick(cm, Qt.Key_Escape)
    label = docked_arrow.label
    check("double click on an arrow: text in the middle of the line, in a box",
          label is not None and label.toPlainText() == "SQL" and near(text_mid(), arrow_mid(), 1.0)
          and abs(label.boundingRect().height() - QGraphicsTextItem.boundingRect(label).height()
                  - 2 * LABEL_BOX_PADDING) < 1e-6)
    select_only(left)
    QTest.keyClick(cm, Qt.Key_J)  # move the docked rectangle down: the text stays in the middle
    followed = near(text_mid(), arrow_mid(), 1.0)
    select_only(docked_arrow)
    QTest.keyClick(cm, Qt.Key_Q)  # rotate the arrow: the text stays horizontal
    across = label.mapToScene(QPointF(10, 0)) - label.mapToScene(QPointF(0, 0))
    check("arrow text: follows the moved shape, stays horizontal when the arrow is rotated",
          followed and abs(across.y()) < 1e-6 and near(text_mid(), arrow_mid(), 1.0))
    cm.undo_stack.undo()
    box_color = cm.scene_.label_box_color()
    check("arrow text box on a screenshot: the bar background, opaque",
          box_color.alpha() == 255 and box_color.rgb() == cm.settings.theme.background.rgb())
    QTest.keyClick(cm, Qt.Key_S, Qt.ControlModifier)
    _, saved_elems, _, _ = load_document(cm.document_path)
    saved_arrow = next(e for e in saved_elems if e.id == docked_arrow.id)
    check("arrow text is saved and loaded with the arrow",
          saved_arrow.label is not None and saved_arrow.label.toPlainText() == "SQL")
    cm.close()

    # Front/back: Ctrl+↑/↓ one step, Ctrl+Shift+↑/↓ all the way; undo; delete+undo keeps the place
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
    check(f"Ctrl+↑ one step ({one_up}), Ctrl+Shift+↑ to the front ({top}), undo",
          one_up == "bacd" and top == "bcda" and order() == "abcd")
    zo.scene_.clearSelection()
    c.setSelected(True)
    d.setSelected(True)
    QTest.keyClick(zo, Qt.Key_Down, Qt.ControlModifier | Qt.ShiftModifier)
    check(f"several to the back, order among them stays ({order()})", order() == "cdab")
    zo.undo_stack.undo()
    zo.scene_.clearSelection()
    b.setSelected(True)
    zo.delete_selected()
    zo.undo_stack.undo()
    check(f"deleted element back at its place via undo ({order()})", order() == "abcd")
    QTest.keyClick(zo, Qt.Key_S, Qt.ControlModifier)
    b.setSelected(True)
    QTest.keyClick(zo, Qt.Key_Up, Qt.ControlModifier | Qt.ShiftModifier)
    QTest.keyClick(zo, Qt.Key_S, Qt.ControlModifier)
    _, saved, _, _ = load_document(zo.document_path)
    check("order is saved", [e.id for e in saved] == [a.id, c.id, d.id, b.id])
    zo.close()

    # Copy/paste/duplicate (Qt clipboard, never the real one: xclip turned off)
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
    check("Ctrl+C/Ctrl+V: copies with new IDs, selected afterwards, marker counts on",
          len(pasted) == 3 and not {e.id for e in pasted} & {e.id for e in originals}
          and cp.selected_elements() == pasted
          and [e.marker_label() for e in pasted if e.tool == Tool.MARKER] == ["2"])
    cp.undo_stack.undo()
    check("paste: one undo step", cp.elements() == originals)
    cp.scene_.clearSelection()
    originals[0].setSelected(True)
    QTest.keyClick(cp, Qt.Key_D, Qt.ControlModifier)
    dup = [e for e in cp.elements() if e not in originals]
    offset = dup[0].pos() - originals[0].pos() if dup else QPointF()
    check("Ctrl+D: duplicated, slightly offset", len(dup) == 1 and offset.x() > 0 and offset == QPointF(offset.x(), offset.x()))
    wb = Canvas(QGuiApplication.primaryScreen(), None, board=True)
    wb.resize(900, 500)
    wb.show_window()
    QApplication.processEvents()
    blur_dict = dict(originals[0].to_dict(), tool="blur")
    wb.insert_copies([originals[0].to_dict(), blur_dict], target=QPointF(0, 0))
    check("paste in the whiteboard: blur is left out",
          [e.tool for e in wb.elements()] == [Tool.RECT])
    wb.undo_stack.setClean()  # otherwise the whiteboard asks on close (dialog without a screen)
    wb.close()
    cp.close()

    # Image elements: crop with markings editable into the whiteboard, paste foreign images
    from PySide6.QtCore import QByteArray, QMimeData
    from elements import ImageElement
    from export import png_bytes
    shot = make_canvas(QPixmap(800, 400))
    sv = shot.viewport()
    shot.set_tool(Tool.MARKER)
    QTest.mouseClick(sv, Qt.LeftButton, Qt.NoModifier, shot.mapFromScene(QPointF(200, 150)))
    QTest.mouseClick(sv, Qt.LeftButton, Qt.NoModifier, shot.mapFromScene(QPointF(700, 350)))  # outside
    shot.set_crop(QRectF(100, 50, 300, 200))
    shot.copy_image()  # Ctrl+C without a selection / Enter
    # Like xclip: the PNG bytes unchanged in the clipboard (Qt alone re-encodes)
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
    check(f"crop into the whiteboard: image at the bottom, marker in it editable ({kinds})",
          kinds == ["ImageElement", "ShapeElement"] and image.size.toTuple() == (300.0, 200.0))
    foreign = QImage(120, 80, QImage.Format_RGB32)
    foreign.fill(QColor("orange"))
    QGuiApplication.clipboard().setImage(foreign)
    wb2.paste_elements()
    pasted = wb2.selected_elements()
    check("foreign image: one image element in original size",
          len(pasted) == 1 and isinstance(pasted[0], ImageElement) and pasted[0].size.toTuple() == (120.0, 80.0))
    start = pasted[0].geometry()
    corner = pasted[0].mapToScene(pasted[0].handle_points()[2])
    pasted[0].drag_handle(2, corner + QPointF(60, 0), start)
    check("image: handle changes the size, aspect ratio stays",
          abs(pasted[0].size.width() / pasted[0].size.height() - 1.5) < 0.01 and pasted[0].size.width() > 120)
    QTest.keyClick(wb2, Qt.Key_S, Qt.ControlModifier)
    _, saved_board, _, _ = load_document(wb2.document_path)
    check("image elements are saved and loaded",
          sum(isinstance(e, ImageElement) for e in saved_board) == 2)
    wb2.undo_stack.setClean()
    wb2.close()
    shot.close()

    # Image from another monitor: larger -> scaled down fully visible, smaller -> 1:1 centered;
    # drawing and export happen in full resolution
    big = QPixmap(2200, 1000)
    big.fill(QColor("#3b4261"))
    large = make_canvas(big)
    check("large image: scaled down", abs(large.zoom() - 0.5) < 0.01)
    lview = large.viewport()
    QTest.keyClick(large, Qt.Key_S)  # line
    QTest.mousePress(lview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(lview, QPoint(300, 200))
    QTest.mouseRelease(lview, Qt.LeftButton, pos=QPoint(300, 200))
    line = large.elements()[-1]
    check("large image: line in image pixels", abs(line.mapToScene(line.points[1]).x()
                                                  - line.mapToScene(line.points[0]).x() - 400) < 2)
    check("large image: export in full resolution", large.render_image().size() == big.size())
    small = QPixmap(400, 300)
    small.fill(QColor("#3b4261"))
    little = make_canvas(small)
    center = little.mapFromScene(little.export_rect.center())
    check("small image: 1:1 and centered", little.zoom() == 1.0
          and (center - little.viewport().rect().center()).manhattanLength() <= 2)
    large.close()
    little.close()

    # History (roadmap 10): one entry per session, browse with ← →
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
    first.close()  # saved when quitting
    second_bg = QPixmap(900, 400)
    second_bg.fill(QColor("#662244"))
    second = make_canvas(second_bg)
    second.start_history()
    draw_rect(second, 100)
    draw_rect(second, 300)
    second.flush_history()
    files = history.entries(hdir)
    check("history: two entries", len(files) == 2 and files[-1] == second.history_path)
    QTest.keyClick(second, Qt.Key_Left)
    check("history ←: older entry loaded", second.history_path == files[0]
          and len(second.elements()) == 1 and second.export_size == first_bg.size()
          and second.undo_stack.count() == 0)
    draw_rect(second, 500)  # keep editing the older entry
    QTest.keyClick(second, Qt.Key_Right)
    _, old_elems, _, _ = load_document(files[0])
    check("history: change to the older entry saved", len(old_elems) == 2)
    check("history →: newer entry loaded", second.history_path == files[1]
          and len(second.elements()) == 2 and second.export_size == second_bg.size())
    QTest.keyClick(second, Qt.Key_Right)
    check("history: the newest stays at the end", second.history_path == files[1])
    second.close()
    check("history cleanup: only the newest stay",
          history.prune(hdir, 1) == 1 and history.entries(hdir) == [files[1]])
    empty = make_canvas(first_bg)
    empty.start_history()
    empty.close()  # nothing drawn
    check("history: screenshot without changes stays out", history.entries(hdir) == [files[1]])
    board_h = Canvas(QGuiApplication.primaryScreen(), None, board=True)
    board_h.start_history()
    check("history: never in the whiteboard", board_h.history_path is None)
    board_h.close()

    # Whiteboard: empty area, save, load again as whiteboard
    import export
    export.shutil.which = lambda name: None  # never touch the real clipboard
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
    check("whiteboard: Esc and Enter do not close", board.isVisible())
    check("whiteboard: unsaved detected", not board.undo_stack.isClean())
    board_image = board.render_image()
    check("whiteboard export = used area", board_image.width() < 400 and board_image.height() < 300)
    QTest.keyClick(board, Qt.Key_S, Qt.ControlModifier)
    check("whiteboard saved (_board)", board.document_path and "_board" in board.document_path.stem)  # also _board_2 in the same second
    check("clean after saving", board.undo_stack.isClean())
    bbg, belems, _, _ = load_document(board.document_path)
    check("loaded as whiteboard", isinstance(bbg, QColor) and bbg == board.board_color and len(belems) == 1)
    board2 = Canvas(QGuiApplication.primaryScreen(), None, belems, board.document_path,
                             board=True, board_color=bbg)
    board2.show_window()
    check("whiteboard loaded again = same export", board2.render_image() == board_image)

    # Shift+Enter: save, copy the absolute path; the whiteboard stays open
    QTest.keyClick(board2, Qt.Key_Return, Qt.ShiftModifier)
    copied = QGuiApplication.clipboard().text()
    check("Shift+Enter: absolute path copied",
          copied == str(Path(board2.document_path).resolve()) and Path(copied).is_absolute()
          and board2.undo_stack.isClean() and board2.isVisible())

    # Change the background (Ctrl+B): undo step, saved with the drawing
    old_bg = QColor(board2.board_color)
    QTest.keyClick(board2, Qt.Key_B, Qt.ControlModifier)
    new_bg = QColor(board2.board_color)
    check("Ctrl+B changes the background", new_bg != old_bg and not board2.undo_stack.isClean())
    QTest.keyClick(board2, Qt.Key_R)
    check("background: undo", board2.board_color == old_bg and board2.undo_stack.isClean())
    QTest.keyClick(board2, Qt.Key_B, Qt.ControlModifier | Qt.ShiftModifier)
    QTest.keyClick(board2, Qt.Key_S, Qt.ControlModifier)
    bbg2, _, _, _ = load_document(board2.document_path)
    check("background saved", bbg2 == board2.board_color != old_bg)

    # Light background: colors are shown darkened, the base color is saved
    from colors import LIGHT_CONTRAST, contrast
    paper = QColor("#f8f6f0")
    light = Canvas(QGuiApplication.primaryScreen(), None, board=True, board_color=paper)
    light.resize(900, 500)
    light.show_window()
    QApplication.processEvents()
    lview = light.viewport()
    # Pick a color that is too weak on paper (otherwise it would stay unchanged)
    weak = next(i for i, c in enumerate(light.settings.swatches) if contrast(c, paper.name()) < LIGHT_CONTRAST)
    light.set_color(weak)
    QTest.keyClick(light, Qt.Key_F)
    QTest.mousePress(lview, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(lview, QPoint(300, 200))
    QTest.mouseRelease(lview, Qt.LeftButton, pos=QPoint(300, 200))
    rect = light.elements()[0]
    base, shown = rect.color.name(), rect.pen().color().name()
    check("light: shape shown darkened", shown != base and contrast(shown, paper.name()) >= LIGHT_CONTRAST)
    check("light: base color saved", rect.to_dict()["color"] == base)
    text = TextElement(QPointF(0, 0), QColor(base), 20, text="x")
    light.scene_.addItem(text)
    check("light: text shown darkened", text.defaultTextColor().name() == shown and text.color.name() == base)
    check("light: color bar adapted", light.palette_bar.colors[light.color_index].name() != light.settings.swatches[light.color_index])
    light.undo_stack.push(PropertyCommand(light.set_board_color, QColor(paper), QColor("#24283b")))
    check("dark: base color shown", rect.pen().color().name() == base and text.defaultTextColor().name() == base)
    light.undo_stack.undo()
    check("undo: darkened again", rect.pen().color().name() == shown)

    print("\nAll OK." if not failures else f"\n{len(failures)} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
