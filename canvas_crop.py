"""Crop part of the Canvas (area selection, key y, screenshot mode only).

y starts the selection: draw a rectangle, then the current tool continues. If there
already is a crop, y shows handles: drag a handle = resize, drag inside = move,
drag outside = draw a new one. Outside
the crop everything is darkened (only on screen, drawForeground). Copying,
saving, exporting and the history only use the crop as the visible image
(output_area); the editable file keeps the whole screenshot and saves the
crop with it ("crop"), so it stays changeable. Esc during the selection removes it.
Setting and removing are undo steps (PropertyCommand on set_crop).

Mixin like BoardMixin (canvas_board.py). Manages (created in Canvas.__init__):
crop_rect (QRectF in scene coordinates or None), cropping (selection in progress),
crop_drag (start point while dragging or None), crop_drag_end, crop_edit (while dragging:
("resize", handle), ("move", None) or None = draw a new one).
Reads from the Canvas: board, export_rect, export_size, scene_, undo_stack, ui_scale,
zoom(), refresh_cursor(), report().
"""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from commands import PropertyCommand
from settings import HANDLE_GRAB, HANDLE_SIZE

CROP_DIM = 110         # darkening outside the crop, 0-255
CROP_MIN_SIZE = 5      # smaller rectangles (screen pixels) count as a click: change nothing
# Handles on the crop (relative position): corners and edge centers, clockwise from top left
CROP_HANDLES = ((0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5))
CROP_CURSORS = (Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor,
                Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor)


class CropMixin:
    # --- State ---
    def set_crop(self, rect):
        """Setter for PropertyCommand: crop (QRectF) or None = whole screenshot."""
        self.crop_rect = QRectF(rect) if rect is not None else None
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
            self.report("Adjust crop: drag handles, drag inside to move, outside for a new one (Esc: remove)"
                        if self.crop_rect is not None else "Draw a crop (Esc: remove crop)")
        self.refresh_cursor()
        self.viewport().update()

    def cancel_crop(self):
        """Esc during the selection: remove the crop (undo step), end the selection."""
        self.cropping = False
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
        grab = HANDLE_GRAB / self.zoom()  # grab radius always the same on screen
        for index, point in enumerate(self.crop_handle_points(self.crop_rect)):
            if abs(point.x() - pos.x()) <= grab and abs(point.y() - pos.y()) <= grab:
                return ("resize", index)
        return ("move", None) if self.crop_rect.contains(pos) else None

    def crop_hover(self, pos):
        """Mouse cursor during the selection: resize arrows over handles, move arrows inside."""
        hit = self.crop_hit(pos)
        if hit is None:
            cursor = Qt.CrossCursor
        elif hit[0] == "move":
            cursor = Qt.SizeAllCursor
        else:
            cursor = CROP_CURSORS[hit[1]]
        self.viewport().setCursor(cursor)

    def crop_press(self, pos):
        self.crop_drag = self.crop_drag_end = pos
        self.crop_edit = self.crop_hit(pos)  # None = draw a new one

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
        if self.cropping and self.crop_rect is not None and (self.crop_drag is None or self.crop_edit is not None):
            line, fill = self.selection_colors()  # like the handles of the selection
            handle_pen = QPen(line, 1.5)
            handle_pen.setCosmetic(True)
            painter.setPen(handle_pen)
            painter.setBrush(fill)
            size = HANDLE_SIZE / self.zoom()
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
