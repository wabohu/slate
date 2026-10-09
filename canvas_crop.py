"""Crop part of the Canvas (area selection, key x, screenshot mode only).

x starts the selection: draw a rectangle, then the current tool continues. If there
already is a crop, x shows handles: drag a handle = resize, drag inside = move,
drag outside = draw a new one. In the select tool a click on the edge of the crop
selects it (crop_selected): handles to resize, dragging the edge moves it, as often as
needed; a click elsewhere deselects it, Esc removes it. Del (whenever no element is
selected, no need to select the crop) clears the area: the
screenshot inside gets filled with the color around it (surrounding_color, gone from saved files too), the markings
stay, the crop is removed. The inside stays free for the elements in it. Outside
the crop everything is darkened (only on screen, drawForeground). Copying,
saving, exporting and the history only use the crop as the visible image
(output_area); the editable file keeps the whole screenshot and saves the
crop with it ("crop"), so it stays changeable. Esc during the selection removes it.
Setting and removing are undo steps (PropertyCommand on set_crop).

Mixin like BoardMixin (canvas_board.py). Manages (created in Canvas.__init__):
crop_rect (QRectF in scene coordinates or None), cropping (selection in progress),
crop_drag (start point while dragging or None), crop_drag_end, crop_edit (while dragging:
("resize", handle), ("move", None) or None = draw a new one), crop_selected.
Reads from the Canvas: board, export_rect, export_size, scene_, undo_stack, ui_scale,
zoom(), screen_px(), refresh_cursor(), report().
"""
from collections import Counter

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from commands import PropertyCommand
from settings import HANDLE_GRAB, HANDLE_SIZE
from tools import Tool

CLEAR_SAMPLES = 2000  # at most this many pixels around the area decide its fill color (Del)
CROP_DIM = 110         # darkening outside the crop, 0-255
CROP_MIN_SIZE = 5      # smaller rectangles (screen pixels) count as a click: change nothing
# Handles on the crop (relative position): corners and edge centers, clockwise from top left
CROP_HANDLES = ((0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5))
CROP_CURSORS = (Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor,
                Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor)


