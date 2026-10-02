"""Input part of the Canvas: mouse (draw, select, move, drag handles),
text input, selection frame with handles, mouse wheel (fine size, on the whiteboard pan/
zoom via BoardMixin), moving the selection with hjkl and deleting.

Mixin like BoardMixin (canvas_board.py): no __init__ of its own, Canvas inherits from it.
super().mousePressEvent(event) etc. ends up in QGraphicsView (Qt's default behavior,
e.g. setting the cursor in the text editor).

Manages (created in Canvas.__init__): current_item, start_pos, editing_text,
editing_old, dragging, drag_offset, drag_start, passthrough, wheel_rest, resizing, panning.
Reads from the Canvas: tool, board, board_color, pen_color, pen_width, text_size, scene_,
settings, toast, undo_stack, selected_element(), element_at(), zoom(), update_bars(),
pan_by(), pan_by_wheel(), zoom_by_wheel().
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from colors import contrast
from commands import (AddItemCommand, EditTextCommand, MoveItemCommand, PropertyCommand, RemoveItemCommand,
                      ReorderCommand, property_command)
from elements import ShapeElement, TextElement
from settings import (HANDLE_GRAB, HANDLE_SIZE, STROKE_WIDTH_RANGE, TEXT_SIZE_RANGE, WHEEL_STROKE_STEP,
                      WHEEL_TEXT_STEP, clamp)
from tools import Tool


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
        if item and left:
            self.dragging = None
            self.edit_text(item, old=(item.toPlainText(), item.color, item.font_size))
        elif left and self.tool == Tool.SELECT and self.element_at(pos) is None:
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
        if self.resizing:
            item, handle, start = self.resizing
            if isinstance(item, TextElement):
                item.drag_handle(handle, pos, start, TEXT_SIZE_RANGE)
            else:
                item.drag_handle(handle, pos, start)
            self.viewport().update()
            return
        if self.dragging:
            delta = pos - self.drag_origin
            for item, start in zip(self.dragging, self.drag_starts):
                item.setPos(start + delta)
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
        if self.resizing:
            item, _, start = self.resizing
            self.resizing = None
            if item.geometry() != start:  # only a real change is an undo step
                self.undo_stack.push(PropertyCommand(item.set_geometry, start, item.geometry(), "Resize"))
            return
        if self.dragging:
            items, starts, only = self.dragging, self.drag_starts, self.click_only
            self.dragging = self.drag_starts = self.drag_origin = self.click_only = None
            if any(item.pos() != start for item, start in zip(items, starts)):  # only real moving
                self.undo_stack.push(MoveItemCommand(items, starts, [i.pos() for i in items]))
            elif only is not None and len(items) > 1:  # a plain click into a multi-selection
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
        """Grab elements for moving (one undo step on release)."""
        self.dragging = list(items)
        self.drag_origin = QPointF(pos)
        self.drag_starts = [QPointF(i.pos()) for i in items]

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

    # --- Text ---
    def start_text(self, pos):
        """Create a new text object at pos and focus it right away for typing."""
        item = TextElement(pos, self.pen_color, self.text_size)
        # Click point roughly at the height of the middle of the line
        item.setPos(pos - QPointF(0, item.boundingRect().height() / 2))
        self.scene_.addItem(item)
        self.edit_text(item, old=None)

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
        """Topmost text object at scene position pos or None."""
        for item in self.scene_.items(pos):  # sorted top to bottom
            if isinstance(item, TextElement):
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
        return None

    def update_cursor(self, pos):
        """Mouse cursor in the select tool: own arrow, a resize arrow over handles."""
        if self.tool != Tool.SELECT:
            return
        handle = self.handle_at(pos)
        item = self.selected_element()
        if handle is None:
            cursor = self.tool_cursor()
        elif isinstance(item, ShapeElement) and item.tool in (Tool.LINE, Tool.ARROW):
            cursor = Qt.SizeAllCursor
        else:  # corners 0/2 diagonal ↖↘, 1/3 diagonal ↗↙
            cursor = Qt.SizeFDiagCursor if handle in (0, 2) else Qt.SizeBDiagCursor
        self.viewport().setCursor(cursor)

    def drawForeground(self, painter, rect):
        """Draw the frame and handles of the selection on top of everything.

        Qt concept: drawForeground belongs to the view, not the scene. Whatever is
        drawn here therefore never ends up in the exported image (scene.render).
        """
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
        self.undo_stack.push(MoveItemCommand(items, olds, news, "Move", mergeable=True))
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
