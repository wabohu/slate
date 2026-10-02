"""Zeichenelemente: Grafikobjekte, die ihre eigenen Werte kennen.

Jedes Element hat eine feste ID und speichert seine Geometrie in lokalen
Koordinaten. Qt-Konzept: Jedes QGraphicsItem hat ein eigenes Koordinatensystem;
pos() und rotation() bilden es in die Szene ab. Verschieben ändert also nur pos,
Drehen nur rotation, die Punkte selbst bleiben unverändert.
"""
import base64
import math
import uuid

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsTextItem, QStyle,
                               QStyleOptionGraphicsItem)

from colors import contrast
from tools import RECT_RADIUS, Tool, marker_radius, shape_path




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


# Unschärfe: Klotzgröße = Strichstärke × Faktor (Stufen 2/4/8/12 px -> 6/12/24/36 px Klötze)
BLUR_BLOCK_FACTOR = 3
BLUR_MIN_BLOCK = 4


def blur_block(width):
    return max(BLUR_MIN_BLOCK, round(width * BLUR_BLOCK_FACTOR))


def pixelate(image, rect, block):
    """Ausschnitt rect (Bildpixel) von image verpixelt: verkleinern (Mittelwert je Klotz),
    dann ohne Glättung wieder vergrößern. Rückgabe: (QImage, benutzter Ausschnitt als QRect)
    oder None, wenn rect ganz außerhalb des Bildes liegt."""
    rect = rect.toAlignedRect().intersected(image.rect())
    if rect.isEmpty():
        return None
    part = image.copy(rect)
    small = part.scaled(max(1, round(part.width() / block)), max(1, round(part.height() / block)),
                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return small.scaled(part.width(), part.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation), rect


def marker_text(rank, kind):
    """1, 2, 3 … bzw. A, B, … Z, AA, AB …"""
    if kind != "letter":
        return str(rank)
    text = ""
    while rank > 0:
        rank, rest = divmod(rank - 1, 26)
        text = chr(ord("A") + rest) + text
    return text


def shown_color(item, color):
    """Farbe, wie das Element sie zeigt. color ist die Grundfarbe (wird gespeichert);
    die Szene kann sie an den Hintergrund anpassen (Canvas.adapt_color, z. B. auf
    hellem Whiteboard abdunkeln). Ohne Szene oder ohne Anpassung: unverändert."""
    adapt = getattr(item.scene(), "adapt_color", None)
    return adapt(color) if adapt else QColor(color)


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
        self._blur_cache = None  # Unschärfe: zuletzt berechnetes Bild
        self.setFlag(QGraphicsPathItem.ItemIsSelectable)  # Qt verwaltet Auswahl + Markierung
        self.id = element_id or new_id()
        self.tool = tool
        self.color = QColor(color)
        self.width = width
        self.radius = radius
        # Marker: Zahlen oder Buchstaben, Reihenfolge des Setzens (die Nummer ist der Platz darin)
        self.marker_kind = "number"
        self.marker_order = 0
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
            **({"kind": self.marker_kind, "order": self.marker_order} if self.tool == Tool.MARKER else {}),
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
        if tool == Tool.MARKER:
            item.marker_kind = "letter" if data.get("kind") == "letter" else "number"
            order = data.get("order", 0)
            if isinstance(order, bool) or not isinstance(order, (int, float)):
                raise ValueError(f"order {order!r} ungültig")
            item.marker_order = order
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
        if self.tool == Tool.MARKER:  # Kreis ganz, dazu die Zeigelinie
            tip, center = self.points
            r = marker_radius(self.width) + 1
            path = QPainterPath()
            path.addEllipse(center, r, r)
            if distance(tip, center) > 1:
                line = QPainterPath(tip)
                line.lineTo(center)
                stroker = QPainterPathStroker()
                stroker.setWidth(8)
                stroker.setCapStyle(Qt.RoundCap)
                path = path.united(stroker.createStroke(line))
            return path
        if self.tool == Tool.BLUR:  # gefüllte Fläche: Treffer auch innen (D2)
            path = QPainterPath()
            path.addRect(self.path().boundingRect())
            return path
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
        if self.tool == Tool.BLUR:
            self.paint_blur(painter)
            return
        if self.tool == Tool.MARKER:
            self.paint_marker(painter)
            return
        super().paint(painter, without_selection_highlight(option), widget)

    def blur_image(self):
        """Verpixelter Screenshot unter diesem Element: (QImage, Ziel in lokalen Koordinaten) oder None.
        Die Szene liefert das Rohbild (blur_source) und den Maßstab Bildpixel je Szeneneinheit."""
        scene = self.scene()
        source = getattr(scene, "blur_source", None)
        if source is None:
            return None
        factor = getattr(scene, "blur_scale", 1.0)
        local = self.path().boundingRect()
        in_scene = self.mapRectToScene(local)
        in_image = QRectF(in_scene.x() * factor, in_scene.y() * factor,
                          in_scene.width() * factor, in_scene.height() * factor)
        key = (in_image.getRect(), self.width, source.cacheKey())
        if self._blur_cache is None or self._blur_cache[0] != key:
            result = pixelate(source, in_image, blur_block(self.width) * factor)
            self._blur_cache = (key, result)
        result = self._blur_cache[1]
        if result is None:
            return None
        image, used = result
        # Zielrechteck lokal: der tatsächlich benutzte Bildausschnitt, zurück in Szeneneinheiten
        target = self.mapRectFromScene(QRectF(used.x() / factor, used.y() / factor,
                                              used.width() / factor, used.height() / factor))
        return image, target

    # --- Marker ---
    def marker_label(self):
        """Nummer bzw. Buchstabe: Platz unter allen Markern derselben Art in der Szene,
        sortiert nach Reihenfolge des Setzens. Löschen nummeriert die übrigen neu."""
        scene = self.scene()
        same = [i for i in (scene.items() if scene else [self])
                if isinstance(i, ShapeElement) and i.tool == Tool.MARKER and i.marker_kind == self.marker_kind]
        same.sort(key=lambda i: (i.marker_order, i.id))
        rank = same.index(self) + 1 if self in same else 1
        return marker_text(rank, self.marker_kind)

    def paint_marker(self, painter):
        tip, center = self.points
        color = shown_color(self, self.color)
        r = marker_radius(self.width)
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        if distance(tip, center) > 1:  # Zeigelinie mit Punkt an der Spitze
            line_w = max(2.0, r * 0.16)
            for pen_color, extra in ((QColor(0, 0, 0, 120), 2.0), (color, 0.0)):
                pen = QPen(pen_color, line_w + extra)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(tip, center)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(tip, line_w * 1.4, line_w * 1.4)
        painter.setPen(QPen(QColor(0, 0, 0, 120), max(1.0, r * 0.08)))
        painter.setBrush(color)
        painter.drawEllipse(center, r, r)
        font = QFont()
        font.setBold(True)
        label = self.marker_label()
        font.setPixelSize(max(1, round(r * (1.15 if len(label) < 2 else 0.9))))
        painter.setFont(font)
        dark = QColor("#1a1b26")
        painter.setPen(dark if contrast(color.name(), dark.name()) > contrast(color.name(), "#ffffff")
                       else QColor("white"))
        painter.drawText(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r), Qt.AlignCenter, label)

    def paint_blur(self, painter):
        blurred = self.blur_image()
        if blurred is None:  # ohne Screenshot (z. B. Whiteboard): nur schraffierter Rahmen
            painter.setPen(QPen(QColor(128, 128, 128), 1, Qt.DashLine))
            painter.setBrush(QColor(128, 128, 128, 60))
            painter.drawRect(self.path().boundingRect())
            return
        image, target = blurred
        painter.drawImage(target, image)

    # Qt-Konzept: itemChange meldet Änderungen am Item, hier "in eine Szene gelegt".
    # Erst dann ist bekannt, auf welchem Hintergrund es liegt, also Farbe neu bestimmen.
    def itemChange(self, change, value):
        if change == QGraphicsPathItem.ItemSceneHasChanged:
            self.refresh_color()
        return super().itemChange(change, value)

    def refresh_color(self):
        """Gezeigte Farbe neu bestimmen (nach Hintergrundwechsel)."""
        self.update_pen()

    # --- Griffe zum Größe ändern (Auswahl-Werkzeug) ---
    def handle_points(self):
        """Griffpunkte in lokalen Koordinaten: Endpunkte bei Linie/Pfeil, sonst 4 Ecken."""
        if self.tool in (Tool.LINE, Tool.ARROW, Tool.MARKER):  # Marker: Spitze und Kreis
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
        if self.tool in (Tool.LINE, Tool.ARROW, Tool.MARKER):
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
        pen = QPen(shown_color(self, self.color), self.width)
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

    # color = Grundfarbe (wird gespeichert), gezeigt wird die an den Hintergrund
    # angepasste Variante (siehe shown_color); Text und Form haben dieselbe Schnittstelle
    @property
    def color(self):
        return QColor(self._color)

    def set_color(self, color):
        self._color = QColor(color)
        self.refresh_color()

    def refresh_color(self):
        """Gezeigte Farbe neu bestimmen (nach Hintergrundwechsel)."""
        self.setDefaultTextColor(shown_color(self, self._color))

    def itemChange(self, change, value):
        if change == QGraphicsTextItem.ItemSceneHasChanged:  # siehe ShapeElement.itemChange
            self.refresh_color()
        return super().itemChange(change, value)

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


