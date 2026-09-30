"""Zeichenelemente: Grafikobjekte, die ihre eigenen Werte kennen.

Jedes Element hat eine feste ID und speichert seine Geometrie in lokalen
Koordinaten. Qt-Konzept: Jedes QGraphicsItem hat ein eigenes Koordinatensystem;
pos() und rotation() bilden es in die Szene ab. Verschieben ändert also nur pos,
Drehen nur rotation, die Punkte selbst bleiben unverändert.
"""
import uuid

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem

from tools import Tool, shape_path


def new_id():
    """Eindeutige Kennung, z. B. für Verbinder und Speichern."""
    return uuid.uuid4().hex


class ShapeElement(QGraphicsPathItem):
    """Freihand, Linie, Pfeil, Rechteck oder Ellipse.

    points (lokal, relativ zu pos):
      Freihand: alle Punkte des Strichs
      sonst:    [Start, Ende]
    """

    def __init__(self, tool, origin, color, width, element_id=None):
        super().__init__()
        self.id = element_id or new_id()
        self.tool = tool
        self.color = QColor(color)
        self.width = width
        self.setPos(origin)  # Startpunkt = Ursprung des Elements
        start = QPointF(0, 0)
        self.points = [start] if tool == Tool.FREEHAND else [start, start]
        self.update_pen()
        self.rebuild()

    # --- Werte ändern ---
    def set_color(self, color):
        self.color = QColor(color)
        self.update_pen()

    def set_width(self, width):
        self.width = width
        self.update_pen()
        self.rebuild()  # z. B. Pfeilspitze hängt von der Strichstärke ab

    def set_end(self, scene_pos):
        """Endpunkt einer Zwei-Punkt-Form setzen (beim Aufziehen mit der Maus)."""
        self.points[1] = self.mapFromScene(scene_pos)
        self.rebuild()

    def add_point(self, scene_pos):
        """Freihand: Punkt anhängen. Verlängert den Pfad, statt ihn neu zu bauen."""
        local = self.mapFromScene(scene_pos)
        self.points.append(local)
        path = self.path()
        path.lineTo(local)
        self.setPath(path)

    # --- Aufbau aus den Werten ---
    def update_pen(self):
        pen = QPen(self.color, self.width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)

    def rebuild(self):
        """Pfad komplett aus tool und points neu berechnen."""
        if self.tool == Tool.FREEHAND:
            first = self.points[0]
            path = QPainterPath(first)
            # Kleiner Startstrich, damit auch ein einzelner Klick einen Punkt zeichnet
            path.lineTo(first.x() + 0.01, first.y())
            for point in self.points[1:]:
                path.lineTo(point)
        else:
            path = shape_path(self.tool, self.points[0], self.points[1], self.width)
        self.setPath(path)
