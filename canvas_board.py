"""Whiteboard part of the Canvas: pan and zoom the view, background, window title,
prompt on close. Only active on the whiteboard (board=True).

Qt/Python concept mixin: BoardMixin has no __init__ of its own and cannot run on
its own. Canvas inherits from it (class Canvas(BoardMixin, QGraphicsView)), so the
methods end up in the Canvas as if they were written there. See docs/plan-aufteilung.md.

Manages (created in Canvas.__init__): board_color, zoom_rest, overview_return.
Reads from the Canvas: board, scene_, settings, palette_bar, toast, undo_stack,
document_path, elements(), used_rect(), zoom(), ask(), save_drawing().
"""
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox

from colors import adapt_color
from commands import PropertyCommand
from notify import NOT_AVAILABLE
from settings import WHEEL_PAN_STEP, ZOOM_RANGE, ZOOM_STEP, clamp


class BoardMixin:
    # --- View: pan and zoom ---
    def pan_by(self, dx, dy):
        """Pan the view by dx/dy screen pixels (the content follows the mouse).

        The scroll bars are hidden but still work: their value is the
        position of the view in the large scene.
        """
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(dx))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(dy))

    def pan_by_wheel(self, event, swap):
        """Mouse wheel: vertical; tilt wheel/touchpad: horizontal; Shift: swap axes."""
        pixels = event.pixelDelta()  # touchpads deliver exact pixels
        if not pixels.isNull():
            dx, dy = pixels.x(), pixels.y()
        else:
            angle = event.angleDelta()
            dx, dy = angle.x() / 120 * WHEEL_PAN_STEP, angle.y() / 120 * WHEEL_PAN_STEP
        if swap:
            dx, dy = dy, dx
        self.pan_by(dx, dy)

    def zoom_by_wheel(self, delta, mouse):
        """Zoom while the point under the mouse cursor (mouse, viewport coordinates) stays put.

        Qt's AnchorUnderMouse does not work here: it remembers the mouse position in
        QGraphicsView.mouseMoveEvent, which we override. So anchor by hand.
        """
        self.zoom_rest += delta
        steps = int(self.zoom_rest / 120)
        if steps == 0:
            return
        self.zoom_rest -= steps * 120
        factor = clamp(self.zoom() * ZOOM_STEP ** steps, ZOOM_RANGE) / self.zoom()
        anchor = self.mapToScene(mouse.toPoint())  # scene point under the mouse
        self.scale(factor, factor)
        drift = self.mapFromScene(anchor) - mouse.toPoint()  # where scaling moved it to
        self.pan_by(-drift.x(), -drift.y())
        self.refresh_cursor()  # circle in the mouse cursor = stroke width at this zoom
        self.toast.show_message(f"Zoom {round(self.zoom() * 100)} %")

    def view_state(self):
        """Current view: transformation (zoom) and scene point in the center of the window."""
        return self.transform(), self.mapToScene(self.viewport().rect().center())

    def set_view_state(self, state):
        transform, center = state
        self.setTransform(transform)
        self.centerOn(center)

    def overview(self):
        """Whiteboard: fit all elements into the window (at most 100 %).

        Pressing Ctrl+W again jumps back to the view before, as long as the overview
        is unchanged (not zoomed or panned); otherwise overview again.
        """
        if not self.board:
            return
        if self.overview_return:
            before, during = self.overview_return
            self.overview_return = None
            transform, center = self.view_state()
            if transform == during[0] and (center - during[1]).manhattanLength() < 1:
                self.set_view_state(before)
                self.refresh_cursor()
                self.toast.show_message(f"Back ({round(self.zoom() * 100)} %)")
                return
        before = self.view_state()
        if not self.elements():
            self.resetTransform()
            self.centerOn(0, 0)
        else:
            rect = self.used_rect()
            view = self.viewport().rect()
            factor = clamp(min(view.width() / rect.width(), view.height() / rect.height()),
                           (ZOOM_RANGE[0], 1.0))
            self.resetTransform()
            self.scale(factor, factor)
            self.centerOn(rect.center())
        self.overview_return = (before, self.view_state())
        self.refresh_cursor()
        self.toast.show_message(f"Overview ({round(self.zoom() * 100)} %)")

    def zoom_reset(self):
        if self.board:
            self.resetTransform()  # back to 100 %, without rotation/distortion
            self.refresh_cursor()
            self.toast.show_message("Zoom 100 %")

    # --- Background ---
    def set_board_color(self, color):
        """Setter for PropertyCommand: background of the whiteboard (saved with it)."""
        self.board_color = QColor(color)
        self.scene_.setBackgroundBrush(self.board_color)
        self.refresh_colors()
        self.refresh_cursor()  # adapt the pen color in the mouse cursor to the background

    def adapt_color(self, color):
        """Shown color for the base color color: darkened on a light whiteboard
        (colors.adapt_color), otherwise unchanged. The base color is always what gets saved."""
        if not self.board:
            return QColor(color)
        return QColor(adapt_color(QColor(color).name(), self.board_color.name(), self.settings.light_overrides))

    def refresh_colors(self):
        """After a background change: elements and color bar show the matching variants."""
        for item in self.elements():
            item.refresh_color()
        self.palette_bar.set_colors([self.adapt_color(c) for c in self.settings.swatches])
        self.viewport().update()

    def cycle_board_color(self, step):
        """Ctrl+B / Ctrl+Shift+B: next or previous background from the list.
        If the current one is not in the list (e.g. from a file), start at the first
        or last one. Whiteboard only."""
        if not self.board:
            return
        colors = self.settings.board_backgrounds
        current = next((i for i, c in enumerate(colors) if c == self.board_color), None)
        if current is None:
            new = colors[0] if step > 0 else colors[-1]
        else:
            new = colors[(current + step) % len(colors)]
        if new == self.board_color:
            return  # only one entry: nothing to do, no empty undo step
        self.undo_stack.push(PropertyCommand(
            self.set_board_color, QColor(self.board_color), QColor(new), "Change background"))

    # --- Window ---
    def update_title(self):
        name = Path(self.document_path).name if self.document_path else "new"
        self.setWindowTitle(f"slate – Whiteboard – {name}")

    def confirm_close(self):
        """Unsaved changes? Ask: save, discard or cancel."""
        choice = self.ask("The whiteboard has unsaved changes.",
                          ["Save", "Discard", "Cancel"])
        if choice is not NOT_AVAILABLE:
            if choice == 0:
                self.save_drawing()
                return self.undo_stack.isClean()
            return choice == 1  # cancel or Esc: keep open
        answer = QMessageBox.question(
            self, "slate", "The whiteboard has unsaved changes. Save?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            self.save_drawing()
            return self.undo_stack.isClean()  # only close if saving worked
        return answer == QMessageBox.Discard
