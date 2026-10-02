"""Tools: enum, names from the config, geometry of the shapes and icons.

Without Canvas dependencies, so elements.py and slate.py can both build on it
without importing each other.
"""
import math
import sys
from enum import Enum

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath


class Tool(Enum):
    FREEHAND = "Freehand"
    LINE = "Line"
    ARROW = "Arrow"
    RECT = "Rectangle"
    ELLIPSE = "Ellipse"
    TEXT = "Text"
    SELECT = "Select"  # not a drawing tool, always first in the bar (key W)
    MARKER = "Marker"  # numbered circle, optionally with a pointer line; fixed place at the end (key C)
    BLUR = "Blur"  # pixelates the screenshot below; fixed place at the end (key Z), screenshot mode only


# Tools with a fixed place in the bar, not part of [tools] order
FIXED_TOOLS = (Tool.SELECT, Tool.MARKER, Tool.BLUR)

# Marker: circle radius from the stroke width (levels 2/4/8/12 px -> radius 15/18/24/30)
MARKER_BASE_RADIUS = 12
MARKER_RADIUS_PER_WIDTH = 1.5


def marker_radius(width):
    return MARKER_BASE_RADIUS + width * MARKER_RADIUS_PER_WIDTH


# Corner radius of the rectangle in pixels (default; per element in ShapeElement.radius,
# for new rectangles from [rect] in the config)
RECT_RADIUS = 8


def parse_tool(name):
    """Config name ('freehand', 'Rect', …) -> Tool; unknown -> None."""
    return Tool.__members__.get(name.strip().upper())


def tool_order(names):
    """Tools in the order of the config, without unknown ones and duplicates.

    Without a usable list: all tools in the order of the enum.
    Select, Marker and Blur are not part of it, they have a fixed place (FIXED_TOOLS).
    """
    result = []
    for name in names or []:
        tool = parse_tool(name)
        if tool is None:
            print(f"[tools] Unknown tool: {name!r}", file=sys.stderr)
        elif tool not in result and tool not in FIXED_TOOLS:
            result.append(tool)
    return result or [t for t in Tool if t not in FIXED_TOOLS]


def shape_path(tool, start, end, pen_width, radius=RECT_RADIUS):
    """Builds the path of a shape from start and end point (everything except freehand)."""
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
        # Qt shrinks the radius itself if the rectangle is too small for it
        path.addRoundedRect(QRectF(start, end).normalized(), radius, radius)
    elif tool == Tool.ELLIPSE:
        path.addEllipse(QRectF(start, end).normalized())
    elif tool == Tool.BLUR:  # area that gets pixelated (drawn in ShapeElement.paint)
        path.addRect(QRectF(start, end).normalized())
    elif tool == Tool.MARKER:  # start = tip (points at the spot), end = circle center
        path.moveTo(start)
        path.lineTo(end)
        path.addEllipse(end, marker_radius(pen_width), marker_radius(pen_width))
    return path


def tool_icon(tool):
    """Icon for the tool bar, in field coordinates 0-30 (bottom right stays free for the key)."""
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
    elif tool == Tool.MARKER:  # circle with "1"
        path.addEllipse(QRectF(5, 5, 19, 19))
        path.moveTo(12.5, 11)
        path.lineTo(15, 9)
        path.lineTo(15, 20)
    elif tool == Tool.BLUR:  # grid like coarse pixels (bottom right stays free for the key)
        for i in range(4):
            path.moveTo(6 + i * 5, 6)
            path.lineTo(6 + i * 5, 21)
            path.moveTo(6, 6 + i * 5)
            path.lineTo(21, 6 + i * 5)
    elif tool == Tool.SELECT:  # mouse pointer
        path.moveTo(9, 5)
        path.lineTo(9, 21)
        path.lineTo(13, 17)
        path.lineTo(16, 23)
        path.lineTo(18.5, 22)
        path.lineTo(15.5, 16)
        path.lineTo(21, 16)
        path.closeSubpath()
    return path
