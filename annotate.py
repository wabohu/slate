#!/usr/bin/env python3
"""Mini-Annotationstool (Meilenstein 1-4)

- Macht einen Screenshot des Monitors, auf dem der Mauszeiger steht
- Zeigt ihn eingefroren im Vollbild
- Linke Maustaste gedrückt halten und ziehen zum Zeichnen
- A S D F G: Werkzeug, in der Reihenfolge aus der Config
  (Standard: Freihand, Linie, Pfeil, Rechteck, Kreis/Ellipse)
- Shift+A S D F G Z X C V B: Farbe, in der Reihenfolge der Farbleiste
- Tab / Shift+Tab: durch die Farbpalette blättern, Klick auf die Leiste unten wählt
- U: letztes Objekt zurücknehmen
- Esc: beenden
"""
import math
import sys
from enum import Enum

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
)

from colors import load_palette
from config import get_list, get_str, load_config
from ui import PaletteBar


# --- Werkzeuge ---------------------------------------------------------------
class Tool(Enum):
    FREEHAND = "Freihand"
    LINE = "Linie"
    ARROW = "Pfeil"
    RECT = "Rechteck"
    ELLIPSE = "Kreis / Ellipse"


# Taste -> Werkzeug an dieser Position der Werkzeug-Reihenfolge ([tools] order in der Config).
# Qt meldet den Buchstaben, nicht die Tastenposition.
TOOL_KEYS = (Qt.Key_A, Qt.Key_S, Qt.Key_D, Qt.Key_F, Qt.Key_G)

# Fallbacks, wenn die eigene Config fehlt oder unbrauchbare Werte enthält
DEFAULT_TOOL = Tool.FREEHAND
DEFAULT_COLOR = "red"

# Eckenradius des Rechtecks in Pixeln
RECT_RADIUS = 8


def parse_tool(name):
    """Config-Name ('freehand', 'Rect', …) -> Tool; unbekannt -> None."""
    return Tool.__members__.get(name.strip().upper())


def tool_order(names):
    """Werkzeuge in der Reihenfolge der Config, ohne Unbekannte und Duplikate.

    Ohne brauchbare Liste: alle Werkzeuge in Reihenfolge des Enums.
    """
    result = []
    for name in names or []:
        tool = parse_tool(name)
        if tool is None:
            print(f"[tools] Unbekanntes Werkzeug: {name!r}", file=sys.stderr)
        elif tool not in result:
            result.append(tool)
    return result or list(Tool)

# Shift+Taste -> Feld der Farbleiste (Position in dieser Liste = Index in der Leiste).
# Hat die Palette weniger Felder, sind die hinteren Kürzel einfach ohne Wirkung.
COLOR_KEYS = (
    Qt.Key_A, Qt.Key_S, Qt.Key_D, Qt.Key_F, Qt.Key_G,
    Qt.Key_Z, Qt.Key_X, Qt.Key_C, Qt.Key_V, Qt.Key_B,
)


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
        # Qt verkleinert den Radius selbst, wenn das Rechteck dafür zu klein ist
        path.addRoundedRect(QRectF(start, end).normalized(), RECT_RADIUS, RECT_RADIUS)
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

        config = load_config()

        # Werkzeuge: Reihenfolge (= Tastenbelegung) und Startwerkzeug aus der Config
        self.tools = tool_order(get_list(config, "tools", "order"))
        self.tool = parse_tool(get_str(config, "tools", "default") or "") or DEFAULT_TOOL
        self.pen_width = 4

        # Farbwerte aus der Alacritty-Config (Fallback: Standardpalette),
        # Auswahl, Reihenfolge und Startfarbe aus der eigenen Config
        self.palette_ = load_palette()
        self.swatches = self.palette_.swatches(get_list(config, "colors", "order"))
        self.colors = [QColor(c) for c in self.swatches]
        default_color = get_str(config, "colors", "default") or DEFAULT_COLOR
        self.color_index = self.index_of(self.palette_.lookup(default_color))
        self.pen_color = self.colors[self.color_index]

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

        # Farbleiste unten; Klick darauf ruft set_color() auf
        self.palette_bar = PaletteBar(self.swatches, self)
        self.palette_bar.colorSelected.connect(self.set_color)
        self.place_palette_bar()

        self.set_tool(self.tool)
        self.set_color(self.color_index)

    def index_of(self, hex_color):
        """Position einer Farbe in der Leiste; fehlt sie, das erste Feld."""
        return self.swatches.index(hex_color) if hex_color in self.swatches else 0

    def set_tool(self, tool):
        self.tool = tool
        self.update_tool_label()

    def set_color(self, index):
        """Farbe für neue Objekte; bereits gezeichnete behalten ihre Farbe."""
        self.color_index = index % len(self.colors)
        self.pen_color = self.colors[self.color_index]
        self.palette_bar.set_active(self.color_index)
        self.update_tool_label()

    def update_tool_label(self):
        # QLabel versteht einfaches HTML ("Rich Text"): so bekommt der Punkt eine eigene Farbe
        dot = f'<span style="color:{self.pen_color.name()}">●</span>'
        self.tool_label.setText(f"{dot}&nbsp;&nbsp;{self.tool.value}&nbsp;&nbsp;&nbsp;&nbsp;[A S D F G]")
        self.tool_label.adjustSize()

    def place_palette_bar(self):
        bar = self.palette_bar
        bar.move((self.width() - bar.width()) // 2, self.height() - bar.height() - 20)

    def resizeEvent(self, event):
        # showFullScreen() ändert die Größe erst nach __init__, darum hier neu platzieren
        super().resizeEvent(event)
        if hasattr(self, "palette_bar"):  # kann schon im Konstruktor kommen
            self.place_palette_bar()

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
    def event(self, event):
        # Tab/Shift+Tab würde Qt sonst für den Fokuswechsel zwischen Widgets schlucken
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_Escape:
            self.close()
        elif mods & Qt.ShiftModifier and key in COLOR_KEYS:
            # Muss vor TOOL_KEYS stehen, sonst würde Shift+A auch das Werkzeug wechseln
            index = COLOR_KEYS.index(key)
            if index < len(self.colors):
                self.set_color(index)
        elif key == Qt.Key_Backtab or (key == Qt.Key_Tab and mods & Qt.ShiftModifier):
            self.set_color(self.color_index - 1)
        elif key == Qt.Key_Tab:
            self.set_color(self.color_index + 1)
        elif key == Qt.Key_U:
            if self.items_drawn:
                self.scene_.removeItem(self.items_drawn.pop())
        elif key in TOOL_KEYS and not mods & Qt.ControlModifier:
            # Ohne Strg, damit z. B. ein späteres Strg+S nicht das Werkzeug wechselt
            index = TOOL_KEYS.index(key)
            if index < len(self.tools):
                self.set_tool(self.tools[index])


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
