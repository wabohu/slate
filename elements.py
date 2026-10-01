"""Zeichenelemente: Grafikobjekte, die ihre eigenen Werte kennen.

Jedes Element hat eine feste ID und speichert seine Geometrie in lokalen
Koordinaten. Qt-Konzept: Jedes QGraphicsItem hat ein eigenes Koordinatensystem;
pos() und rotation() bilden es in die Szene ab. Verschieben ändert also nur pos,
Drehen nur rotation, die Punkte selbst bleiben unverändert.
"""
import math
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsTextItem, QStyle, QStyleOptionGraphicsItem

from tools import RECT_RADIUS, Tool, shape_path




def new_id():
    """Eindeutige Kennung, z. B. für Verbinder und Speichern."""
    return uuid.uuid4().hex


def corners(rect):
    """Ecken eines Rechtecks in fester Reihenfolge: oben links, oben rechts, unten rechts,
    unten links. Die gegenüberliegende Ecke von i ist (i + 2) % 4."""
    return [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]


def without_selection_highlight(option):
    """Kopie der Zeichen-Optionen ohne "ausgewählt": Qt soll seinen eigenen gestrichelten
    Rahmen nicht zeichnen, die Canvas zeichnet Rahmen und Griffe selbst."""
    option = QStyleOptionGraphicsItem(option)
    option.state &= ~QStyle.State_Selected
    return option


def scale_factor(new, fixed, old):
    """Streckfaktor entlang einer Achse; bei (fast) null Ausdehnung nicht strecken."""
    return (new - fixed) / (old - fixed) if abs(old - fixed) > 0.5 else 1.0


def distance(a, b):
    return math.hypot(a.x() - b.x(), a.y() - b.y())


class ShapeElement(QGraphicsPathItem):
    """Freihand, Linie, Pfeil, Rechteck oder Ellipse.

    points (lokal, relativ zu pos):
      Freihand: alle Punkte des Strichs
      sonst:    [Start, Ende]
    radius: Eckenradius, nur für Rechtecke
    """

    def __init__(self, tool, origin, color, width, element_id=None, radius=RECT_RADIUS):
        super().__init__()
        self._hit_shape = None  # Zwischenspeicher für shape(), siehe unten
        self.setFlag(QGraphicsPathItem.ItemIsSelectable)  # Qt verwaltet Auswahl + Markierung
        self.id = element_id or new_id()
        self.tool = tool
        self.color = QColor(color)
        self.width = width
        self.radius = radius
        self.setPos(origin)  # Startpunkt = Ursprung des Elements
        start = QPointF(0, 0)
        self.points = [start] if tool == Tool.FREEHAND else [start, start]
        self.update_pen()
        self.rebuild()

    # --- Speichern / Laden (document.py) ---
    def to_dict(self):
        """Alle Werte als einfache Python-Daten (JSON-tauglich). Farben als "#rrggbb"."""
        return {
            "type": "shape",
            "id": self.id,
            "tool": self.tool.name.lower(),
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.rotation(),
            "points": [[p.x(), p.y()] for p in self.points],
            "color": self.color.name(),
            "width": self.width,
            **({"radius": self.radius} if self.tool == Tool.RECT else {}),
        }

    @classmethod
    def from_dict(cls, data):
        """Gegenstück zu to_dict. Fehlerhafte Daten lösen KeyError/ValueError/TypeError aus."""
        tool = Tool[data["tool"].upper()]
        # Ältere Dateien ohne "radius": bisheriger Standard, sieht also aus wie damals
        radius = data.get("radius", RECT_RADIUS)
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius < 0:
            raise ValueError(f"radius {radius!r} ungültig")
        item = cls(tool, QPointF(*data["pos"]), data["color"], data["width"],
                   element_id=data.get("id"), radius=radius)
        item.points = [QPointF(x, y) for x, y in data["points"]]
        expected = None if tool == Tool.FREEHAND else 2
        if not item.points or (expected and len(item.points) != expected):
            raise ValueError(f"{tool.name}: falsche Anzahl Punkte")
        item.setRotation(data.get("rotation", 0))
        item.rebuild()
        return item

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

    # --- Treffer beim Anklicken (D2: nur der Rand) ---
    # Qt fragt shape() für Klicks und boundingRect() für Neuzeichnen und Suche.
    # Standard bei geschlossenen Pfaden wäre: auch das Innere ist Treffer.
    # Die Toleranz neben dem Strich gibt die Canvas dazu (in Bildschirm-Pixeln, zoomunabhängig).
    def shape(self):
        if self._hit_shape is None:
            stroker = QPainterPathStroker()  # macht aus einer Linie eine Fläche dieser Breite
            stroker.setWidth(self.width + 2)
            stroker.setCapStyle(Qt.RoundCap)
            stroker.setJoinStyle(Qt.RoundJoin)
            self._hit_shape = stroker.createStroke(self.path())
        return self._hit_shape

    def boundingRect(self):
        return self.shape().boundingRect()  # muss die Trefferfläche ganz umschließen

    # Pfad oder Stift ändern sich -> Zwischenspeicher verwerfen (vor und nach dem
    # eigentlichen Setzen, weil Qt dazwischen noch das alte Rechteck abfragt)
    def setPath(self, path):
        self._hit_shape = None
        super().setPath(path)
        self._hit_shape = None

    def setPen(self, pen):
        self._hit_shape = None
        super().setPen(pen)
        self._hit_shape = None

    def paint(self, painter, option, widget=None):
        super().paint(painter, without_selection_highlight(option), widget)

    # --- Griffe zum Größe ändern (Auswahl-Werkzeug) ---
    def handle_points(self):
        """Griffpunkte in lokalen Koordinaten: Endpunkte bei Linie/Pfeil, sonst 4 Ecken."""
        if self.tool in (Tool.LINE, Tool.ARROW):
            return list(self.points)
        return corners(self.box(self.points))

    def box(self, points):
        """Umrandendes Rechteck der Geometrie (ohne Strichbreite)."""
        if self.tool == Tool.FREEHAND:
            return QPolygonF(points).boundingRect()
        return QRectF(points[0], points[1]).normalized()

    def geometry(self):
        """Alles, was sich beim Größe ändern ändern kann, für Undo (kopiert)."""
        return (QPointF(self.pos()), [QPointF(p) for p in self.points])

    def set_geometry(self, state):
        pos, points = state
        self.setPos(pos)
        self.points = [QPointF(p) for p in points]
        self.rebuild()

    def drag_handle(self, index, scene_pos, start):
        """Griff index wurde nach scene_pos gezogen; start = geometry() bei Zugbeginn."""
        local = self.mapFromScene(scene_pos)  # pos ändert sich beim Ziehen nicht
        points = [QPointF(p) for p in start[1]]
        if self.tool in (Tool.LINE, Tool.ARROW):
            points[index] = local
        elif self.tool == Tool.FREEHAND:
            # Alle Punkte strecken; die gegenüberliegende Ecke bleibt fest
            box = corners(self.box(points))
            fixed, handle = box[(index + 2) % 4], box[index]
            sx = scale_factor(local.x(), fixed.x(), handle.x())
            sy = scale_factor(local.y(), fixed.y(), handle.y())
            points = [QPointF(fixed.x() + (p.x() - fixed.x()) * sx,
                              fixed.y() + (p.y() - fixed.y()) * sy) for p in points]
        else:  # Rechteck, Ellipse: gegenüberliegende Ecke + neue Ecke
            points = [corners(self.box(points))[(index + 2) % 4], local]
        self.points = points
        self.rebuild()

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
            path = shape_path(self.tool, self.points[0], self.points[1], self.width, self.radius)
        self.setPath(path)


