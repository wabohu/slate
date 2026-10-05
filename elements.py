"""Drawing elements: graphics objects that know their own values.

Every element has a fixed ID and stores its geometry in local
coordinates. Qt concept: every QGraphicsItem has its own coordinate system;
pos() and rotation() map it into the scene. Moving therefore only changes pos,
rotating only rotation, the points themselves stay unchanged.
"""
import base64
import math
import uuid

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainterPath, QPainterPathStroker, QPen, QPolygonF, QTextOption
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsTextItem, QStyle,
                               QStyleOptionGraphicsItem)

from colors import contrast
from tools import RECT_RADIUS, Tool, marker_radius, shape_path




def is_label(item):
    """Is item the label of a shape (part of it, not an element of its own)?

    Deliberately not via item.parentItem(): in PySide6 that call can hand the ownership
    of an item that only the scene holds back to Python, and the garbage collector then
    deletes it from the scene (seen when loading history entries). Labels therefore know
    their shape through their own attribute owner.
    """
    return getattr(item, "owner", None) is not None


def new_id():
    """Unique identifier, e.g. for connectors and saving."""
    return uuid.uuid4().hex


def corners(rect):
    """Corners of a rectangle in a fixed order: top left, top right, bottom right,
    bottom left. The opposite corner of i is (i + 2) % 4."""
    return [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]


def without_selection_highlight(option):
    """Copy of the paint options without "selected": Qt should not draw its own dashed
    frame, the Canvas draws frames and handles itself."""
    option = QStyleOptionGraphicsItem(option)
    option.state &= ~QStyle.State_Selected
    return option


# Labels (text in shapes, roadmap 15): only these shapes get one. Distance of the text from
# the outline, and the share of the width an ellipse leaves for the text (its rounding)
LABEL_TOOLS = (Tool.RECT, Tool.ELLIPSE)
LABEL_PADDING = 8
ELLIPSE_LABEL_SHARE = 0.7


class PoseMixin:
    """Position and rotation together, for rotating (Q / Shift+Q) with undo.

    Qt concept: rotation() turns the item around its own origin, the point pos()
    in the scene. To rotate around the middle instead, the Canvas also moves pos
    (canvas_input.rotate_selected). set_pose is a bound method, so the undo stack
    can merge several presses on the same element (PropertyCommand.mergeWith).
    """

    def pose(self):
        return (QPointF(self.pos()), self.rotation())

    def set_pose(self, state):
        pos, angle = state
        self.setRotation(angle)
        self.setPos(pos)


def scale_factor(new, fixed, old):
    """Stretch factor along one axis; do not stretch for (almost) zero extent."""
    return (new - fixed) / (old - fixed) if abs(old - fixed) > 0.5 else 1.0


def distance(a, b):
    return math.hypot(a.x() - b.x(), a.y() - b.y())


# Blur: block size = stroke width × factor (levels 2/4/8/12 px -> 6/12/24/36 px blocks)
BLUR_BLOCK_FACTOR = 3
BLUR_MIN_BLOCK = 4


def blur_block(width):
    return max(BLUR_MIN_BLOCK, round(width * BLUR_BLOCK_FACTOR))


