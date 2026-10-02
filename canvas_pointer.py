"""Pointer part of the Canvas: own mouse cursor while drawing, spotlight and magnifier for pointing.

Mouse cursor (drawing tools; hidden while pointing; select: arrow, see make_select_cursor): thin crosshair in the pen color, in the center a
thin circle as wide as the stroke on screen (stroke width × zoom), at the bottom
right a small version of the tool's shape.
Qt concept: QCursor(QPixmap, x, y) turns a self-drawn image into a
mouse cursor; (x, y) is the click point (hotspot), here the center.

Pointing (draws nothing, never in the export):
- Spotlight (e): everything darkened except a circle around the mouse
- Magnifier (Shift+E): enlarged area around the mouse
The same key or Esc ends it, and so does changing the tool. Both are drawn in
drawForeground (InputMixin) via paint_pointer().

Mixin like BoardMixin (canvas_board.py). Manages (created in Canvas.__init__):
pointer_mode (None, "spotlight", "lens"), cursor_cache.
Reads from the Canvas: tool, board, pen_color, pen_width, ui_scale, scene_, settings, zoom(),
adapt_color().
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap

from tools import Tool

# All sizes for a screen height of 1080 px, multiplied by ui_scale
CURSOR_ARM = 8          # length of the crosshair arms
CURSOR_GAP = 3          # distance of the arms from the circle
CURSOR_MARK = 8         # size of the tool shape at the bottom right
CURSOR_MIN_RADIUS = 2   # smallest circle, even for a very thin stroke


def round_pen(color, width):
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def contrast_stroke(p, path, color, width):
    """Dark outline first, then the color: visible on light and dark backgrounds."""
    p.setBrush(Qt.NoBrush)
    p.setPen(round_pen(QColor(0, 0, 0, 210), width + 2))
    p.drawPath(path)
    p.setPen(round_pen(color, width))
    p.drawPath(path)


def tool_mark(tool, size):
    """Small shape of the tool for the mouse cursor, centered on (0, 0)."""
    h = size / 2
    path = QPainterPath()
    if tool == Tool.RECT:
        path.addRoundedRect(QRectF(-h, -h * .75, size, size * .75), h * .3, h * .3)
    elif tool == Tool.ELLIPSE:
        path.addEllipse(QPointF(0, 0), h, h * .8)
    elif tool == Tool.LINE:
        path.moveTo(-h, h)
        path.lineTo(h, -h)
    elif tool == Tool.ARROW:
        path.moveTo(-h, h)
        path.lineTo(h, -h)
        path.moveTo(0, -h)
        path.lineTo(h, -h)
        path.lineTo(h, 0)
    elif tool == Tool.FREEHAND:
        path.moveTo(-h, h * .3)
        path.cubicTo(-h * .3, -h, h * .3, h, h, -h * .3)
    elif tool == Tool.MARKER:
        path.addEllipse(QPointF(0, 0), h, h)
        path.moveTo(-h * 0.2, -h * 0.35)
        path.lineTo(h * 0.15, -h * 0.6)
        path.lineTo(h * 0.15, h * 0.6)
    elif tool == Tool.BLUR:
        path.addRect(QRectF(-h, -h, size, size))
        path.moveTo(0, -h)
        path.lineTo(0, h)
        path.moveTo(-h, 0)
        path.lineTo(h, 0)
    elif tool == Tool.TEXT:
        path.moveTo(-h * .8, -h)
        path.lineTo(h * .8, -h)
        path.moveTo(0, -h)
        path.lineTo(0, h)
    return path


def make_cursor(tool, color, stroke_px, scale):
    """Crosshair mouse cursor; stroke_px = stroke width on screen (None = no circle)."""
    s = scale
    radius = max(CURSOR_MIN_RADIUS * s, (stroke_px or 0) / 2)
    radius = min(radius, 120 * s)  # huge zooms: do not make the cursor arbitrarily large
    inner, outer = radius + CURSOR_GAP * s, radius + (CURSOR_GAP + CURSOR_ARM) * s
    mark_at = outer + 2 * s
    half = math.ceil(max(outer, mark_at + CURSOR_MARK * s / 2) + 3 * s)
    pixmap = QPixmap(2 * half, 2 * half)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(half, half)
    arms = QPainterPath()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        arms.moveTo(dx * inner, dy * inner)
        arms.lineTo(dx * outer, dy * outer)
    contrast_stroke(p, arms, color, 1.5 * s)
    if stroke_px:  # thin circle: this is how wide the stroke will be
        faint = QColor(color)
        faint.setAlpha(170)
        p.setPen(QPen(QColor(0, 0, 0, 120), max(1.0, 0.8 * s) + 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), radius, radius)
        p.setPen(QPen(faint, max(1.0, 0.8 * s)))
        p.drawEllipse(QPointF(0, 0), radius, radius)
    p.translate(mark_at, mark_at)
    contrast_stroke(p, tool_mark(tool, CURSOR_MARK * s), color, 1.3 * s)
    p.end()
    return QCursor(pixmap, half, half)


def make_select_cursor(color, scale):
    """Mouse cursor of the select tool: arrow in the pen color (like the crosshair, because
    choosing a color here affects the selection), at the bottom right a small dashed
    selection frame (like the tool shape on the crosshair). Click point = arrow tip."""
    s = scale
    pad = math.ceil(2 * s)  # room for the outline around the tip
    k = 14 / 15 * s
    points = [(0, 0), (0, 15), (4, 11.5), (7, 18), (9.5, 17), (6.5, 10.5), (11.5, 10.5)]
    arrow = QPainterPath(QPointF(0, 0))
    for x, y in points[1:]:
        arrow.lineTo(x * k, y * k)
    arrow.closeSubpath()
    mark = QPainterPath()
    mark.addRect(QRectF(-4 * s, -4 * s, 8 * s, 8 * s))
    mark_at = QPointF(16 * s, 19 * s)
    size = math.ceil(mark_at.x() + 7 * s) + pad
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(pad, pad)
    p.setPen(QPen(QColor(0, 0, 0, 220), 1.4 * s))
    p.setBrush(color)
    p.drawPath(arrow)
    p.translate(mark_at)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 200), 3 * s))
    p.drawPath(mark)
    p.setPen(QPen(color, 1.3 * s, Qt.DashLine))
    p.drawPath(mark)
    p.end()
    return QCursor(pixmap, pad, pad)


class PointerMixin:
    # --- Mouse cursor ---
    def tool_cursor(self):
        """Mouse cursor for the current tool (select: arrow in the pen color with a frame,
        pointing: none, spotlight or magnifier mark the spot themselves)."""
        if self.pointer_mode:
            return QCursor(Qt.BlankCursor)
        if self.cropping:  # drawing a crop (canvas_crop.py)
            return QCursor(Qt.CrossCursor)
        color = self.adapt_color(self.pen_color) if self.board else QColor(self.pen_color)
        if self.tool == Tool.SELECT:
            key = ("select", color.name(), self.ui_scale)
            if key not in self.cursor_cache:
                self.cursor_cache[key] = make_select_cursor(color, self.ui_scale)
            return self.cursor_cache[key]
        stroke = None if self.tool == Tool.TEXT else self.pen_width * self.zoom()
        key = (self.tool, color.name(), None if stroke is None else round(stroke, 1), self.ui_scale)
        if key not in self.cursor_cache:
            self.cursor_cache[key] = make_cursor(self.tool, color, stroke, self.ui_scale)
        return self.cursor_cache[key]

    def refresh_cursor(self):
        """Call after a change of tool, color, size, zoom or background."""
        self.viewport().setCursor(self.tool_cursor())

    # --- Pointing: spotlight and magnifier ---
    def toggle_pointer(self, mode):
        """Turn mode on; if it is already on, turn it off."""
        self.pointer_mode = None if self.pointer_mode == mode else mode
        self.refresh_cursor()
        self.viewport().update()

    def stop_pointer(self):
        if self.pointer_mode:
            self.pointer_mode = None
            self.refresh_cursor()
            self.viewport().update()

    def paint_pointer(self, painter):
        """Draw spotlight or magnifier on top of everything (from drawForeground, in screen coordinates)."""
        if not self.pointer_mode:
            return
        pos = QPointF(self.viewport().mapFromGlobal(QCursor.pos()))
        view = QRectF(self.viewport().rect())
        if not view.contains(pos):
            return  # mouse on another monitor: darken nothing
        s = self.ui_scale
        painter.save()
        painter.resetTransform()  # from here on screen pixels instead of scene coordinates
        painter.setRenderHint(QPainter.Antialiasing)
        if self.pointer_mode == "spotlight":
            radius = self.settings.spotlight_radius * s  # [pointer] spotlight_radius
            dark = QPainterPath()
            dark.addRect(view)
            hole = QPainterPath()
            hole.addEllipse(pos, radius, radius)
            dim = round(self.settings.spotlight_dim * 2.55)  # percent -> opacity 0-255
            painter.fillPath(dark.subtracted(hole), QColor(0, 0, 0, dim))
            painter.setPen(QPen(QColor(255, 255, 255, 110), max(1.0, s)))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(pos, radius, radius)
        else:
            radius = self.settings.lens_radius * s  # [pointer] lens_radius
            target = QRectF(pos.x() - radius, pos.y() - radius, 2 * radius, 2 * radius)
            half = radius / (self.zoom() * self.settings.lens_zoom)  # half width of the area in the scene
            center = self.mapToScene(pos.toPoint())
            source = QRectF(center.x() - half, center.y() - half, 2 * half, 2 * half)
            circle = QPainterPath()
            circle.addEllipse(pos, radius, radius)
            painter.setClipPath(circle)
            painter.fillRect(target, self.backgroundBrush())  # border next to the image
            self.scene_.render(painter, target, source)       # draw the scene into it, enlarged
            painter.setClipping(False)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 200), 4 * s))
            painter.drawEllipse(pos, radius, radius)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5 * s))
            painter.drawEllipse(pos, radius, radius)
        painter.restore()
