#!/usr/bin/env python3
"""Mini-Annotationstool (Meilenstein 1-3)

- Macht einen Screenshot des Monitors, auf dem der Mauszeiger steht
- Zeigt ihn eingefroren im Vollbild
- Linke Maustaste gedrückt halten und ziehen zum Zeichnen
- 1 Freihand | 2 Linie | 3 Pfeil | 4 Rechteck | 5 Kreis/Ellipse
- Strg+Z: letztes Objekt zurücknehmen
- Esc: beenden
"""
import math
import sys
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
)


# --- Werkzeuge ---------------------------------------------------------------
class Tool(Enum):
    FREEHAND = "Freihand"
    LINE = "Linie"
    ARROW = "Pfeil"
    RECT = "Rechteck"
    ELLIPSE = "Kreis / Ellipse"


TOOL_KEYS = {
    Qt.Key_1: Tool.FREEHAND,
    Qt.Key_2: Tool.LINE,
    Qt.Key_3: Tool.ARROW,
    Qt.Key_4: Tool.RECT,
    Qt.Key_5: Tool.ELLIPSE,
}


def shape_path(tool, start, end, pen_width):
    """Baut den Pfad einer Form aus Start- und Endpunkt (alles außer Freihand)."""
    path = QPainterPath()
    if tool == Tool.LINE:
        path.moveTo(start)
        path.lineTo(end)
    elif tool == Tool.ARROW:
        path.moveTo(start)
        path.lineTo(end)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = max(14, pen_width * 4)
        spread = math.radians(25)
        for sign in (-1, 1):
            tip = QPointF(
                end.x() - head_len * math.cos(angle + sign * spread),
                end.y() - head_len * math.sin(angle + sign * spread),
            )
            path.moveTo(end)
            path.lineTo(tip)
    elif tool == Tool.RECT:
        path.addRect(QRectF(start, end).normalized())
    elif tool == Tool.ELLIPSE:
        path.addEllipse(QRectF(start, end).normalized())
    return path


# --- Capture -----------------------------------------------------------------
def grab_screen():
    """Screenshot des Monitors unter dem Mauszeiger (X11)."""
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    return screen, screen.grabWindow(0)


# --- Zeichenfläche -----------------------------------------------------------
class Canvas(QGraphicsView):
    def __init__(self, screen, pixmap):
        super().__init__()

        # Szene mit dem Screenshot als Hintergrund
        self.scene_ = QGraphicsScene(self)
        self.scene_.addPixmap(pixmap)
        self.setScene(self.scene_)

        # Fenster: rahmenlos, im Vordergrund, exakt auf dem Monitor
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setGeometry(screen.geometry())
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.Antialiasing)
        self.setCursor(Qt.CrossCursor)

        # Aktuelle Einstellungen (später per Toolbar änderbar)
        self.tool = Tool.FREEHAND
        self.pen_color = QColor("#ff2d2d")
        self.pen_width = 4

        # Zustand
        self.items_drawn = []  # für Undo
        self.current_item = None
        self.current_path = None  # nur für Freihand
        self.start_pos = None

        # Kleine Anzeige des aktiven Werkzeugs
        self.tool_label = QLabel(self)
        self.tool_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.tool_label.setStyleSheet(
            "background: rgba(20, 20, 20, 190); color: white;"
            "padding: 6px 12px; border-radius: 6px; font-size: 14px;"
        )
        self.tool_label.move(20, 20)
        self.set_tool(self.tool)

    def set_tool(self, tool):
        self.tool = tool
        self.tool_label.setText(f"{tool.value}    [1-5]")
        self.tool_label.adjustSize()

    def make_pen(self):
        pen = QPen(self.pen_color, self.pen_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    # --- Maus ---
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = self.mapToScene(event.position().toPoint())
        self.start_pos = pos

        if self.tool == Tool.FREEHAND:
            self.current_path = QPainterPath(pos)
            # Kleiner Startpunkt, damit auch ein einzelner Klick einen Punkt zeichnet
            self.current_path.lineTo(pos.x() + 0.01, pos.y())
            path = self.current_path
        else:
            path = shape_path(self.tool, pos, pos, self.pen_width)

        self.current_item = QGraphicsPathItem(path)
        self.current_item.setPen(self.make_pen())
        self.scene_.addItem(self.current_item)

    def mouseMoveEvent(self, event):
        if self.current_item is None:
            return
        pos = self.mapToScene(event.position().toPoint())
        if self.tool == Tool.FREEHAND:
            self.current_path.lineTo(pos)
            self.current_item.setPath(self.current_path)
        else:
            self.current_item.setPath(
                shape_path(self.tool, self.start_pos, pos, self.pen_width)
            )

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.current_item is None:
            return
        pos = self.mapToScene(event.position().toPoint())
        # Versehentlicher Klick ohne Ziehen: leere Form wieder wegwerfen
        too_small = (pos - self.start_pos).manhattanLength() < 3
        if self.tool != Tool.FREEHAND and too_small:
            self.scene_.removeItem(self.current_item)
        else:
            self.items_drawn.append(self.current_item)
        self.current_item = None
        self.current_path = None
        self.start_pos = None

    # --- Tastatur ---
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.close()
        elif key in TOOL_KEYS:
            self.set_tool(TOOL_KEYS[key])
        elif key == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            if self.items_drawn:
                self.scene_.removeItem(self.items_drawn.pop())


# --- Start -------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    screen, pixmap = grab_screen()  # erst grabben, dann Fenster zeigen!
    canvas = Canvas(screen, pixmap)
    canvas.showFullScreen()
    canvas.activateWindow()
    canvas.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