class ImageElement(QGraphicsItem):
    """Bild (z. B. ein eingefügter Screenshot-Ausschnitt im Whiteboard).

    image: das Bild in voller Auflösung; size: angezeigte Größe in Szeneneinheiten.
    Griffe an den Ecken ändern die Größe mit festem Seitenverhältnis. Farbe und
    Strichstärke gibt es nicht: set_color tut nichts, Größen-Tasten lassen es aus.
    """

    def __init__(self, origin, image, size=None, element_id=None):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.id = element_id or new_id()
        self.image = QImage(image)
        self.size = QSizeF(size) if size is not None else QSizeF(self.image.size())
        self.color = QColor("#000000")  # nur damit Farb-Vergleiche bei einer Auswahl funktionieren
        self.setPos(origin)

    # --- Qt: Fläche und Zeichnen ---
    def boundingRect(self):
        return QRectF(QPointF(0, 0), self.size)

    def shape(self):  # Treffer auf der ganzen Fläche
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.boundingRect(), self.image)

    def set_color(self, color):
        """Bilder haben keine Stiftfarbe; Farbwechsel bei einer Auswahl lassen sie aus."""

    def refresh_color(self):
        """Nichts anzupassen (kein Stift)."""

    # --- Griffe: Größe mit festem Seitenverhältnis ---
    def handle_points(self):
        return corners(self.boundingRect())

    def geometry(self):
        return (QPointF(self.pos()), QSizeF(self.size))

    def set_geometry(self, state):
        pos, size = state
        self.prepareGeometryChange()  # Qt-Konzept: vor jeder Änderung von boundingRect melden
        self.size = QSizeF(size)
        self.setPos(pos)

    def drag_handle(self, index, scene_pos, start):
        """Ecke index nach scene_pos; gegenüberliegende Ecke bleibt, Seitenverhältnis fest."""
        start_pos, start_size = start
        box = corners(QRectF(start_pos, start_size))
        fixed = box[(index + 2) % 4]
        ratio = start_size.width() / max(1e-6, start_size.height())
        width = max(8.0, abs(scene_pos.x() - fixed.x()), abs(scene_pos.y() - fixed.y()) * ratio)
        size = QSizeF(width, width / ratio)
        left = fixed.x() - size.width() if scene_pos.x() < fixed.x() else fixed.x()
        top = fixed.y() - size.height() if scene_pos.y() < fixed.y() else fixed.y()
        self.set_geometry((QPointF(left, top), size))

    # --- Speichern / Laden ---
    def to_dict(self):
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        self.image.save(buffer, "PNG")
        return {
            "type": "image",
            "id": self.id,
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.rotation(),
            "size": [self.size.width(), self.size.height()],
            "png": base64.b64encode(bytes(buffer.data())).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, data):
        image = QImage.fromData(base64.b64decode(data["png"]))
        if image.isNull():
            raise ValueError("Bild unlesbar")
        width, height = (float(v) for v in data["size"])
        if width <= 0 or height <= 0:
            raise ValueError("Bildgröße muss positiv sein")
        item = cls(QPointF(*data["pos"]), image, QSizeF(width, height), element_id=data.get("id"))
        item.setRotation(data.get("rotation", 0))
        return item
