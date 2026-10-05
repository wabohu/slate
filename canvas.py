"""Drawing surface: the Canvas (a QGraphicsView) for the screenshot overlay and the whiteboard.

This file holds setup, state, tool/color/size, bars, selection helpers and keys.
More methods come from the mixins: canvas_input.py (mouse, text, handles, mouse wheel),
canvas_board.py (whiteboard), canvas_output.py (copy, save, messages),
canvas_history.py (history). Fixed values from the config: settings.py. See docs/plan-aufteilung.md.
"""
from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter, QUndoStack
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsScene, QGraphicsView

from canvas_board import BoardMixin
from canvas_crop import CropMixin
from canvas_history import HistoryMixin
from canvas_input import InputMixin
from canvas_output import OutputMixin
from canvas_pointer import PointerMixin
from commands import property_command
from config import load_config
from elements import ImageElement, ShapeElement, TextElement, is_label
from settings import BOARD_EXTENT, HIT_TOLERANCE, ROTATE_STEP, SIZE_LEVELS, Settings
from tools import Tool, tool_icon
from shortcuts import overview
from ui import HelpPanel, MainBar, PaletteBar, SizeBar, Toast, ToolBar, ui_scale
from wm import restore_focus

# All element kinds (selection, saving, stacking order …)
ELEMENT_CLASSES = (ShapeElement, TextElement, ImageElement)

# Screenshot mode: how long to wait after losing focus before the overlay takes it
# back (mouse still over it), so the window manager has finished
FOCUS_RETRY_MS = 50

# Actions that also work as keys while typing text (prefixes of the action names).
# Only keys that should not produce a character while typing, otherwise letters go missing
ACTIONS_WHILE_TYPING = ("size_",)