def pixelate(image, rect, block):
    """Area rect (image pixels) of image pixelated: scale down (average per block),
    then scale up again without smoothing. Returns: (QImage, area used as QRect)
    or None if rect lies completely outside the image."""
    rect = rect.toAlignedRect().intersected(image.rect())
    if rect.isEmpty():
        return None
    part = image.copy(rect)
    small = part.scaled(max(1, round(part.width() / block)), max(1, round(part.height() / block)),
                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return small.scaled(part.width(), part.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation), rect


def marker_text(rank, kind):
    """1, 2, 3 … or A, B, … Z, AA, AB …"""
    if kind != "letter":
        return str(rank)
    text = ""
    while rank > 0:
        rank, rest = divmod(rank - 1, 26)
        text = chr(ord("A") + rest) + text
    return text


def shown_color(item, color):
    """Color as the element shows it. color is the base color (gets saved);
    the scene can adapt it to the background (Canvas.adapt_color, e.g. darken it
    on a light whiteboard). Without a scene or without adaptation: unchanged."""
    adapt = getattr(item.scene(), "adapt_color", None)
    return adapt(color) if adapt else QColor(color)


class ShapeElement(PoseMixin, QGraphicsPathItem):
    """Freehand, line, arrow, rectangle or ellipse.

    points (local, relative to pos):
      freehand: all points of the stroke
      others:   [start, end]
    radius: corner radius, only for rectangles
    """

    def __init__(self, tool, origin, color, width, element_id=None, radius=RECT_RADIUS):
        super().__init__()
        self._hit_shape = None  # cache for shape(), see below
        self._blur_cache = None  # blur: most recently computed image
        self.setFlag(QGraphicsPathItem.ItemIsSelectable)  # Qt manages selection + highlight
        self.id = element_id or new_id()
        self.tool = tool
        self.color = QColor(color)
        self.width = width
        self.radius = radius
        # Marker: numbers or letters, order of placement (the number is the rank in it)
        self.marker_kind = "number"
        self.marker_order = 0
        self.label = None  # rectangle/ellipse: TextElement as a child item, see set_label
        # Line/arrow: IDs of the elements its start and end are docked to (connectors.py)
        self.ends = [None, None]
        self.setPos(origin)  # start point = origin of the element
        start = QPointF(0, 0)
        self.points = [start] if tool == Tool.FREEHAND else [start, start]
        self.update_pen()
        self.rebuild()

    # --- Save / load (document.py) ---
    def to_dict(self):
        """All values as plain Python data (JSON-compatible). Colors as "#rrggbb"."""
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
            **({"label": {"text": self.label.toPlainText(), "font_size": self.label.font_size}}
               if self.label is not None else {}),
            **({"ends": list(self.ends)} if any(self.ends) else {}),
        }

    @classmethod
    def from_dict(cls, data):
        """Counterpart to to_dict. Broken data raises KeyError/ValueError/TypeError."""
        tool = Tool[data["tool"].upper()]
        label = data.get("label")  # optional; older files have none
        ends = data.get("ends", [None, None])  # line/arrow docked to elements; older files: free
        if (not isinstance(ends, list) or len(ends) != 2
                or not all(e is None or isinstance(e, str) for e in ends)):
            raise ValueError(f"ends {ends!r} invalid")
        # Older files without "radius": the previous default, so it looks like it did back then
        radius = data.get("radius", RECT_RADIUS)
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius < 0:
            raise ValueError(f"radius {radius!r} invalid")
        item = cls(tool, QPointF(*data["pos"]), data["color"], data["width"],
                   element_id=data.get("id"), radius=radius)
        item.points = [QPointF(x, y) for x, y in data["points"]]
        if tool == Tool.MARKER:
            item.marker_kind = "letter" if data.get("kind") == "letter" else "number"
            order = data.get("order", 0)
            if isinstance(order, bool) or not isinstance(order, (int, float)):
                raise ValueError(f"order {order!r} invalid")
            item.marker_order = order
        expected = None if tool == Tool.FREEHAND else 2
        if not item.points or (expected and len(item.points) != expected):
            raise ValueError(f"{tool.name}: wrong number of points")
        item.setRotation(data.get("rotation", 0))
        if tool in (Tool.LINE, Tool.ARROW):
            item.ends = list(ends)
        item.rebuild()
        if label is not None and tool in LABEL_TOOLS:
            text, size = label["text"], label["font_size"]
            if not isinstance(text, str) or isinstance(size, bool) or not isinstance(size, (int, float)) or size <= 0:
                raise ValueError(f"label {label!r} invalid")
            item.set_label(TextElement(QPointF(0, 0), item.color, size, text))
        return item

    # --- Label (text in the shape) ---
    def set_label(self, label):
        """Attach label (a TextElement) as the shape's text, or remove it (None).

        Qt concept child item: setParentItem(self) makes the text part of the shape. Its
        coordinates are then relative to the shape, and it moves, rotates and disappears
        together with it, without us doing anything. It is not selectable on its own:
        a click on it selects the shape (Canvas.element_at).
        """
        if self.label is not None and self.label is not label:
            old = self.label
            scene = old.scene()
            old.owner = None
            old.setParentItem(None)
            if scene is not None:  # without a parent it would otherwise stay in the scene on its own
                scene.removeItem(old)
        self.label = label
        if label is None:
            return
        label.owner = self  # see is_label
        label.setFlag(QGraphicsTextItem.ItemIsSelectable, False)
        label.document().setDefaultTextOption(QTextOption(Qt.AlignHCenter))  # lines centered
        label.setParentItem(self)
        label.set_color(self.color)
        self.layout_label()

    def layout_label(self):
        """Wrap the label at the width of the shape and put it in the middle.
        Called after resizing (rebuild), font size changes and while typing."""
        label = self.label
        if label is None:
            return
        box = self.box(self.points)
        share = ELLIPSE_LABEL_SHARE if self.tool == Tool.ELLIPSE else 1.0
        label.setTextWidth(max(label.font_size, box.width() * share - 2 * LABEL_PADDING))
        size = label.boundingRect().size()
        label.setPos(box.center() - QPointF(size.width() / 2, size.height() / 2))

    # --- Change values ---
    def set_color(self, color):
        self.color = QColor(color)
        self.update_pen()
        if self.label is not None:  # the label always has the color of the shape
            self.label.set_color(color)

    def set_width(self, width):
        self.width = width
        self.update_pen()
        self.rebuild()  # e.g. the arrow head depends on the stroke width

    def set_end(self, scene_pos):
        """Set the end point of a two-point shape (while drawing it with the mouse)."""
        self.points[1] = self.mapFromScene(scene_pos)
        self.rebuild()

    def add_point(self, scene_pos):
        """Freehand: append a point. Extends the path instead of rebuilding it."""
        local = self.mapFromScene(scene_pos)
        self.points.append(local)
        path = self.path()
        path.lineTo(local)
        self.setPath(path)

    # --- Hits when clicking (D2: only the outline) ---
    # Qt asks shape() for clicks and boundingRect() for repainting and searching.
    # The default for closed paths would be: the inside is a hit too.
    # The Canvas adds the tolerance next to the stroke (in screen pixels, independent of zoom).
    def shape(self):
        if self.tool == Tool.MARKER:  # the whole circle, plus the pointer line
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
        if self.tool == Tool.BLUR:  # filled area: a hit inside too (D2)
            path = QPainterPath()
            path.addRect(self.path().boundingRect())
            return path
        if self._hit_shape is None:
            stroker = QPainterPathStroker()  # turns a line into an area of this width
            stroker.setWidth(self.width + 2)
            stroker.setCapStyle(Qt.RoundCap)
            stroker.setJoinStyle(Qt.RoundJoin)
            self._hit_shape = stroker.createStroke(self.path())
        return self._hit_shape

    def boundingRect(self):
        return self.shape().boundingRect()  # must enclose the hit area completely

    # Path or pen change -> discard the cache (before and after the actual
    # setting, because Qt still asks for the old rectangle in between)
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
        """Pixelated screenshot under this element: (QImage, target in local coordinates) or None.
        The scene provides the raw image (blur_source) and the scale in image pixels per scene unit."""
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
        # Local target rectangle: the image area actually used, back in scene units
        target = self.mapRectFromScene(QRectF(used.x() / factor, used.y() / factor,
                                              used.width() / factor, used.height() / factor))
        return image, target

    # --- Marker ---
    def marker_label(self):
        """Number or letter: rank among all markers of the same kind in the scene,
        sorted by order of placement. Deleting renumbers the others."""
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
        if distance(tip, center) > 1:  # pointer line with a dot at the tip
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
        if blurred is None:  # without a screenshot (e.g. whiteboard): only a hatched frame
            painter.setPen(QPen(QColor(128, 128, 128), 1, Qt.DashLine))
            painter.setBrush(QColor(128, 128, 128, 60))
            painter.drawRect(self.path().boundingRect())
            return
        image, target = blurred
        painter.drawImage(target, image)

    # Qt concept: itemChange reports changes to the item, here "put into a scene".
    # Only then is it known which background it lies on, so determine the color again.
    def itemChange(self, change, value):
        if change == QGraphicsPathItem.ItemSceneHasChanged:
            self.refresh_color()
        return super().itemChange(change, value)

    def refresh_color(self):
        """Determine the shown color again (after a background change)."""
        self.update_pen()

    # --- Handles for resizing (select tool) ---
    def handle_points(self):
        """Handle points in local coordinates: end points for line/arrow, otherwise 4 corners."""
        if self.tool in (Tool.LINE, Tool.ARROW, Tool.MARKER):  # marker: tip and circle
            return list(self.points)
        return corners(self.box(self.points))

    def box(self, points):
        """Bounding rectangle of the geometry (without stroke width)."""
        if self.tool == Tool.FREEHAND:
            return QPolygonF(points).boundingRect()
        return QRectF(points[0], points[1]).normalized()

    def geometry(self):
        """Everything that can change when resizing, for undo (copied). For lines/arrows
        that includes where their ends are docked (re-docking via a handle is one undo step)."""
        return (QPointF(self.pos()), [QPointF(p) for p in self.points], tuple(self.ends))

    def set_geometry(self, state):
        pos, points, ends = state
        self.setPos(pos)
        self.points = [QPointF(p) for p in points]
        self.ends = list(ends)
        self.rebuild()

    def drag_handle(self, index, scene_pos, start):
        """Handle index was dragged to scene_pos; start = geometry() at drag start."""
        local = self.mapFromScene(scene_pos)  # pos does not change while dragging
        points = [QPointF(p) for p in start[1]]
        if self.tool in (Tool.LINE, Tool.ARROW, Tool.MARKER):
            points[index] = local
        elif self.tool == Tool.FREEHAND:
            # Stretch all points; the opposite corner stays fixed
            box = corners(self.box(points))
            fixed, handle = box[(index + 2) % 4], box[index]
            sx = scale_factor(local.x(), fixed.x(), handle.x())
            sy = scale_factor(local.y(), fixed.y(), handle.y())
            points = [QPointF(fixed.x() + (p.x() - fixed.x()) * sx,
                              fixed.y() + (p.y() - fixed.y()) * sy) for p in points]
        else:  # rectangle, ellipse: opposite corner + new corner
            points = [corners(self.box(points))[(index + 2) % 4], local]
        self.points = points
        self.rebuild()

    # --- Build from the values ---
    def update_pen(self):
        pen = QPen(shown_color(self, self.color), self.width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)

    def rebuild(self):
        """Recompute the path completely from tool and points."""
        if self.tool == Tool.FREEHAND:
            first = self.points[0]
            path = QPainterPath(first)
            # Tiny start stroke, so that even a single click draws a dot
            path.lineTo(first.x() + 0.01, first.y())
            for point in self.points[1:]:
                path.lineTo(point)
        else:
            path = shape_path(self.tool, self.points[0], self.points[1], self.width, self.radius)
        self.setPath(path)
        self.layout_label()  # resized: wrap the label anew and center it