class TextElement(QGraphicsTextItem):
    """Textobjekt mit fester ID, Farbe und Schriftgröße (fett, in Pixeln).

    Später hängt eine Formbeschriftung als Kind-Item an einem ShapeElement (D5).
    """

    def __init__(self, origin, color, font_size, text="", element_id=None):
        super().__init__()
        self.setFlag(QGraphicsTextItem.ItemIsSelectable)
        self.id = element_id or new_id()
        self.set_font_size(font_size)
        self.set_color(color)
        self.setPlainText(text)
        self.setPos(origin)

    # Farbe steckt schon in QGraphicsTextItem; die Property gibt Text und Form dieselbe Schnittstelle
    @property
    def color(self):
        return self.defaultTextColor()

    def set_color(self, color):
        self.setDefaultTextColor(QColor(color))

    def set_font_size(self, size):
        self.font_size = size
        font = QFont()
        font.setPixelSize(size)
        font.setBold(True)
        self.setFont(font)

    def paint(self, painter, option, widget=None):
        super().paint(painter, without_selection_highlight(option), widget)

    # --- Griffe: Ziehen an einer Ecke skaliert die Schrift ---
    def handle_points(self):
        return corners(self.boundingRect())

    def geometry(self):
        return (QPointF(self.pos()), self.font_size)

    def set_geometry(self, state):
        pos, size = state
        self.set_font_size(size)
        self.setPos(pos)

    def drag_handle(self, index, scene_pos, start, size_range=(6, 300)):
        """Schriftgröße im Verhältnis der Diagonale; gegenüberliegende Ecke bleibt stehen."""
        start_pos, start_size = start
        self.set_geometry(start)  # vom Ausgangszustand aus rechnen, nicht schrittweise
        box = corners(self.boundingRect())
        fixed_local, handle_local = box[(index + 2) % 4], box[index]
        fixed_scene = start_pos + fixed_local
        ratio = (distance(scene_pos, fixed_scene)
                 / max(1.0, distance(start_pos + handle_local, fixed_scene)))
        low, high = size_range
        self.set_font_size(max(low, min(high, round(start_size * ratio))))
        # Neue Größe: Position so setzen, dass die feste Ecke an ihrem Platz bleibt
        self.setPos(fixed_scene - corners(self.boundingRect())[(index + 2) % 4])

    # --- Speichern / Laden (document.py) ---
    def to_dict(self):
        return {
            "type": "text",
            "id": self.id,
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.rotation(),
            "text": self.toPlainText(),
            "color": self.color.name(),
            "font_size": self.font_size,
        }

    @classmethod
    def from_dict(cls, data):
        item = cls(QPointF(*data["pos"]), data["color"], data["font_size"],
                   text=data["text"], element_id=data.get("id"))
        item.setRotation(data.get("rotation", 0))
        return item

    # --- Bearbeiten ---
    def start_editing(self):
        # TextEditorInteraction macht das Item zu einem kleinen Editor (Cursor, Tippen, Auswahl)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus()  # Tastatureingaben gehen jetzt über die Szene an dieses Item

    def stop_editing(self):
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.clearFocus()