def surrounding_color(image, rect):
    """Most frequent color on the ring of pixels just outside rect (image pixels; sides at the
    image edge use the outermost row inside instead). On a web page or terminal that is its
    background, so a cleared area blends in. The most frequent, not the average: text or lines
    on the edge would mix in a gray that exists nowhere in the picture."""
    left, top = round(rect.left()), round(rect.top())
    right, bottom = round(rect.right()) - 1, round(rect.bottom()) - 1  # last pixel inside
    width, height = image.width(), image.height()
    # One pixel outside where possible, otherwise the edge pixel inside
    x0 = left - 1 if left > 0 else left
    x1 = right + 1 if right < width - 1 else right
    y0 = top - 1 if top > 0 else top
    y1 = bottom + 1 if bottom < height - 1 else bottom
    step = max(1, 2 * ((x1 - x0) + (y1 - y0)) // CLEAR_SAMPLES)
    points = [(x, y) for x in range(x0, x1 + 1, step) for y in (y0, y1)]
    points += [(x, y) for y in range(y0, y1 + 1, step) for x in (x0, x1)]
    counts = Counter(image.pixel(x, y) for x, y in points if 0 <= x < width and 0 <= y < height)
    return QColor.fromRgb(counts.most_common(1)[0][0]) if counts else QColor("white")


class CropMixin:
    # --- State ---
    def set_crop(self, rect):
        """Setter for PropertyCommand: crop (QRectF) or None = whole screenshot."""
        self.crop_rect = QRectF(rect) if rect is not None else None
        if rect is None:
            self.crop_selected = False  # nothing left to select (also after an undo)
        self.viewport().update()

    def output_area(self):
        """(area in the scene, size in image pixels) for rendering and saving."""
        if self.crop_rect is None:
            return self.export_rect, self.export_size
        area = self.crop_rect.intersected(self.export_rect)
        factor = self.export_size.width() / max(1.0, self.export_rect.width())
        return area, QSize(max(1, round(area.width() * factor)), max(1, round(area.height() * factor)))

    # --- Key y and mouse ---
    def crop_key(self):
        """y: start the selection (with an existing crop: handles to adjust it);
        if it is already running, cancel it (the crop stays)."""
        if self.board:
            return
        self.cropping = not self.cropping
        self.crop_drag = None
        if self.cropping:
            self.stop_pointer()
            self.report("Adjust crop: drag handles, drag inside to move, outside for a new one (Esc: remove, Del: clear the area)"
                        if self.crop_rect is not None else "Draw a crop (Esc: remove crop)")
        self.refresh_cursor()
        self.viewport().update()

    def cancel_crop(self):
        """Esc during the selection or on the selected crop: remove the crop (undo step)."""
        self.cropping = False
        self.crop_selected = False
        self.crop_drag = None
        if self.crop_rect is not None:
            self.undo_stack.push(PropertyCommand(self.set_crop, QRectF(self.crop_rect), None, "Remove crop"))
        self.refresh_cursor()
        self.viewport().update()

    def crop_handle_points(self, rect):
        return [QPointF(rect.left() + fx * rect.width(), rect.top() + fy * rect.height()) for fx, fy in CROP_HANDLES]

    def crop_hit(self, pos):
        """What is under pos? ("resize", handle), ("move", None) or None (outside: draw a new one)."""
        if self.crop_rect is None:
            return None
        grab = self.screen_px(HANDLE_GRAB)  # grab radius always the same on screen
        for index, point in enumerate(self.crop_handle_points(self.crop_rect)):
            if abs(point.x() - pos.x()) <= grab and abs(point.y() - pos.y()) <= grab:
                return ("resize", index)
        return ("move", None) if self.crop_rect.contains(pos) else None

    def crop_cursor(self, hit):
        """Resize arrows over handles, move arrows for ("move", None), else a cross."""
        if hit is None:
            return Qt.CrossCursor
        return Qt.SizeAllCursor if hit[0] == "move" else CROP_CURSORS[hit[1]]

    def crop_hover(self, pos):
        """Mouse cursor during the selection: resize arrows over handles, move arrows inside."""
        self.viewport().setCursor(self.crop_cursor(self.crop_hit(pos)))

    def crop_press(self, pos):
        self.crop_drag = self.crop_drag_end = pos
        self.crop_edit = self.crop_hit(pos)  # None = draw a new one

    # --- Select tool: select the crop by its edge, adjust it ---
    def crop_select_hit(self, pos):
        """Select tool: ("resize", handle) on a handle of the selected crop, ("move", None)
        on the edge of the crop, otherwise None (also inside: that belongs to the elements)."""
        if self.board or self.crop_rect is None or self.tool != Tool.SELECT:
            return None
        if self.crop_selected:
            hit = self.crop_hit(pos)
            if hit is not None and hit[0] == "resize":
                return hit
        grab = self.screen_px(HANDLE_GRAB)  # same tolerance on screen as for handles
        rect = self.crop_rect
        near = rect.adjusted(-grab, -grab, grab, grab).contains(pos)
        inside = rect.adjusted(grab, grab, -grab, -grab).contains(pos)
        return ("move", None) if near and not inside else None

    def grab_crop(self, pos, hit):
        """Select tool: select the crop (elements are deselected) and start dragging hit."""
        self.scene_.clearSelection()
        self.update_bars()
        self.crop_selected = True
        self.crop_drag = self.crop_drag_end = pos
        self.crop_edit = hit
        self.viewport().update()

    def deselect_crop(self):
        if self.crop_selected:
            self.crop_selected = False
            self.viewport().update()

    def clear_crop_area(self):
        """Del when there is a crop and no element is selected (any tool, selected or not):
        fill the screenshot inside with the color around it and remove the crop, one undo step.
        Changes the raw image itself, so the content is gone from saved files too."""
        if self.board or self.crop_rect is None:
            return
        rect = self.crop_rect.intersected(self.export_rect)
        factor = self.scene_.blur_scale  # scene -> image pixels
        area = QRectF(rect.x() * factor, rect.y() * factor, rect.width() * factor, rect.height() * factor)
        cleared = self.background_image.copy()
        painter = QPainter(cleared)
        painter.fillRect(area, surrounding_color(self.background_image, area))
        painter.end()
        self.cropping = False
        self.undo_stack.beginMacro("Clear area")  # several commands = one undo step
        self.undo_stack.push(PropertyCommand(self.set_background_image, self.background_image, cleared, "Clear area"))
        self.undo_stack.push(PropertyCommand(self.set_crop, QRectF(self.crop_rect), None, "Remove crop"))
        self.undo_stack.endMacro()
        self.refresh_cursor()

    def crop_move(self, pos):
        self.crop_drag_end = pos
        self.viewport().update()

    def crop_preview(self):
        """The crop as it currently looks (while dragging, already with the change)."""
        if self.crop_drag is None:
            return self.crop_rect
        start, end = self.crop_drag, self.crop_drag_end
        if self.crop_edit is None:
            return QRectF(start, end).normalized().intersected(self.export_rect)
        mode, index = self.crop_edit
        rect = QRectF(self.crop_rect)
        dx, dy = end.x() - start.x(), end.y() - start.y()
        bounds = self.export_rect
        if mode == "move":  # move, but stay inside the screenshot
            dx = min(max(dx, bounds.left() - rect.left()), bounds.right() - rect.right())
            dy = min(max(dy, bounds.top() - rect.top()), bounds.bottom() - rect.bottom())
            return rect.translated(dx, dy)
        fx, fy = CROP_HANDLES[index]
        if fx == 0:
            rect.setLeft(rect.left() + dx)
        elif fx == 1:
            rect.setRight(rect.right() + dx)
        if fy == 0:
            rect.setTop(rect.top() + dy)
        elif fy == 1:
            rect.setBottom(rect.bottom() + dy)
        return rect.normalized().intersected(bounds)

    def crop_release(self, pos):
        self.crop_drag_end = pos
        rect = self.crop_preview()
        self.crop_drag = self.crop_edit = None
        self.cropping = False
        self.refresh_cursor()
        if rect is not None and min(rect.width(), rect.height()) * self.zoom() >= CROP_MIN_SIZE \
                and rect != self.crop_rect:
            old = QRectF(self.crop_rect) if self.crop_rect is not None else None
            self.undo_stack.push(PropertyCommand(self.set_crop, old, rect, "Crop"))
        # In the select tool the crop stays selected: adjust it again as often as needed
        self.crop_selected = self.tool == Tool.SELECT and self.crop_rect is not None
        self.viewport().update()

    # --- Display ---
    def paint_crop(self, painter):
        """Darken outside the crop, show frame and size (never in the export)."""
        if self.board:
            return
        rect = self.crop_preview()  # while dragging, already with the change
        if rect is None:
            return
        rect = rect.intersected(self.export_rect)
        s = self.ui_scale
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        outside = QPainterPath()
        outside.addRect(self.mapToScene(self.viewport().rect()).boundingRect().united(self.export_rect))
        inside = QPainterPath()
        inside.addRect(rect)
        painter.fillPath(outside.subtracted(inside), QColor(0, 0, 0, CROP_DIM))
        painter.setBrush(Qt.NoBrush)
        # Dark line under the light dashed one: visible on light and dark backgrounds
        for color, style in ((QColor(0, 0, 0, 170), Qt.SolidLine), (QColor(255, 255, 255, 230), Qt.DashLine)):
            pen = QPen(color, 1.5 * s, style)
            pen.setCosmetic(True)  # always the same thickness on screen, however it is zoomed
            painter.setPen(pen)
            painter.drawRect(rect)
        if (self.cropping or self.crop_selected) and self.crop_rect is not None \
                and (self.crop_drag is None or self.crop_edit is not None):
            line, fill = self.selection_colors()  # like the handles of the selection
            handle_pen = QPen(line, 1.5 * s)
            handle_pen.setCosmetic(True)
            painter.setPen(handle_pen)
            painter.setBrush(fill)
            size = self.screen_px(HANDLE_SIZE)
            for p in self.crop_handle_points(rect):
                painter.drawRect(QRectF(p.x() - size / 2, p.y() - size / 2, size, size))
        # Size in image pixels at the bottom right of the frame, in screen coordinates
        factor = self.export_size.width() / max(1.0, self.export_rect.width())
        label = f"{round(rect.width() * factor)} × {round(rect.height() * factor)}"
        corner = self.mapFromScene(rect.bottomRight())
        painter.resetTransform()
        font = QFont()
        font.setPixelSize(round(12 * s))
        painter.setFont(font)
        box = QRectF(corner.x() - 120 * s, corner.y() + 4 * s, 120 * s, 20 * s)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        width = painter.fontMetrics().horizontalAdvance(label) + 12 * s
        painter.drawRoundedRect(QRectF(box.right() - width, box.top(), width, box.height()), 4 * s, 4 * s)
        painter.setPen(QColor("white"))
        painter.drawText(box.adjusted(0, 0, -6 * s, 0), Qt.AlignRight | Qt.AlignVCenter, label)
        painter.restore()
