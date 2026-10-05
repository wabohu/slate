"""Input part of the Canvas: mouse (draw, select, move, drag handles),
text input, selection frame with handles, mouse wheel (fine size, on the whiteboard pan/
zoom via BoardMixin), moving the selection with hjkl, rotating (Q) and deleting.

Mixin like BoardMixin (canvas_board.py): no __init__ of its own, Canvas inherits from it.
super().mousePressEvent(event) etc. ends up in QGraphicsView (Qt's default behavior,
e.g. setting the cursor in the text editor).

Manages (created in Canvas.__init__): current_item, start_pos, editing_text,
editing_old, dragging, drag_offset, drag_start, passthrough, wheel_rest, resizing, rotating, panning.
Reads from the Canvas: tool, board, board_color, pen_color, pen_width, text_size, scene_,
settings, toast, undo_stack, selected_element(), element_at(), zoom(), update_bars(),
pan_by(), pan_by_wheel(), zoom_by_wheel().
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPathStroker, QPen, QPolygonF, QTransform

import connectors
from colors import contrast
from commands import (AddItemCommand, EditTextCommand, MoveItemCommand, PropertyCommand, RemoveItemCommand,
                      ReorderCommand, SetLabelCommand, property_command)
from elements import LABEL_TOOLS, ShapeElement, TextElement, is_label
from settings import (HANDLE_GRAB, HANDLE_SIZE, ROTATE_HANDLE_OFFSET, STROKE_WIDTH_RANGE,
                      TEXT_SIZE_RANGE, WHEEL_STROKE_STEP, WHEEL_TEXT_STEP, clamp)
from tools import Tool

# Width of the highlight band around a docking target (screen pixels)
DOCK_HINT_WIDTH = 10

# handle_at() returns this instead of a corner number when the mouse is on the rotate handle
ROTATE_HANDLE = "rotate"
# Not rotatable: lines/arrows turn via their end points, blur and markers do not rotate at all
NOT_ROTATABLE = (Tool.LINE, Tool.ARROW, Tool.MARKER, Tool.BLUR)


def angle_to(center, pos):
    """Direction from center to pos in degrees (Qt: y points down, so clockwise is positive)."""
    return math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))


def turned(center, start, delta):
    """Pose of an element after turning rigidly by delta degrees around center (start = pose before)."""
    start_pos, start_angle = start
    return (center + QTransform().rotate(delta).map(start_pos - center), (start_angle + delta) % 360)


class InputMixin:
    # --- Mouse: draw, select, move, drag handles ---
    def mousePressEvent(self, event):
        if not self.board and not self.isActiveWindow():
            self.take_focus()  # a hotkey moved the focus elsewhere: take it back on click
        if self.help_panel.isVisible():  # a click next to the shortcut overview only closes it
            self.help_panel.hide()
            return
        if self.pointer_mode and event.button() == Qt.LeftButton:
            return  # spotlight/magnifier: clicks draw nothing (middle button still pans)
        if self.cropping and event.button() == Qt.LeftButton:
            self.crop_press(self.mapToScene(event.position().toPoint()))  # draw the crop
            return
        if event.button() == Qt.MiddleButton and self.board:
            self.panning = event.position()  # panning the view starts
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if event.button() != Qt.LeftButton:
            return
        pos = self.mapToScene(event.position().toPoint())

        if self.editing_text:
            if self.editing_text.contains(self.editing_text.mapFromScene(pos)):
                # Click into the text being edited: Qt sets the cursor or selects
                self.passthrough = True
                super().mousePressEvent(event)
                return
            # A click next to it only ends the input
            self.finish_text()
            if self.tool in (Tool.TEXT, Tool.SELECT):
                return

        if self.tool == Tool.SELECT:
            handle = self.handle_at(pos)
            if handle == ROTATE_HANDLE:  # rotate handle: turn around the middle of the element
                item = self.selected_element()
                center = item.mapToScene(item.boundingRect().center())
                self.rotating = (item, center, angle_to(center, pos), item.pose())
                self.viewport().setCursor(Qt.ClosedHandCursor)
                return
            if handle is not None:  # grabbing a handle = resize
                item = self.selected_element()
                self.resizing = (item, handle, item.geometry())
                return
            item = self.element_at(pos)
            shift = bool(event.modifiers() & Qt.ShiftModifier)
            if item and shift:  # Shift+click: add element to the selection or remove it
                item.setSelected(not item.isSelected())
            elif item:  # click = select and grab; part of a selection: dragging moves all
                if not item.isSelected():
                    self.scene_.clearSelection()
                    item.setSelected(True)
                self.start_drag(self.selected_elements(), pos)
                self.click_only = item  # release without dragging: select only this element
            else:  # empty spot: draw a selection rectangle (Shift: add to the selection)
                before = self.selected_elements() if shift else []
                if not shift:
                    self.scene_.clearSelection()
                self.rubber = (pos, pos, before)
            self.update_bars()
            return

        if self.tool == Tool.TEXT:
            item = self.text_at(pos)
            if item:  # grab existing text to move it
                self.start_drag([item], pos)
            else:
                self.start_text(pos)
            return

        if self.current_item is not None:  # previous shape without release (e.g. double click)
            self.finish_shape(pos)
        self.start_pos = pos
        self.current_item = ShapeElement(self.tool, pos, self.pen_color, self.pen_width,
                                         radius=self.settings.rect_radius)
        if self.tool == Tool.MARKER:
            self.current_item.marker_kind = self.marker_kind
            self.current_item.marker_order = self.next_marker_order()
        self.scene_.addItem(self.current_item)
        if connectors.is_connector(self.current_item):  # line/arrow starting at a shape: dock its start
            target = self.dock_target(pos, self.current_item)
            self.current_item.ends[0] = target.id if target is not None else None

    def mouseDoubleClickEvent(self, event):
        # On the second click Qt sends a DoubleClick event instead of mousePressEvent
        pos = self.mapToScene(event.position().toPoint())
        if self.editing_text:
            if self.editing_text.contains(self.editing_text.mapFromScene(pos)):
                self.passthrough = True
                super().mouseDoubleClickEvent(event)  # in the editor: select a word
            else:
                self.mousePressEvent(event)  # next to it: end input like a click
            return
        item = self.text_at(pos) if self.tool in (Tool.TEXT, Tool.SELECT) else None
        left = event.button() == Qt.LeftButton
        hit = self.element_at(pos) if left and self.tool == Tool.SELECT and not item else None
        # Rectangle/ellipse: hit on the outline or the label, or a double click into its empty inside
        shape = hit if isinstance(hit, ShapeElement) and hit.tool in LABEL_TOOLS else None
        if shape is None and hit is None and left and self.tool == Tool.SELECT and not item:
            shape = self.shape_at(pos)
        if item and left:
            self.dragging = None
            self.edit_text(item, old=(item.toPlainText(), item.color, item.font_size))
        elif shape is not None:  # select tool, double click into a shape: label it / edit the label
            self.dragging = None
            self.start_label(shape)
        elif left and self.tool == Tool.SELECT and hit is None:
            # Select tool, double click on an empty spot: new text (like Excalidraw).
            # Only here, in drawing tools the first click would already have drawn something
            self.dragging = None
            self.start_text(pos)
        else:
            self.mousePressEvent(event)  # otherwise treat it like a normal click

    def mouseMoveEvent(self, event):
        if self.panning is not None:
            delta = event.position() - self.panning
            self.panning = event.position()
            self.pan_by(delta.x(), delta.y())
            return
        if self.pointer_mode:
            self.viewport().update()  # spotlight/magnifier follow the mouse
            return
        if self.crop_drag is not None:
            self.crop_move(self.mapToScene(event.position().toPoint()))
            return
        if self.cropping:  # adjust the cursor over handles or inside the crop
            self.crop_hover(self.mapToScene(event.position().toPoint()))
            return
        if self.passthrough:
            super().mouseMoveEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        if self.rotating:
            item, center, start_mouse, start = self.rotating
            # Follows the mouse freely, no snapping (Shift is kept free for later, e.g. aligning)
            item.set_pose(turned(center, start, angle_to(center, pos) - start_mouse))
            self.update_connectors()  # docked lines/arrows follow live
            self.viewport().update()
            return
        if self.resizing:
            item, handle, start = self.resizing
            if isinstance(item, TextElement):
                item.drag_handle(handle, pos, start, TEXT_SIZE_RANGE)
            else:
                item.drag_handle(handle, pos, start)
            if connectors.is_connector(item):  # end handle of a line/arrow: dock or undock it
                self.dock_end(item, handle, pos)
            else:
                self.update_connectors()  # docked lines/arrows follow live
            self.viewport().update()
            return
        if self.dragging:
            delta = pos - self.drag_origin
            for item, start in zip(self.dragging, self.drag_starts):
                item.setPos(start + delta)
            self.update_connectors()  # docked lines/arrows follow live
            self.viewport().update()  # handles move along
            return
        if self.rubber is not None:
            start, _, before = self.rubber
            self.rubber = (start, pos, before)
            self.select_in_rubber()
            return
        if self.current_item is None:
            self.update_cursor(pos)  # only movement without a button
            return
        # Tool of the element, not self.tool: a key press in the middle of dragging changes nothing
        if self.current_item.tool == Tool.FREEHAND:
            self.current_item.add_point(pos)
        else:
            self.current_item.set_end(pos)
            if connectors.is_connector(self.current_item):
                self.dock_end(self.current_item, 1, pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self.panning is not None:
            self.panning = None
            self.refresh_cursor()
            return
        if event.button() != Qt.LeftButton:
            return
        if self.crop_drag is not None:
            self.crop_release(self.mapToScene(event.position().toPoint()))
            return
        if self.passthrough:
            self.passthrough = False
            super().mouseReleaseEvent(event)
            return
        if self.rotating:
            item, _, _, start = self.rotating
            self.rotating = None
            if item.pose() != start:  # only a real change is an undo step
                self.undo_stack.push(PropertyCommand(item.set_pose, start, item.pose(), "Rotate"))
            self.update_cursor(self.mapToScene(event.position().toPoint()))
            return
        if self.resizing:
            item, _, start = self.resizing
            self.resizing = None
            if self.dock_hint is not None:
                self.dock_hint = None
                self.viewport().update()
            if item.geometry() != start:  # only a real change is an undo step
                self.undo_stack.push(PropertyCommand(item.set_geometry, start, item.geometry(), "Resize"))
            return
        if self.dragging:
            items, starts, only, undock = self.dragging, self.drag_starts, self.click_only, self.drag_undock
            self.dragging = self.drag_starts = self.drag_origin = self.click_only = None
            self.drag_undock = []
            moved = any(item.pos() != start for item, start in zip(items, starts))
            if moved and undock:  # moving lines/arrows away from their shapes: one undo step
                self.undo_stack.beginMacro("Move")
                self.undo_stack.push(property_command(undock, "Undock"))
                self.undo_stack.push(MoveItemCommand(items, starts, [i.pos() for i in items]))
                self.undo_stack.endMacro()
            elif moved:
                self.undo_stack.push(MoveItemCommand(items, starts, [i.pos() for i in items]))
            else:
                for setter, old, _ in undock:  # only a click: stay docked
                    setter(old)
                if only is not None and len(items) > 1:  # a plain click into a multi-selection
                    self.scene_.clearSelection()
                    only.setSelected(True)
                    self.update_bars()
            return
        if self.rubber is not None:
            self.rubber = None
            self.update_bars()
            return
        if self.current_item is None:
            return
        self.finish_shape(self.mapToScene(event.position().toPoint()))

    def start_drag(self, items, pos):
        """Grab elements for moving (one undo step on release). Lines/arrows among them let go
        of shapes that are not moved along (otherwise they would snap back to them)."""
        self.dragging = list(items)
        self.drag_origin = QPointF(pos)
        self.drag_starts = [QPointF(i.pos()) for i in items]
        self.drag_undock = self.undock_changes(items)
        for setter, _, new in self.drag_undock:
            setter(new)

    def undock_changes(self, items):
        """Moving/rotating items: lines/arrows among them undock the ends whose element is not
        part of items. Returns [(set_ends, old, new)] for an undo step (empty: nothing to undock)."""
        moved = {i.id for i in items}
        changes = []
        for item in items:
            if connectors.is_connector(item):
                new = [e if e in moved else None for e in item.ends]
                if new != item.ends:
                    changes.append((item.set_ends, list(item.ends), new))
        return changes

    def select_in_rubber(self):
        """Selection = whatever lies completely inside the rectangle (plus the previous selection with Shift)."""
        start, end, before = self.rubber
        rect = QRectF(start, end).normalized()
        for item in self.elements():
            item.setSelected(item in before or rect.contains(item.sceneBoundingRect()))
        self.update_bars()

    def finish_shape(self, pos):
        """Finish the drawn shape: push it as an undo step or, if too small, discard it."""
        # Accidental click without dragging: throw the empty shape away again
        too_small = (pos - self.start_pos).manhattanLength() < 3
        if self.current_item.tool == Tool.MARKER and too_small:
            self.current_item.set_end(self.start_pos)  # click: only the circle, without a pointer line
        if self.current_item.tool not in (Tool.FREEHAND, Tool.MARKER) and too_small:
            self.scene_.removeItem(self.current_item)
        else:
            self.undo_stack.push(AddItemCommand(self.scene_, self.current_item))
        self.current_item = None
        self.start_pos = None
        if self.dock_hint is not None:
            self.dock_hint = None
            self.viewport().update()

    # --- Connectors: dock line/arrow ends onto elements (connectors.py) ---
    def dock_target(self, pos, exclude):
        """Docking target near pos (close to its outline, DOCK_MARGIN screen pixels) or None."""
        return connectors.target_at(self.scene_, pos, connectors.DOCK_MARGIN / self.zoom(), exclude)

    def dock_end(self, line, index, pos):
        """End index of line was drawn/dragged to pos: dock it onto the target there (not the
        one the other end is docked to), otherwise free; show the target, lay the line out."""
        target = self.dock_target(pos, line)
        if target is not None and target.id == line.ends[1 - index]:
            target = None  # both ends on the same shape: the second one stays free
        line.ends[index] = target.id if target is not None else None
        if target is not self.dock_hint:
            # Qt only repaints the area that changed (here: the line); the frame drawn in
            # drawForeground around the target lies elsewhere, so repaint everything
            self.dock_hint = target
            self.viewport().update()
        connectors.layout(line, {e.id: e for e in self.elements()})

    def paint_dock_hint(self, painter):
        """Glowing band along the outline of the docking target under the line/arrow end being
        drawn (never in the export): a translucent band in the accent color, DOCK_HINT_WIDTH
        screen pixels wide, so it stays visible on top of the shape's own outline."""
        if self.dock_hint is None or self.dock_hint.scene() is None:
            return
        stroker = QPainterPathStroker()
        stroker.setWidth(DOCK_HINT_WIDTH / self.zoom())
        band = stroker.createStroke(connectors.outline(self.dock_hint))
        glow = QColor(self.settings.theme.accent)
        glow.setAlpha(150)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawPath(band)

    # --- Text ---
    def start_text(self, pos):
        """Create a new text object at pos and focus it right away for typing."""
        item = TextElement(pos, self.pen_color, self.text_size)
        # Click point roughly at the height of the middle of the line
        item.setPos(pos - QPointF(0, item.boundingRect().height() / 2))
        self.scene_.addItem(item)
        self.edit_text(item, old=None)

    def start_label(self, shape):
        """Open the label of shape for typing; without one, create an empty one first
        (it becomes an undo step only when the input ends with text, see finish_text)."""
        label = shape.label
        if label is None:
            label = TextElement(QPointF(0, 0), shape.color, self.text_size)
            shape.set_label(label)
            self.edit_text(label, old=None)
        else:
            self.edit_text(label, old=(label.toPlainText(), label.color, label.font_size))

    def shape_at(self, pos):
        """Topmost rectangle/ellipse whose area (not only the outline, D2) contains pos, or None.
        Qt concept: items(…, IntersectsItemBoundingRect) finds candidates by their bounding
        rectangle; path().contains() then checks the actual area of the shape."""
        for item in self.scene_.items(pos, Qt.IntersectsItemBoundingRect):  # top to bottom
            if (isinstance(item, ShapeElement) and item.tool in LABEL_TOOLS
                    and item.path().contains(item.mapFromScene(pos))):
                return item
        return None

    def edit_text(self, item, old):
        """Open item for typing. old = (text, color, size) before, None for new text."""
        self.scene_.clearSelection()  # do not show a selection frame while typing
        item.start_editing()
        self.editing_text = item
        self.editing_old = old

    def finish_text(self):
        """End the input and push it as an undo step; empty text disappears."""
        item, old = self.editing_text, self.editing_old
        self.editing_text = self.editing_old = None
        item.stop_editing()
        new = (item.toPlainText(), item.color, item.font_size)
        empty = not new[0].strip()

        if is_label(item):  # label of a rectangle/ellipse: attached to it, not an element of its own
            shape = item.owner
            if old is None:  # new label: empty = discard it again
                if empty:
                    shape.set_label(None)
                else:
                    self.undo_stack.push(SetLabelCommand(shape, None, item, "Add label"))
            elif empty:  # emptied: remove the label (undo brings it back with its text)
                self.undo_stack.beginMacro("Delete label")
                self.undo_stack.push(EditTextCommand(item, old, new))
                self.undo_stack.push(SetLabelCommand(shape, item, None))
                self.undo_stack.endMacro()
            elif new != old:
                self.undo_stack.push(EditTextCommand(item, old, new, "Edit label"))
            return

        if old is None:  # new text
            if empty:
                self.scene_.removeItem(item)
            else:
                self.undo_stack.push(AddItemCommand(self.scene_, item, "Add text"))
        elif empty:
            # Macro: several commands that are undone together with one undo
            self.undo_stack.beginMacro("Delete text")
            self.undo_stack.push(EditTextCommand(item, old, new))
            self.undo_stack.push(RemoveItemCommand(self.scene_, item))
            self.undo_stack.endMacro()
        elif new != old:
            self.undo_stack.push(EditTextCommand(item, old, new))

    def text_at(self, pos):
        """Topmost loose text object at scene position pos or None. Labels of shapes do not
        count: they are reached via the shape (double click), and the text tool must not
        drag them out of their shape."""
        for item in self.scene_.items(pos):  # sorted top to bottom
            if isinstance(item, TextElement) and not is_label(item):
                return item
        return None

    # --- Handles and selection frame ---
    def handle_at(self, pos):
        """Number of the selection's handle at scene position pos or None."""
        item = self.selected_element()
        if item is None or self.tool != Tool.SELECT or self.editing_text:
            return None
        grab = HANDLE_GRAB / self.zoom()  # grab radius in scene units
        for i, local in enumerate(item.handle_points()):
            point = item.mapToScene(local)
            if abs(point.x() - pos.x()) <= grab and abs(point.y() - pos.y()) <= grab:
                return i
        rotate = self.rotate_handle(item)
        if rotate is not None and abs(rotate[0].x() - pos.x()) <= grab and abs(rotate[0].y() - pos.y()) <= grab:
            return ROTATE_HANDLE
        return None

    def rotate_handle(self, item):
        """(rotate handle, point on the frame it hangs on) in scene coordinates, or None if
        item cannot be rotated with the mouse. The handle sits above the middle of the top edge
        and turns with the element; its distance stays the same on screen at any zoom."""
        if isinstance(item, ShapeElement) and item.tool in NOT_ROTATABLE:
            return None
        corner = [item.mapToScene(p) for p in item.handle_points()]
        top, center = (corner[0] + corner[1]) / 2, (corner[0] + corner[2]) / 2
        up = top - center
        length = math.hypot(up.x(), up.y())
        if length < 1e-6:  # flat element (e.g. a horizontal stroke): straight up, turned along
            up, length = item.mapToScene(QPointF(0, -1)) - item.mapToScene(QPointF(0, 0)), 1.0
        return top + up * (ROTATE_HANDLE_OFFSET / self.zoom() / length), top

    def update_cursor(self, pos):
        """Mouse cursor in the select tool: own arrow, a resize arrow over handles."""
        if self.tool != Tool.SELECT:
            return
        handle = self.handle_at(pos)
        item = self.selected_element()
        if handle is None:
            cursor = self.tool_cursor()
        elif handle == ROTATE_HANDLE:
            cursor = Qt.OpenHandCursor
        elif isinstance(item, ShapeElement) and item.tool in (Tool.LINE, Tool.ARROW, Tool.MARKER):
            cursor = Qt.SizeAllCursor
        else:  # resize arrow along the diagonal through this corner (also when rotated)
            center = item.mapToScene(item.boundingRect().center())
            direction = angle_to(center, item.mapToScene(item.handle_points()[handle])) % 180
            cursors = (Qt.SizeHorCursor, Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor)
            cursor = cursors[int((direction + 22.5) // 45) % 4]  # 45° sectors: ↔ ↘ ↕ ↙
        self.viewport().setCursor(cursor)

    def drawForeground(self, painter, rect):
        """Draw the frame and handles of the selection on top of everything.

        Qt concept: drawForeground belongs to the view, not the scene. Whatever is
        drawn here therefore never ends up in the exported image (scene.render).
        """
        self.paint_dock_hint(painter)
        self.paint_selection(painter)
        self.paint_crop(painter)     # crop: darken outside (canvas_crop.py)
        self.paint_pointer(painter)  # spotlight/magnifier on top of everything (canvas_pointer.py)

    def paint_selection(self, painter):
        """Frame and handles of the selection (only in the select tool). One element: frame with
        handles; several: a dashed frame each without handles; plus the selection rectangle."""
        if self.tool != Tool.SELECT or self.editing_text:
            return
        line, fill = self.selection_colors()
        if self.rubber is not None:  # selection rectangle while dragging
            start, end, _ = self.rubber
            band = QPen(line, 1, Qt.DashLine)
            band.setCosmetic(True)
            painter.setPen(band)
            tint = QColor(line)
            tint.setAlpha(30)
            painter.setBrush(tint)
            painter.drawRect(QRectF(start, end).normalized())
        items = self.selected_elements()
        if len(items) > 1:
            frame = QPen(line, 1, Qt.DashLine)
            frame.setCosmetic(True)
            painter.setPen(frame)
            painter.setBrush(Qt.NoBrush)
            pad = 4 / self.zoom()
            for item in items:
                painter.drawRect(item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad))
            return
        item = self.selected_element()
        if item is None:
            return
        points = [item.mapToScene(p) for p in item.handle_points()]
        painter.setRenderHint(QPainter.Antialiasing)
        if len(points) == 4:  # frame through the corners (for lines only the end points)
            frame = QPen(line, 1, Qt.DashLine)
            frame.setCosmetic(True)  # always 1 pixel, regardless of zoom/transformation
            painter.setPen(frame)
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF(points))
        outline = QPen(line, 1.5)
        outline.setCosmetic(True)
        painter.setPen(outline)
        painter.setBrush(QBrush(fill))
        size = HANDLE_SIZE / self.zoom()  # always the same size on screen
        rotate = self.rotate_handle(item) if len(points) == 4 else None
        if rotate is not None:  # rotate handle: a short stem from the top edge, a round knob
            handle, top = rotate
            painter.drawLine(top, handle)
            painter.drawEllipse(handle, size * 0.6, size * 0.6)
        for p in points:
            painter.drawRect(QRectF(p.x() - size / 2, p.y() - size / 2, size, size))

    def selection_colors(self):
        """(line, fill) for selection frame and handles: the bar color with more
        contrast to the whiteboard background as the line, so it is visible on light and dark."""
        line, fill = QColor(self.settings.theme.foreground), QColor(self.settings.theme.background)
        if self.board and contrast(fill.name(), self.board_color.name()) > \
                contrast(line.name(), self.board_color.name()):
            line, fill = fill, line
        fill.setAlpha(255)
        line.setAlpha(255)
        return line, fill

    # --- Mouse wheel and keys for the selection ---
    def wheelEvent(self, event):
        """Alt+wheel: fine size adjustment. Whiteboard: wheel pans, Ctrl+wheel zooms."""
        mods = event.modifiers()
        if self.board and not mods & Qt.AltModifier:
            event.accept()
            if mods & Qt.ControlModifier:
                self.zoom_by_wheel(event.angleDelta().y() or event.angleDelta().x(), event.position())
            else:
                self.pan_by_wheel(event, swap=bool(mods & Qt.ShiftModifier))
            return
        if not mods & Qt.AltModifier:
            super().wheelEvent(event)
            return
        event.accept()
        # With Alt, Qt on Linux reports the mouse wheel as horizontal, so use both axes
        delta = event.angleDelta()
        self.wheel_rest += delta.y() or delta.x()
        steps = int(self.wheel_rest / 120)  # 120 = one notch
        if steps == 0:
            return
        self.wheel_rest -= steps * 120
        self.adjust_size(steps)

    def adjust_size(self, steps):
        """Change the size by steps notches, independent of the levels."""
        if self.editing_text:  # the undo step is created when the input ends
            item = self.editing_text
            item.set_font_size(clamp(item.font_size + steps * WHEEL_TEXT_STEP, TEXT_SIZE_RANGE))
            return
        items = self.selected_elements()
        if not items:
            self.toast.show_message("Alt+wheel: select something first (W)")
            return
        changes = []  # every element by the same notches, one undo step
        for item in items:
            if isinstance(item, TextElement):
                old = item.font_size
                changes.append((item.set_font_size, old, clamp(old + steps * WHEEL_TEXT_STEP, TEXT_SIZE_RANGE)))
            elif isinstance(item, ShapeElement):
                old = item.width
                changes.append((item.set_width, old, clamp(old + steps * WHEEL_STROKE_STEP, STROKE_WIDTH_RANGE)))
        if changes and any(old != new for _, old, new in changes):
            self.undo_stack.push(property_command(changes, "Change size", mergeable=True))
            self.update_bars()  # when merging, the stack reports no change

    def move_selected(self, dx, dy, fine):
        """Move the selection by one step (screen pixels, independent of zoom)."""
        items = self.selected_elements()
        if not items:
            return
        step = self.settings.move_steps[fine] / self.zoom()
        olds = [QPointF(i.pos()) for i in items]
        news = [p + QPointF(dx * step, dy * step) for p in olds]
        undock = self.undock_changes(items)
        if undock:  # lines/arrows moved away from their shapes let go of them (one undo step)
            self.undo_stack.beginMacro("Move")
            self.undo_stack.push(property_command(undock, "Undock"))
        self.undo_stack.push(MoveItemCommand(items, olds, news, "Move", mergeable=not undock))
        if undock:
            self.undo_stack.endMacro()
        self.update_bars()  # move the handles along; when merging, the stack reports nothing

    def rotate_selected(self, step):
        """Q / Shift+Q: rotate the selection by step degrees (positive = clockwise).

        One element turns around its own middle, several turn together around the
        middle of their centers (the arrangement stays). Blur and markers are left out:
        blur pixelates axis-parallel areas of the screenshot, a marker number would tilt.
        Presses in quick succession = one undo step.

        Qt concept: QTransform().rotate(step) is a pure rotation around (0, 0). Applied to
        "pos minus center" it turns the position around the center; rotation() turns
        the element itself by the same angle, so it moves rigidly.
        """
        items = self.selected_elements()
        if not items:
            self.report("Rotate: select something first (W)")
            return
        items = [i for i in items if not (isinstance(i, ShapeElement) and i.tool in (Tool.BLUR, Tool.MARKER))]
        if not items:
            self.report("Blur and markers cannot be rotated")
            return
        centers = [i.mapToScene(i.boundingRect().center()) for i in items]
        center = QPointF(sum(c.x() for c in centers) / len(centers), sum(c.y() for c in centers) / len(centers))
        changes = self.undock_changes(items)  # rotated lines/arrows let go of shapes not rotated along
        changes += [(item.set_pose, item.pose(), turned(center, item.pose(), step)) for item in items]
        self.undo_stack.push(property_command(changes, "Rotate", mergeable=True))
        self.update_bars()  # move the handles along; when merging, the stack reports nothing

    def restack(self, step):
        """Move the selection in the stacking order: step +1/-1 = one element further
        forward/back, +2/-2 = all the way to the front/back. The selection keeps its order."""
        order = self.elements()  # bottom -> top
        chosen = [e for e in order if e.isSelected()]
        if not chosen:
            return
        new = list(order)
        if abs(step) == 2:
            rest = [e for e in order if not e.isSelected()]
            new = rest + chosen if step > 0 else chosen + rest
        else:
            # One step: every selected element swaps with the next unselected
            # neighbor in direction step (starting from the tip, so groups stay together)
            indices = range(len(new) - 1, -1, -1) if step > 0 else range(len(new))
            for i in indices:
                j = i + step
                if new[i].isSelected() and 0 <= j < len(new) and not new[j].isSelected():
                    new[i], new[j] = new[j], new[i]
        if new != order:
            self.undo_stack.push(ReorderCommand(order, new, "Bring forward" if step > 0 else "Send backward"))

    def delete_selected(self):
        items = self.selected_elements()
        if not items:
            return
        self.undo_stack.beginMacro("Delete")  # several commands = one undo step
        for item in items:
            item.setSelected(False)  # otherwise it would still be selected after an undo
            self.undo_stack.push(RemoveItemCommand(self.scene_, item, "Delete"))
        self.undo_stack.endMacro()
