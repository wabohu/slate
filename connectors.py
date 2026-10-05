"""Connectors (roadmap 15, part 2): lines and arrows whose ends dock onto elements.

A line/arrow stores in ends = [start_id, end_id] which element each end is docked to
(None = free). Its position is derived from that: a docked end aims at the middle of its
element and stops at its outline, with a small gap. If both ends are docked, the line runs
from middle to middle, clipped at both outlines. The Canvas recomputes all connectors after
every change (Canvas.update_connectors), so moving, rotating, resizing or deleting an element
needs no extra work, and undo needs nothing of its own either.

Without Canvas dependencies (like tools.py), so it can be tested on its own.
Plan: docs/plan-verbinder.md.
"""
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath

from elements import ImageElement, ShapeElement, TextElement, is_label
from tools import Tool

# Lines and arrows can be connectors; these shapes can be docking targets
CONNECTOR_TOOLS = (Tool.LINE, Tool.ARROW)
TARGET_TOOLS = (Tool.RECT, Tool.ELLIPSE)
# Gap between the end of a connector and the outline of its target (scene units, plus half the stroke)
GAP = 6
# Steps of the bisection along the line (2^-20 of its length: far below a pixel)
CLIP_STEPS = 20


def is_connector(item):
    return isinstance(item, ShapeElement) and item.tool in CONNECTOR_TOOLS


def is_target(item):
    """Can a connector dock onto item? Rectangle, ellipse, image and loose text."""
    if isinstance(item, ShapeElement):
        return item.tool in TARGET_TOOLS
    if isinstance(item, TextElement):
        return not is_label(item)
    return isinstance(item, ImageElement)


def outline(item):
    """Area of a target in scene coordinates (rotated like the element). Text and image:
    the rectangle around their content."""
    if isinstance(item, ShapeElement):
        local = item.path()
    else:
        local = QPainterPath()
        local.addRect(item.boundingRect())
    return item.mapToScene(local)


def middle(item):
    """Middle of a target in scene coordinates."""
    if isinstance(item, ShapeElement):
        return item.mapToScene(item.box(item.points).center())
    return item.mapToScene(item.boundingRect().center())


def clip(center, toward, area):
    """Point where the line center -> toward leaves area (QPainterPath in the scene).

    Bisection: inside at center, outside at toward; halve the interval until it is tiny.
    Works for every shape, also rotated, without a formula per kind of shape.
    If toward itself lies inside the area, there is no exit: center is returned.
    """
    if area.contains(toward):
        return QPointF(center)
    inside, outside = 0.0, 1.0
    for _ in range(CLIP_STEPS):
        t = (inside + outside) / 2
        if area.contains(center + (toward - center) * t):
            inside = t
        else:
            outside = t
    return center + (toward - center) * outside


def end_point(target, toward, gap):
    """Docked end at target: on its outline toward toward, pulled back by gap."""
    center = middle(target)
    exit_point = clip(center, toward, outline(target))
    direction = toward - center
    length = math.hypot(direction.x(), direction.y())
    if length < 1e-6:
        return exit_point
    return exit_point + direction * (gap / length)


def layout(line, lookup):
    """Recompute the end points of line from its docked targets.

    lookup: element ID -> element (only elements in the scene). An ID that is not in it
    (target deleted) counts as free: that end stays where it is. Returns True if the
    line changed.
    """
    targets = [lookup.get(i) if i is not None else None for i in line.ends]
    targets = [t if t is not None and t is not line and is_target(t) else None for t in targets]
    if not any(targets):
        return False
    current = [line.mapToScene(p) for p in line.points]
    # Where each end aims from: the middle of its target, or the free end itself
    anchors = [middle(t) if t is not None else current[i] for i, t in enumerate(targets)]
    gap = GAP + line.width / 2
    new = [end_point(t, anchors[1 - i], gap) if t is not None else current[i]
           for i, t in enumerate(targets)]
    local = [line.mapFromScene(p) for p in new]
    if all(abs(a.x() - b.x()) < 1e-6 and abs(a.y() - b.y()) < 1e-6 for a, b in zip(local, line.points)):
        return False
    line.points = local
    line.rebuild()
    return True


def update_all(elements):
    """Recompute every connector among elements (all elements of a scene, bottom to top)."""
    lookup = {e.id: e for e in elements}
    for item in elements:
        if is_connector(item) and any(item.ends):
            layout(item, lookup)