class Canvas(InputMixin, BoardMixin, OutputMixin, HistoryMixin, PointerMixin, CropMixin, QGraphicsView):
    """Drawing surface for screenshot and whiteboard. More methods in the mixins:
    canvas_input.py (mouse, text, handles, mouse wheel), canvas_board.py (whiteboard view
    and background), canvas_output.py (copy, save, messages),
    canvas_history.py (history), canvas_pointer.py (mouse cursor, spotlight, magnifier),
    canvas_crop.py (crop);
    see docs/plan-aufteilung.md."""

    def __init__(self, screen, pixmap, elements=(), document_path=None, board=False, board_color=None):
        """pixmap: background (screenshot or loaded image), None on the whiteboard;
        elements: loaded elements (bottom -> top); document_path: file that Ctrl+S
        saves to; board: whiteboard instead of screenshot; board_color: background of the
        whiteboard (None = from the config)."""
        super().__init__()
        self.board = board

        self.scene_ = QGraphicsScene(self)
        if board:
            # "Infinite" surface: a very large scene rect to scroll around in freely
            self.scene_.setSceneRect(-BOARD_EXTENT, -BOARD_EXTENT, 2 * BOARD_EXTENT, 2 * BOARD_EXTENT)
            self.background_image = None
        else:
            self.set_background(pixmap)
        for item in elements:  # initial state, therefore not in the undo stack
            self.scene_.addItem(item)
        self.document_path = document_path
        self.setScene(self.scene_)

        if board:
            # Normal window: herbstluftwm tiles it, keyboard via normal focus
            self.resize(screen.availableGeometry().size() * 0.8)
        else:
            # Window: frameless, exactly on the monitor, bypassing the window manager.
            # X11BypassWindowManagerHint = X11 "override-redirect": herbstluftwm does not manage
            # the window. Otherwise the desktop background flickers briefly when a fullscreen
            # window opens/closes. Consequence: no showFullScreen(), focus by hand (show_overlay)
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint
            )
            self.setGeometry(screen.geometry())
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.Antialiasing)

        # Values from the config (do not change during the session), see settings.py
        self.settings = Settings(load_config(), board)
        if not board:
            # Border around an image that does not fill the whole screen (fit_overlay): bar
            # background, opaque. Belongs to the view, not the scene, so never in the export
            edge = QColor(self.settings.theme.background)
            edge.setAlpha(255)
            self.setBackgroundBrush(edge)
        self.tool = self.settings.default_tool
        self.size_level = self.settings.default_size_level
        self.color_index = self.settings.default_color_index
        self.pen_color = self.settings.colors[self.color_index]
        if board:
            # The scene background is rendered too, so it also ends up in the export
            self.board_color = QColor(board_color or self.settings.board_background)
            self.scene_.setBackgroundBrush(self.board_color)
            self.update_title()

        # State
        self.undo_stack = QUndoStack(self)  # all changes, for undo/redo (see commands.py)
        self.current_item = None  # ShapeElement currently being drawn
        self.start_pos = None
        self.editing_text = None  # TextElement while typing
        self.editing_old = None   # (text, color, size) before editing; None = new text
        self.dragging = None      # elements currently being moved (list) or None
        self.drag_origin = None   # mouse point when grabbed (scene)
        self.drag_starts = None   # positions of the elements before moving
        self.rubber = None        # selection rectangle: (start, end, selection before) while dragging
        self.click_only = None    # clicked element of a multi-selection (without dragging: only it)
        self.passthrough = False  # mouse events go to the text editor (set cursor, select text)
        self.wheel_rest = 0       # partial mouse wheel notch (touchpads send small steps)
        self.resizing = None      # (element, handle number, geometry at drag start) while dragging a handle
        self.rotating = None      # (element, center, mouse angle at start, pose at start) while dragging the rotate handle
        self.panning = None       # last mouse position while panning with the middle button
        self.zoom_rest = 0        # partial notch while zooming
        self.overview_return = None  # (view before, view in the overview) for Ctrl+W back
        self.crop_rect = None     # crop (key y, canvas_crop.py), None = whole screenshot
        self.cropping = False     # crop is currently being drawn
        self.crop_drag = None     # start point while drawing
        self.crop_drag_end = None
        self.crop_edit = None     # while dragging: change handle, move or new
        self.marker_kind = "number"  # new markers: "number" (1 2 3) or "letter" (A B C)
        self.pointer_mode = None  # pointing: None, "spotlight" or "lens" (canvas_pointer.py)
        self.cursor_cache = {}    # finished mouse cursors per tool/color/width
        self.asking = False  # rofi prompt open: do not take focus back (canvas_output.ask)
        self.history_path = None  # history entry of this session (canvas_history.py), None = off
        self.history_timer = QTimer(self)
        self.history_timer.setSingleShot(True)
        self.history_timer.timeout.connect(self.save_history)
        self.viewport().setMouseTracking(True)  # mouse movement even without a button (cursor over handles)

        # Shared bar at the bottom center: tools | colors | size (click selects).
        # Select tool fixed at the front, then the drawing tools in config order,
        # marker and blur fixed at the end; blur only in screenshot mode
        # (nothing to hide on the whiteboard)
        self.bar_tools = [Tool.SELECT] + self.settings.tools + [Tool.MARKER] + ([] if board else [Tool.BLUR])
        labels = [self.settings.keymap.label("tool_select")]
        labels += [self.settings.keymap.label(f"tool_{i}") for i in range(1, len(self.settings.tools) + 1)]
        labels += [self.settings.keymap.label("tool_marker")]
        labels += [] if board else [self.settings.keymap.label("tool_blur")]
        self.tool_bar = ToolBar([tool_icon(t) for t in self.bar_tools], labels, self.settings.theme)
        # lambda: translates the bar index into the matching tool
        self.tool_bar.selected.connect(lambda i: self.set_tool(self.bar_tools[i]))
        self.palette_bar = PaletteBar(self.settings.swatches, self.settings.theme)
        if board:
            # Elements ask their scene how their color is shown (elements.shown_color)
            self.scene_.adapt_color = self.adapt_color
            self.refresh_colors()
        self.palette_bar.selected.connect(self.set_color)
        self.size_bar = SizeBar(SIZE_LEVELS, self.settings.theme)
        self.size_bar.selected.connect(self.set_size)
        self.main_bar = MainBar([self.tool_bar, self.palette_bar, self.size_bar], self.settings.theme, self)
        # Scale bar and messages with the screen (4K = twice as large as 1080p)
        self.ui_scale = ui_scale(screen)
        self.main_bar.set_scale(self.ui_scale)
        self.main_bar.setVisible(self.settings.show_bar)  # initial state from [ui], b toggles
        self.place_bars()

        self.toast = Toast(self.settings.theme, self)  # short messages, e.g. after saving
        self.toast.set_scale(self.ui_scale)
        self.help_panel = HelpPanel(self.settings.theme, self)  # shortcut overview (?)

        self.set_tool(self.tool)
        self.set_color(self.color_index)
        self.set_size(self.size_level)
        # After every undo/redo/push the selection may have changed -> update the bar
        self.undo_stack.indexChanged.connect(self.on_undo_index_changed)
        self.undo_stack.indexChanged.connect(self.schedule_history_save)

        # Action (name from keymap.py) -> function. New key = entry there + handler here
        self.actions = {
            "tool_select": lambda: self.set_tool(Tool.SELECT),
            "select_all": self.select_all,
            "raise": lambda: self.restack(+1),
            "lower": lambda: self.restack(-1),
            "rotate_left": lambda: self.rotate_selected(-ROTATE_STEP),  # Qt: positive = clockwise
            "rotate_right": lambda: self.rotate_selected(+ROTATE_STEP),
            "raise_top": lambda: self.restack(+2),
            "lower_bottom": lambda: self.restack(-2),
            "tool_blur": lambda: None if self.board else self.set_tool(Tool.BLUR),
            "tool_marker": self.marker_key,
            "crop": self.crop_key,
            "delete": self.delete_selected,
            "undo": self.undo_stack.undo,
            "redo": self.undo_stack.redo,
            "copy_quit": self.copy_and_quit,
            "copy_path_quit": self.copy_path_and_quit,
            "copy_image": self.copy_selection_or_image,  # with a selection: the elements, otherwise the image
            "paste": self.paste_elements,
            "duplicate": self.duplicate_selected,
            "save": self.save_drawing,
            "quit": self.close,
            "zoom_reset": self.zoom_reset,
            "overview": self.overview,
            "background_next": lambda: self.cycle_board_color(+1),
            "background_prev": lambda: self.cycle_board_color(-1),
            "export_png": self.export_image,
            "history_prev": lambda: self.history_step(-1),
            "history_next": lambda: self.history_step(+1),
            "help": self.show_help,
            "toggle_bar": lambda: self.main_bar.setVisible(not self.main_bar.isVisible()),
            "spotlight": lambda: self.toggle_pointer("spotlight"),
            "magnifier": lambda: self.toggle_pointer("lens"),
            "color_next": lambda: self.set_color(self.color_index + 1),
            "color_prev": lambda: self.set_color(self.color_index - 1),
        }
        for i in range(len(self.settings.tools)):
            # Default argument i=i: otherwise all lambdas would end up seeing the same (last) i
            self.actions[f"tool_{i + 1}"] = lambda i=i: self.set_tool(self.settings.tools[i])
        for i in range(len(self.settings.colors)):
            self.actions[f"color_{i + 1}"] = lambda i=i: self.set_color(i)
        for i in range(SIZE_LEVELS):
            self.actions[f"size_{i + 1}"] = lambda i=i: self.set_size(i)
        for name, (dx, dy) in {"left": (-1, 0), "down": (0, 1), "up": (0, -1), "right": (1, 0)}.items():
            self.actions[f"move_{name}"] = lambda dx=dx, dy=dy: self.move_selected(dx, dy, fine=False)
            self.actions[f"move_{name}_fine"] = lambda dx=dx, dy=dy: self.move_selected(dx, dy, fine=True)

    def set_tool(self, tool):
        self.tool = tool
        if tool != Tool.SELECT:
            self.scene_.clearSelection()  # drawing never affects a selection
        # The start tool may be missing if it is not in [tools] order -> highlight nothing
        self.tool_bar.set_active(self.bar_tools.index(tool) if tool in self.bar_tools else -1)
        self.pointer_mode = None  # changing the tool ends spotlight/magnifier
        self.cropping = False     # and a crop selection in progress
        self.viewport().update()
        self.refresh_cursor()
        self.update_bars()

    # --- Selection ---
    def selected_elements(self):
        """All selected elements, bottom to top."""
        return [e for e in self.elements() if e.isSelected()]

    def selected_element(self):
        """The selected element if exactly one is selected (handles, text editing), otherwise None."""
        items = self.selected_elements()
        return items[0] if len(items) == 1 else None

    def select_all(self):
        """Ctrl+A: select tool, all elements selected."""
        if self.editing_text:
            return
        self.set_tool(Tool.SELECT)
        for item in self.elements():
            item.setSelected(True)
        self.update_bars()

    def zoom(self):
        """Current zoom factor of the view (1.0 = 100 %)."""
        return self.transform().m11()

    def element_at(self, pos):
        """Topmost element at scene position pos or None.

        Searches a small square around pos whose size in screen pixels is fixed
        (HIT_TOLERANCE). Qt checks shape() for this: for shapes only the outline (D2).
        """
        r = HIT_TOLERANCE / self.zoom()
        area = QRectF(pos.x() - r, pos.y() - r, 2 * r, 2 * r)
        for item in self.scene_.items(area, Qt.IntersectsItemShape):  # top to bottom
            if isinstance(item, ELEMENT_CLASSES):
                return item.owner if is_label(item) else item  # a shape's label counts as the shape
        return None

    def on_undo_index_changed(self, _index):
        self.update_bars()
        self.scene_.update()  # markers renumber when one is added or removed

    def update_bars(self):
        """The bar shows the values of the selection, otherwise those for new elements (principle 3).

        If a value of the selection matches no field, nothing is highlighted (-1).
        """
        self.viewport().update()  # redraw frame and handles (drawForeground)
        items = self.selected_elements()
        if not items:
            self.palette_bar.set_active(self.color_index)
            self.size_bar.set_active(self.size_level)
            return
        # Multi-selection: only highlight what all have in common (images have no color/size)
        items = [i for i in items if not isinstance(i, ImageElement)] or items
        names = {i.color.name() for i in items}
        name = names.pop() if len(names) == 1 else None
        self.palette_bar.set_active(self.settings.swatches.index(name) if name in self.settings.swatches else -1)
        levels_of = {self.size_level_of(i) for i in items}
        self.size_bar.set_active(levels_of.pop() if len(levels_of) == 1 else -1)

    def size_level_of(self, item):
        """Size level of an element (0-based) or -1 if the value matches no level."""
        if isinstance(item, ShapeElement):
            levels, value = self.settings.stroke_widths, item.width
        elif isinstance(item, TextElement):
            levels, value = self.settings.text_sizes, item.font_size
        else:  # image: no size level
            return -1
        return levels.index(value) if value in levels else -1

    # Current size, derived from the level
    @property
    def pen_width(self):
        return self.settings.stroke_widths[self.size_level]

    @property
    def text_size(self):
        return self.settings.text_sizes[self.size_level]

    def set_size(self, level):
        """Size level (0-based) for new objects, the text being typed and the selection."""
        self.size_level = level
        if self.editing_text:
            self.editing_text.set_font_size(self.text_size)
        changes = []  # all selected elements, one undo step
        for item in self.selected_elements():
            if isinstance(item, ShapeElement) and item.width != self.pen_width:
                changes.append((item.set_width, item.width, self.pen_width))
            elif isinstance(item, TextElement) and item.font_size != self.text_size:
                changes.append((item.set_font_size, item.font_size, self.text_size))
        if changes:
            self.undo_stack.push(property_command(changes, "Change size"))
        self.refresh_cursor()  # circle or color in the mouse cursor
        self.update_bars()

    def set_color(self, index):
        """Color for new objects, the text being typed and the selection."""
        self.color_index = index % len(self.settings.colors)
        self.pen_color = self.settings.colors[self.color_index]
        if self.editing_text:  # a color change while typing applies to this text
            self.editing_text.set_color(self.pen_color)
        # Copies of QColor, so later changes do not alter the remembered values
        changes = [(item.set_color, QColor(item.color), QColor(self.pen_color))
                   for item in self.selected_elements()
                   if not isinstance(item, ImageElement) and item.color != self.pen_color]
        if changes:
            self.undo_stack.push(property_command(changes, "Change color"))
        self.refresh_cursor()  # circle or color in the mouse cursor
        self.update_bars()

    def place_bars(self):
        """Shared bar at the bottom center."""
        bar = self.main_bar
        bar.move((self.width() - bar.width()) // 2, self.height() - bar.height() - round(20 * self.ui_scale))

    def show_overlay(self):
        """Show the window and take the keyboard focus.

        No keyboard grab any more: it would have caught all keys, including the global
        hotkeys of sxhkd. Instead normal focus via activateWindow() (for a window that
        bypasses the WM, Qt sets the X focus directly). closeEvent gives the focus back
        to herbstluftwm via wm.restore_focus().
        """
        self.show()
        self.take_focus()
        # Normally the scene only becomes active once the window is active. Without an active
        # scene a text item gets no keyboard focus, so activate it by hand here
        QApplication.sendEvent(self.scene_, QEvent(QEvent.WindowActivate))

    def set_background(self, pixmap):
        """Screenshot mode: put pixmap into the scene as background."""
        background = self.scene_.addPixmap(pixmap)
        # For the export: area of the screenshot in the scene and its size in pixels
        self.export_rect = background.boundingRect()
        self.export_size = pixmap.size()
        self.background_image = pixmap.toImage()  # raw, embedded when saving
        # Fixed scene size = image: the view shows it centered (fit_overlay), even if
        # a stroke sticks out over the edge
        self.scene_.setSceneRect(self.export_rect)
        # Blur elements pixelate this raw image (elements.ShapeElement.blur_image)
        self.scene_.blur_source = self.background_image
        self.scene_.blur_scale = self.background_image.width() / max(1.0, self.export_rect.width())

    def replace_content(self, pixmap, elements):
        """History: load another screenshot including its elements into the same canvas.
        Undo starts over; Ctrl+S creates a new file again."""
        if self.editing_text:
            self.finish_text()
        self.current_item = self.dragging = self.resizing = self.rotating = self.rubber = None
        self.undo_stack.clear()  # before scene_.clear(): commands refer to elements
        self.scene_.clear()      # deletes all items, including the old background
        self.set_background(pixmap)
        for item in elements:
            self.scene_.addItem(item)
        self.document_path = None
        self.crop_rect = None
        self.cropping = False
        self.history_timer.stop()  # undo_stack.clear() scheduled a save, not needed
        self.fit_overlay()
        self.update_bars()

    def fit_overlay(self):
        """Screenshot mode: show the whole image. Larger than the screen (e.g. saved on a
        larger monitor) -> scaled down, smaller -> original size; always centered.

        Qt concept: the view has a transformation (zoom). It only changes the display;
        the scene, and with it saving and export, keep the full resolution.
        """
        view, image = self.viewport().size(), self.export_rect.size()
        if view.isEmpty() or image.isEmpty():
            return
        factor = min(1.0, view.width() / image.width(), view.height() / image.height())
        self.resetTransform()
        self.scale(factor, factor)
        self.centerOn(self.export_rect.center())
        self.refresh_cursor()  # circle in the mouse cursor = stroke width on screen

    def marker_key(self):
        """c: marker tool; if it is already active, toggle between 1 2 3 and A B C."""
        if self.tool != Tool.MARKER:
            self.set_tool(Tool.MARKER)
            return
        self.marker_kind = "letter" if self.marker_kind == "number" else "number"
        self.report("Marker: A B C" if self.marker_kind == "letter" else "Marker: 1 2 3")

    def next_marker_order(self):
        """Order for a new marker: after all existing ones."""
        orders = [e.marker_order for e in self.elements() if isinstance(e, ShapeElement) and e.tool == Tool.MARKER]
        return max(orders, default=0) + 1

    def show_help(self):
        """?: overview of the keyboard shortcuts as they are currently bound."""
        data = overview(self.settings.keymap, self.settings.tools, len(self.settings.colors), SIZE_LEVELS, self.board)
        self.help_panel.set_content(data, self.palette_bar.colors)  # colors as in the bar
        self.help_panel.show_centered()

    def take_focus(self):
        """Screenshot mode: take the keyboard focus (again), e.g. after a click when a
        hotkey has focused another window in the meantime."""
        self.activateWindow()
        self.setFocus()

    # Focus follows the mouse (like focus_follows_mouse in herbstluftwm): if the mouse is over
    # the overlay, it gets the keys, otherwise the window under the mouse does.
    def hovered(self):
        return self.isVisible() and self.frameGeometry().contains(QCursor.pos())

    def refocus_if_hovered(self):
        if not self.board and not self.asking and not self.isActiveWindow() and self.hovered():
            self.take_focus()

    def changeEvent(self, event):
        # Qt concept: changeEvent reports state changes of the window, here "active/inactive".
        # If a hotkey took the focus away but the mouse is still here: take it back.
        # Wait briefly so the window manager finishes its focus change first
        if event.type() == QEvent.ActivationChange and not self.board and not self.isActiveWindow():
            QTimer.singleShot(FOCUS_RETRY_MS, self.refocus_if_hovered)
        super().changeEvent(event)

    def enterEvent(self, event):
        self.refocus_if_hovered()  # mouse comes in from another monitor
        super().enterEvent(event)

    def show_window(self):
        """Show the whiteboard as a normal window, point the view at the elements."""
        self.show()
        items = self.elements()
        if items:
            self.centerOn(self.used_rect().center())
        else:
            self.centerOn(0, 0)

    def closeEvent(self, event):
        # QUndoStack remembers the "clean" state (setClean when saving);
        # every change after that makes it "unclean"
        if self.board and not self.undo_stack.isClean() and not self.confirm_close():
            event.ignore()  # window stays open
            return
        if self.history_path is not None:
            self.hide()  # disappear first, then save: feels faster
            self.flush_history()
        if not self.board:
            restore_focus()  # focus to the window herbstluftwm has focused
        # On teardown Qt deletes the scene before the undo stack; the stack still reports
        # changes then. Without disconnecting, update_bars() would run on a deleted scene
        self.undo_stack.indexChanged.disconnect(self.on_undo_index_changed)
        super().closeEvent(event)

    def resizeEvent(self, event):
        # The final size may only arrive after __init__, so place things again here
        super().resizeEvent(event)
        if hasattr(self, "main_bar"):  # can already arrive in the constructor
            self.place_bars()
        if hasattr(self, "help_panel") and self.help_panel.isVisible():
            self.help_panel.center()
        if not self.board:
            self.fit_overlay()

    def elements(self):
        """All elements bottom to top (order when saving). Labels are part of their shape
        (child items) and do not count as elements of their own."""
        return [i for i in self.scene_.items(Qt.AscendingOrder)
                if isinstance(i, ELEMENT_CLASSES) and not is_label(i)]

    # --- Keyboard ---
    def event(self, event):
        # Qt would otherwise swallow Tab/Shift+Tab for moving the focus between widgets
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if self.help_panel.isVisible():  # overview open: any key only closes it
            self.help_panel.hide()
            return
        key = event.key()
        if self.editing_text:
            # While typing, keys go to the text. Exceptions: Esc finishes,
            # size keys (Alt+…) change the font size instead of typing a letter
            action = self.settings.keymap.action_for(event)
            if key == Qt.Key_Escape:
                self.finish_text()
            elif action and action.startswith(ACTIONS_WHILE_TYPING) and action in self.actions:
                self.actions[action]()
            else:
                super().keyPressEvent(event)  # QGraphicsView passes the key on to the scene
            return
        if key == Qt.Key_Escape:  # fixed, so the tool can always be left
            if self.pointer_mode:  # end spotlight/magnifier first
                self.stop_pointer()
            elif self.cropping:  # while selecting a crop: remove the crop
                self.cancel_crop()
            elif self.selected_element():  # clear the selection first, then quit
                self.scene_.clearSelection()
                self.update_bars()
            elif not self.board:  # the whiteboard only closes with Ctrl+Q / closing the window
                self.close()
            return
        action = self.settings.keymap.action_for(event)
        if action in self.actions:  # slots without a tool/color have no handler
            self.actions[action]()
