"""Werkzeuge: Enum, Namen aus der Config, Geometrie der Formen und Symbole.

Ohne Canvas-Abhängigkeiten, damit elements.py und annotate.py beide darauf
aufbauen können, ohne sich gegenseitig zu importieren.
"""
import math
import sys
from enum import Enum

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath


class Tool(Enum):
    FREEHAND = "Freihand"
    LINE = "Linie"
    ARROW = "Pfeil"
    RECT = "Rechteck"
    ELLIPSE = "Kreis / Ellipse"
    TEXT = "Text"
    SELECT = "Auswahl"  # kein Zeichenwerkzeug, steht in der Leiste immer vorne (Taste W)


# Eckenradius des Rechtecks in Pixeln (Standard; je Element in ShapeElement.radius,
# für neue Rechtecke aus [rect] in der Config)
RECT_RADIUS = 8


def parse_tool(name):
    """Config-Name ('freehand', 'Rect', …) -> Tool; unbekannt -> None."""
    return Tool.__members__.get(name.strip().upper())


def tool_order(names):
    """Werkzeuge in der Reihenfolge der Config, ohne Unbekannte und Duplikate.

    Ohne brauchbare Liste: alle Werkzeuge in Reihenfolge des Enums.
    Das Auswahl-Werkzeug gehört nicht dazu, es hat einen festen Platz.
    """
    result = []
    for name in names or []:
        tool = parse_tool(name)
        if tool is None:
            print(f"[tools] Unbekanntes Werkzeug: {name!r}", file=sys.stderr)
        elif tool not in result and tool != Tool.SELECT:
            result.append(tool)
    return result or [t for t in Tool if t != Tool.SELECT]


def shape_path(tool, start, end, pen_width, radius=RECT_RADIUS):
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
        path.addRoundedRect(QRectF(start, end).normalized(), radius, radius)
    elif tool == Tool.ELLIPSE:
        path.addEllipse(QRectF(start, end).normalized())
    return path


def tool_icon(tool):
    """Symbol für die Werkzeugleiste, in Feld-Koordinaten 0-30 (unten rechts bleibt Platz für die Taste)."""
    path = QPainterPath()
    if tool == Tool.FREEHAND:
        path.moveTo(6, 18)
        path.cubicTo(10, 4, 14, 26, 23, 9)
    elif tool == Tool.LINE:
        path.moveTo(7, 22)
        path.lineTo(22, 7)
    elif tool == Tool.ARROW:
        path.moveTo(7, 22)
        path.lineTo(22, 7)
        path.moveTo(14, 7)
        path.lineTo(22, 7)
        path.lineTo(22, 15)
    elif tool == Tool.RECT:
        path.addRoundedRect(QRectF(5, 8, 17, 12), 3, 3)
    elif tool == Tool.ELLIPSE:
        path.addEllipse(QRectF(5, 7, 17, 14))
    elif tool == Tool.TEXT:
        path.moveTo(8, 8)
        path.lineTo(22, 8)
        path.moveTo(15, 8)
        path.lineTo(15, 22)
    elif tool == Tool.SELECT:  # Mauszeiger
        path.moveTo(9, 5)
        path.lineTo(9, 21)
        path.lineTo(13, 17)
        path.lineTo(16, 23)
        path.lineTo(18.5, 22)
        path.lineTo(15.5, 16)
        path.lineTo(21, 16)
        path.closeSubpath()
    return path
