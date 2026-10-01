"""Zeiger-Teil der Canvas: eigener Mauszeiger beim Zeichnen, Spotlight und Lupe zum Zeigen.

Mauszeiger (Zeichenwerkzeuge; beim Zeigen ausgeblendet): feines Fadenkreuz in der Stiftfarbe, in der Mitte ein
feiner Kreis so breit wie der Strich auf dem Bildschirm (Strichstärke × Zoom), rechts
unten klein die Form des Werkzeugs. Im Auswahl-Werkzeug bleibt der normale Pfeil.
Qt-Konzept: QCursor(QPixmap, x, y) macht aus einem selbst gezeichneten Bild einen
Mauszeiger; (x, y) ist der Klickpunkt (Hotspot), hier die Mitte.

Zeigen (zeichnet nichts, nie im Export):
- Spotlight (e): alles abgedunkelt bis auf einen Kreis um die Maus
- Lupe (Shift+E): vergrößerter Ausschnitt um die Maus
Dieselbe Taste oder Esc beendet, ein Werkzeugwechsel ebenso. Gezeichnet wird beides in
drawForeground (InputMixin) über paint_pointer().

Mixin wie BoardMixin (canvas_board.py). Verwaltet (angelegt in Canvas.__init__):
pointer_mode (None, "spotlight", "lens"), cursor_cache.
Liest aus der Canvas: tool, board, pen_color, pen_width, ui_scale, scene_, settings, zoom(),
adapt_color().
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap

from tools import Tool

# Alle Maße für 1080 px Bildschirmhöhe, werden mit ui_scale vervielfacht
CURSOR_ARM = 8          # Länge der Fadenkreuz-Arme
CURSOR_GAP = 3          # Abstand der Arme vom Kreis
CURSOR_MARK = 8         # Größe der Werkzeugform unten rechts
CURSOR_MIN_RADIUS = 2   # kleinster Kreis, auch bei sehr dünnem Strich


def round_pen(color, width):
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def contrast_stroke(p, path, color, width):
    """Erst dunkle Kontur, dann die Farbe: auf hellem und dunklem Grund sichtbar."""
    p.setBrush(Qt.NoBrush)
    p.setPen(round_pen(QColor(0, 0, 0, 210), width + 2))
    p.drawPath(path)
    p.setPen(round_pen(color, width))
    p.drawPath(path)


def tool_mark(tool, size):
    """Kleine Form des Werkzeugs für den Mauszeiger, zentriert auf (0, 0)."""
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
    elif tool == Tool.TEXT:
        path.moveTo(-h * .8, -h)
        path.lineTo(h * .8, -h)
        path.moveTo(0, -h)
        path.lineTo(0, h)
    return path


def make_cursor(tool, color, stroke_px, scale):
    """Fadenkreuz-Mauszeiger; stroke_px = Strichbreite auf dem Bildschirm (None = kein Kreis)."""
    s = scale
    radius = max(CURSOR_MIN_RADIUS * s, (stroke_px or 0) / 2)
    radius = min(radius, 120 * s)  # riesige Zooms: Zeiger nicht beliebig groß
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
    if stroke_px:  # feiner Kreis: so breit wird der Strich
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


class PointerMixin:
    # --- Mauszeiger ---
    def tool_cursor(self):
        """Mauszeiger für das aktuelle Werkzeug (Auswahl: normaler Pfeil, Zeigen: keiner,
        Spotlight bzw. Lupe markieren die Stelle selbst)."""
        if self.pointer_mode:
            return QCursor(Qt.BlankCursor)
        if self.tool == Tool.SELECT:
            return QCursor(Qt.ArrowCursor)
        color = self.adapt_color(self.pen_color) if self.board else QColor(self.pen_color)
        stroke = None if self.tool == Tool.TEXT else self.pen_width * self.zoom()
        key = (self.tool, color.name(), None if stroke is None else round(stroke, 1), self.ui_scale)
        if key not in self.cursor_cache:
            self.cursor_cache[key] = make_cursor(self.tool, color, stroke, self.ui_scale)
        return self.cursor_cache[key]

    def refresh_cursor(self):
        """Nach Wechsel von Werkzeug, Farbe, Größe, Zoom oder Hintergrund aufrufen."""
        self.viewport().setCursor(self.tool_cursor())

    # --- Zeigen: Spotlight und Lupe ---
    def toggle_pointer(self, mode):
        """mode an; ist er schon an, aus."""
        self.pointer_mode = None if self.pointer_mode == mode else mode
        self.refresh_cursor()
        self.viewport().update()

    def stop_pointer(self):
        if self.pointer_mode:
            self.pointer_mode = None
            self.refresh_cursor()
            self.viewport().update()

    def paint_pointer(self, painter):
        """Spotlight bzw. Lupe über allem zeichnen (aus drawForeground, in Bildschirmkoordinaten)."""
        if not self.pointer_mode:
            return
        pos = QPointF(self.viewport().mapFromGlobal(QCursor.pos()))
        view = QRectF(self.viewport().rect())
        if not view.contains(pos):
            return  # Maus auf einem anderen Monitor: nichts abdunkeln
        s = self.ui_scale
        painter.save()
        painter.resetTransform()  # ab hier Bildschirmpixel statt Szenenkoordinaten
        painter.setRenderHint(QPainter.Antialiasing)
        if self.pointer_mode == "spotlight":
            radius = self.settings.spotlight_radius * s  # [pointer] spotlight_radius
            dark = QPainterPath()
            dark.addRect(view)
            hole = QPainterPath()
            hole.addEllipse(pos, radius, radius)
            dim = round(self.settings.spotlight_dim * 2.55)  # Prozent -> Deckkraft 0-255
            painter.fillPath(dark.subtracted(hole), QColor(0, 0, 0, dim))
            painter.setPen(QPen(QColor(255, 255, 255, 110), max(1.0, s)))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(pos, radius, radius)
        else:
            radius = self.settings.lens_radius * s  # [pointer] lens_radius
            target = QRectF(pos.x() - radius, pos.y() - radius, 2 * radius, 2 * radius)
            half = radius / (self.zoom() * self.settings.lens_zoom)  # halbe Breite des Ausschnitts in der Szene
            center = self.mapToScene(pos.toPoint())
            source = QRectF(center.x() - half, center.y() - half, 2 * half, 2 * half)
            circle = QPainterPath()
            circle.addEllipse(pos, radius, radius)
            painter.setClipPath(circle)
            painter.fillRect(target, self.backgroundBrush())  # Rand neben dem Bild
            self.scene_.render(painter, target, source)       # Szene vergrößert hineinzeichnen
            painter.setClipping(False)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 200), 4 * s))
            painter.drawEllipse(pos, radius, radius)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5 * s))
            painter.drawEllipse(pos, radius, radius)
        painter.restore()