class TextElement(PoseMixin, QGraphicsTextItem):
    """Text object with a fixed ID, color and font size (bold, in pixels).

    Also used as the label of a rectangle/ellipse: then it is a child item of the shape
    (ShapeElement.set_label) and the shape lays it out.
    """

    def __init__(self, origin, color, font_size, text="", element_id=None):
        super().__init__()
        self.setFlag(QGraphicsTextItem.ItemIsSelectable)
        self.id = element_id or new_id()
        self.owner = None  # as a label: the shape it belongs to (ShapeElement.set_label)
        self.set_font_size(font_size)
        self.set_color(color)
        self.setPlainText(text)
        self.setPos(origin)
        # Qt concept signal: the document reports every change of the text (also while typing)
        self.document().contentsChanged.connect(self.relayout)

    def relayout(self):
        """As a label: let the shape center the text again (new text or font size)."""
        if self.owner is not None:
            self.owner.layout_label()

    # color = base color (gets saved), what is shown is the variant adapted to the
    # background (see shown_color); text and shape have the same interface
    @property
    def color(self):
        return QColor(self._color)

    def set_color(self, color):
        self._color = QColor(color)
        self.refresh_color()

    def refresh_color(self):
        """Determine the shown color again (after a background change)."""
        self.setDefaultTextColor(shown_color(self, self._color))

    def itemChange(self, change, value):
        if change == QGraphicsTextItem.ItemSceneHasChanged:  # see ShapeElement.itemChange
            self.refresh_color()
        return super().itemChange(change, value)

    def set_font_size(self, size):
        self.font_size = size
        font = QFont()
        font.setPixelSize(size)
        font.setBold(True)
        self.setFont(font)
        if getattr(self, "owner", None) is not None:  # as a label: center it again
            self.relayout()

    def paint(self, painter, option, widget=None):
        super().paint(painter, without_selection_highlight(option), widget)

    # --- Handles: dragging a corner scales the font ---
    def handle_points(self):
        return corners(self.boundingRect())

    def geometry(self):
        return (QPointF(self.pos()), self.font_size)

    def set_geometry(self, state):
        pos, size = state
        self.set_font_size(size)
        self.setPos(pos)

    def drag_handle(self, index, scene_pos, start, size_range=(6, 300)):
        """Font size in proportion to the diagonal; the opposite corner stays put
        (also when the text is rotated: corners are mapped with mapToScene)."""
        _, start_size = start
        self.set_geometry(start)  # compute from the initial state, not step by step
        box = corners(self.boundingRect())
        fixed_scene = self.mapToScene(box[(index + 2) % 4])
        ratio = (distance(scene_pos, fixed_scene)
                 / max(1.0, distance(self.mapToScene(box[index]), fixed_scene)))
        low, high = size_range
        self.set_font_size(max(low, min(high, round(start_size * ratio))))
        # New size: shift the position so that the fixed corner stays in its place
        moved = self.mapToScene(corners(self.boundingRect())[(index + 2) % 4])
        self.setPos(self.pos() + fixed_scene - moved)

    # --- Save / load (document.py) ---
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

    # --- Editing ---
    def start_editing(self):
        # TextEditorInteraction turns the item into a small editor (cursor, typing, selection)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus()  # keyboard input now goes to this item via the scene

    def stop_editing(self):
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.clearFocus()


class ImageElement(PoseMixin, QGraphicsItem):
    """Image (e.g. a pasted screenshot crop on the whiteboard).

    image: the image in full resolution; size: displayed size in scene units.
    Handles at the corners resize it with a fixed aspect ratio. There is no color
    or stroke width: set_color does nothing, size keys skip it.
    """

    def __init__(self, origin, image, size=None, element_id=None):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.id = element_id or new_id()
        self.image = QImage(image)
        self.size = QSizeF(size) if size is not None else QSizeF(self.image.size())
        self.color = QColor("#000000")  # only so that color comparisons work for a selection
        self.setPos(origin)

    # --- Qt: area and painting ---
    def boundingRect(self):
        return QRectF(QPointF(0, 0), self.size)

    def shape(self):  # hit on the whole area
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.boundingRect(), self.image)

    def set_color(self, color):
        """Images have no pen color; color changes on a selection skip them."""

    def refresh_color(self):
        """Nothing to adapt (no pen)."""

    # --- Handles: size with a fixed aspect ratio ---
    def handle_points(self):
        return corners(self.boundingRect())

    def geometry(self):
        return (QPointF(self.pos()), QSizeF(self.size))

    def set_geometry(self, state):
        pos, size = state
        self.prepareGeometryChange()  # Qt concept: announce every change of boundingRect beforehand
        self.size = QSizeF(size)
        self.setPos(pos)

    def drag_handle(self, index, scene_pos, start):
        """Corner index to scene_pos; the opposite corner stays, aspect ratio fixed.
        Computed in local coordinates, so it also works when the image is rotated."""
        _, start_size = start
        self.set_geometry(start)  # compute from the initial state, not step by step
        fixed = corners(QRectF(QPointF(0, 0), start_size))[(index + 2) % 4]
        local = self.mapFromScene(scene_pos)
        ratio = start_size.width() / max(1e-6, start_size.height())
        width = max(8.0, abs(local.x() - fixed.x()), abs(local.y() - fixed.y()) * ratio)
        size = QSizeF(width, width / ratio)
        left = fixed.x() - size.width() if local.x() < fixed.x() else fixed.x()
        top = fixed.y() - size.height() if local.y() < fixed.y() else fixed.y()
        # The new top left corner in old local coordinates becomes the new pos (same rotation)
        self.set_geometry((self.mapToScene(QPointF(left, top)), size))

    # --- Save / load ---
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
            raise ValueError("image unreadable")
        width, height = (float(v) for v in data["size"])
        if width <= 0 or height <= 0:
            raise ValueError("image size must be positive")
        item = cls(QPointF(*data["pos"]), image, QSizeF(width, height), element_id=data.get("id"))
        item.setRotation(data.get("rotation", 0))
        return item
