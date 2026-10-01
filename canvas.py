"""Zeichenfläche: die Canvas (ein QGraphicsView) für Screenshot-Overlay und Whiteboard.

Hier stehen Aufbau, Zustand, Werkzeug/Farbe/Größe, Leisten, Auswahl-Helfer und Tasten.
Weitere Methoden kommen aus den Mixins: canvas_input.py (Maus, Text, Griffe, Mausrad),
canvas_board.py (Whiteboard), canvas_output.py (Kopieren, Speichern, Meldungen).
Feste Werte aus der Config: settings.py. Siehe docs/plan-aufteilung.md.
"""
from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QUndoStack
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsScene, QGraphicsView

from canvas_board import BoardMixin
from canvas_input import InputMixin
from canvas_output import OutputMixin
from commands import PropertyCommand
from config import load_config
from elements import ShapeElement, TextElement
from settings import BOARD_EXTENT, HIT_TOLERANCE, SIZE_LEVELS, Settings
from tools import Tool, tool_icon
from ui import MainBar, PaletteBar, SizeBar, Toast, ToolBar

# Aktionen, die auch während der Texteingabe als Taste wirken (Präfixe der Aktionsnamen).
# Nur Tasten, die beim Tippen kein Zeichen erzeugen sollen, sonst fehlen Buchstaben im Text
ACTIONS_WHILE_TYPING = ("size_",)


class Canvas(InputMixin, BoardMixin, OutputMixin, QGraphicsView):
    """Zeichenfläche für Screenshot und Whiteboard. Weitere Methoden in den Mixins:
    canvas_input.py (Maus, Text, Griffe, Mausrad), canvas_board.py (Whiteboard-Ansicht
    und -Hintergrund), canvas_output.py (Kopieren, Speichern, Meldungen);
    siehe docs/plan-aufteilung.md."""

    def __init__(self, screen, pixmap, elements=(), document_path=None, board=False, board_color=None):
        """pixmap: Hintergrund (Screenshot oder geladenes Bild), im Whiteboard None;
        elements: geladene Elemente (unten -> oben); document_path: Datei, in die Strg+S
        speichert; board: Whiteboard statt Screenshot; board_color: Hintergrund des
        Whiteboards (None = aus der Config)."""
        super().__init__()
        self.board = board

        self.scene_ = QGraphicsScene(self)
        if board:
            # "Unendliche" Fläche: ein sehr großes Szenen-Rechteck, in dem man frei scrollt
            self.scene_.setSceneRect(-BOARD_EXTENT, -BOARD_EXTENT, 2 * BOARD_EXTENT, 2 * BOARD_EXTENT)
            self.background_image = None
        else:
            # Szene mit dem Screenshot als Hintergrund
            background = self.scene_.addPixmap(pixmap)
            # Für den Export: Bereich des Screenshots in der Szene und seine Größe in Pixeln
            self.export_rect = background.boundingRect()
            self.export_size = pixmap.size()
            self.background_image = pixmap.toImage()  # roh, wird beim Speichern eingebettet
            # Feste Szenengröße = Bild: Die Ansicht zeigt es mittig (fit_overlay), auch wenn
            # ein Strich über den Rand hinausragt
            self.scene_.setSceneRect(self.export_rect)
        for item in elements:  # Ausgangszustand, darum nicht im Undo
            self.scene_.addItem(item)
        self.document_path = document_path
        self.setScene(self.scene_)

        if board:
            # Normales Fenster: herbstluftwm kachelt es, Tastatur über den normalen Fokus
            self.resize(screen.availableGeometry().size() * 0.8)
        else:
            # Fenster: rahmenlos, exakt auf dem Monitor, am Window-Manager vorbei.
            # X11BypassWindowManagerHint = X11 "override-redirect": herbstluftwm verwaltet
            # das Fenster nicht. Sonst flackert beim Öffnen/Schließen eines Vollbildfensters
            # kurz der Desktop-Hintergrund. Folge: kein showFullScreen(), Tastatur per Grab (show_overlay)
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint
            )
            self.setGeometry(screen.geometry())
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.Antialiasing)
        self.setCursor(Qt.CrossCursor)

        # Werte aus der Config (ändern sich während der Sitzung nicht), siehe settings.py
        self.settings = Settings(load_config(), board)
        if not board:
            # Rand um ein Bild, das nicht den ganzen Bildschirm füllt (fit_overlay): Leisten-
            # Hintergrund, deckend. Gehört zur Ansicht, nicht zur Szene, darum nie im Export
            edge = QColor(self.settings.theme.background)
            edge.setAlpha(255)
            self.setBackgroundBrush(edge)
        self.tool = self.settings.default_tool
        self.size_level = self.settings.default_size_level
        self.color_index = self.settings.default_color_index
        self.pen_color = self.settings.colors[self.color_index]
        if board:
            # Der Szenen-Hintergrund wird mitgerendert, landet also auch im Export
            self.board_color = QColor(board_color or self.settings.board_background)
            self.scene_.setBackgroundBrush(self.board_color)
            self.update_title()

        # Zustand
        self.undo_stack = QUndoStack(self)  # alle Änderungen, für Undo/Redo (siehe commands.py)
        self.current_item = None  # ShapeElement, das gerade aufgezogen wird
        self.start_pos = None
        self.editing_text = None  # TextElement, solange getippt wird
        self.editing_old = None   # (Text, Farbe, Größe) vor dem Bearbeiten; None = neuer Text
        self.dragging = None      # Element, das gerade verschoben wird
        self.drag_offset = None   # Abstand Mauspunkt -> Item-Position beim Anfassen
        self.drag_start = None    # Item-Position vor dem Verschieben
        self.passthrough = False  # Maus-Events gehen an den Text-Editor (Cursor setzen, markieren)
        self.wheel_rest = 0       # angefangene Mausrad-Raste (Touchpads liefern kleine Schritte)
        self.resizing = None      # (Element, Griff-Nummer, Geometrie bei Zugbeginn) beim Ziehen am Griff
        self.panning = None       # letzte Mausposition beim Verschieben mit der mittleren Taste
        self.zoom_rest = 0        # angefangene Raste beim Zoomen
        self.overview_return = None  # (Ansicht vorher, Ansicht in der Übersicht) für Strg+W zurück
        self.viewport().setMouseTracking(True)  # Mausbewegung auch ohne Taste (Zeiger über Griffen)

        # Gemeinsame Leiste unten mittig: Werkzeuge | Farben | Größe (Klick wählt aus).
        # Auswahl-Werkzeug fest vorne, dann die Zeichenwerkzeuge in Config-Reihenfolge
        self.bar_tools = [Tool.SELECT] + self.settings.tools
        labels = [self.settings.keymap.label("tool_select")]
        labels += [self.settings.keymap.label(f"tool_{i}") for i in range(1, len(self.settings.tools) + 1)]
        self.tool_bar = ToolBar([tool_icon(t) for t in self.bar_tools], labels, self.settings.theme)
        # lambda: der Leisten-Index wird in das passende Werkzeug übersetzt
        self.tool_bar.selected.connect(lambda i: self.set_tool(self.bar_tools[i]))
        self.palette_bar = PaletteBar(self.settings.swatches, self.settings.theme)
        if board:
            # Elemente fragen ihre Szene, wie ihre Farbe gezeigt wird (elements.shown_color)
            self.scene_.adapt_color = self.adapt_color
            self.refresh_colors()
        self.palette_bar.selected.connect(self.set_color)
        self.size_bar = SizeBar(SIZE_LEVELS, self.settings.theme)
        self.size_bar.selected.connect(self.set_size)
        self.main_bar = MainBar([self.tool_bar, self.palette_bar, self.size_bar], self.settings.theme, self)
        self.place_bars()

        self.toast = Toast(self.settings.theme, self)  # kurze Meldungen, z. B. nach dem Speichern

        self.set_tool(self.tool)
        self.set_color(self.color_index)
        self.set_size(self.size_level)
        # Nach jedem Undo/Redo/Push kann sich die Auswahl geändert haben -> Leiste anpassen
        self.undo_stack.indexChanged.connect(self.on_undo_index_changed)

        # Aktion (Name aus keymap.py) -> Funktion. Neue Taste = Eintrag dort + Handler hier
        self.actions = {
            "tool_select": lambda: self.set_tool(Tool.SELECT),
            "delete": self.delete_selected,
            "undo": self.undo_stack.undo,
            "redo": self.undo_stack.redo,
            "copy_quit": self.copy_and_quit,
            "copy_path_quit": self.copy_path_and_quit,
            "copy_image": self.copy_image,
            "save": self.save_drawing,
            "quit": self.close,
            "zoom_reset": self.zoom_reset,
            "overview": self.overview,
            "background_next": lambda: self.cycle_board_color(+1),
            "background_prev": lambda: self.cycle_board_color(-1),
            "export_png": self.export_image,
            "color_next": lambda: self.set_color(self.color_index + 1),
            "color_prev": lambda: self.set_color(self.color_index - 1),
        }
        for i in range(len(self.settings.tools)):
            # Default-Argument i=i: sonst sähen alle Lambdas am Ende dasselbe (letzte) i
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
            self.scene_.clearSelection()  # Zeichnen wirkt nie auf eine Auswahl
        # Startwerkzeug kann fehlen, wenn es nicht in [tools] order steht -> nichts markieren
        self.tool_bar.set_active(self.bar_tools.index(tool) if tool in self.bar_tools else -1)
        self.viewport().setCursor(Qt.ArrowCursor if tool == Tool.SELECT else Qt.CrossCursor)
        self.update_bars()

    # --- Auswahl ---
    def selected_element(self):
        """Das ausgewählte Element oder None (vorerst höchstens eins)."""
        items = [i for i in self.scene_.selectedItems() if isinstance(i, (ShapeElement, TextElement))]
        return items[0] if items else None

    def zoom(self):
        """Aktueller Zoomfaktor der Ansicht (1.0 = 100 %)."""
        return self.transform().m11()

    def element_at(self, pos):
        """Oberstes Element an der Szenenposition pos oder None.

        Sucht in einem kleinen Quadrat um pos, dessen Größe in Bildschirm-Pixeln fest ist
        (HIT_TOLERANCE). Qt prüft dabei shape(): bei Formen nur der Rand (D2).
        """
        r = HIT_TOLERANCE / self.zoom()
        area = QRectF(pos.x() - r, pos.y() - r, 2 * r, 2 * r)
        for item in self.scene_.items(area, Qt.IntersectsItemShape):  # von oben nach unten
            if isinstance(item, (ShapeElement, TextElement)):
                return item
        return None

    def on_undo_index_changed(self, _index):
        self.update_bars()

    def update_bars(self):
        """Leiste zeigt die Werte der Auswahl, sonst die für neue Elemente (Grundsatz 3).

        Passt ein Wert der Auswahl zu keinem Feld, wird nichts markiert (-1).
        """
        self.viewport().update()  # Rahmen und Griffe neu zeichnen (drawForeground)
        item = self.selected_element()
        if item is None:
            self.palette_bar.set_active(self.color_index)
            self.size_bar.set_active(self.size_level)
            return
        name = item.color.name()
        self.palette_bar.set_active(self.settings.swatches.index(name) if name in self.settings.swatches else -1)
        if isinstance(item, ShapeElement):
            levels, value = self.settings.stroke_widths, item.width
        else:
            levels, value = self.settings.text_sizes, item.font_size
        self.size_bar.set_active(levels.index(value) if value in levels else -1)

    # Aktuelle Größe, abgeleitet aus der Stufe
    @property
    def pen_width(self):
        return self.settings.stroke_widths[self.size_level]

    @property
    def text_size(self):
        return self.settings.text_sizes[self.size_level]

    def set_size(self, level):
        """Größen-Stufe (0-basiert) für neue Objekte, den getippten Text und die Auswahl."""
        self.size_level = level
        if self.editing_text:
            self.editing_text.set_font_size(self.text_size)
        item = self.selected_element()
        if isinstance(item, ShapeElement) and item.width != self.pen_width:
            self.undo_stack.push(
                PropertyCommand(item.set_width, item.width, self.pen_width, "Strichstärke ändern"))
        elif isinstance(item, TextElement) and item.font_size != self.text_size:
            self.undo_stack.push(
                PropertyCommand(item.set_font_size, item.font_size, self.text_size, "Schriftgröße ändern"))
        self.update_bars()

    def set_color(self, index):
        """Farbe für neue Objekte, den getippten Text und die Auswahl."""
        self.color_index = index % len(self.settings.colors)
        self.pen_color = self.settings.colors[self.color_index]
        if self.editing_text:  # Farbwechsel während der Eingabe gilt für diesen Text
            self.editing_text.set_color(self.pen_color)
        item = self.selected_element()
        if item and item.color != self.pen_color:
            # Kopien von QColor, damit spätere Änderungen die gemerkten Werte nicht verändern
            self.undo_stack.push(
                PropertyCommand(item.set_color, QColor(item.color), QColor(self.pen_color), "Farbe ändern"))
        self.update_bars()

    def place_bars(self):
        """Gemeinsame Leiste unten mittig."""
        bar = self.main_bar
        bar.move((self.width() - bar.width()) // 2, self.height() - bar.height() - 20)

    def show_overlay(self):
        """Fenster zeigen und alle Tasten abfangen, ohne den X-Fokus zu verschieben.

        Kein activateWindow(): Das zuvor fokussierte Fenster behält den Fokus, und
        herbstluftwm muss ihn nach dem Schließen nicht neu vergeben.
        """
        self.show()
        self.grabKeyboard()  # Keyboard-Grab: alle Tastendrücke kommen hier an
        self.setFocus()
        # Die Szene wird normalerweise erst aktiv, wenn das Fenster aktiv ist. Ohne aktive
        # Szene bekommt ein Textobjekt keinen Tastaturfokus, darum hier von Hand aktivieren
        QApplication.sendEvent(self.scene_, QEvent(QEvent.WindowActivate))

    def fit_overlay(self):
        """Screenshot-Modus: Bild ganz zeigen. Größer als der Bildschirm (z. B. auf einem
        größeren Monitor gespeichert) -> verkleinert, kleiner -> Originalgröße; immer mittig.

        Qt-Konzept: Die Ansicht hat eine Transformation (Zoom). Sie ändert nur die Anzeige,
        die Szene und damit Speichern und Export behalten die volle Auflösung.
        """
        view, image = self.viewport().size(), self.export_rect.size()
        if view.isEmpty() or image.isEmpty():
            return
        factor = min(1.0, view.width() / image.width(), view.height() / image.height())
        self.resetTransform()
        self.scale(factor, factor)
        self.centerOn(self.export_rect.center())

    def show_window(self):
        """Whiteboard als normales Fenster zeigen, Ansicht auf die Elemente richten."""
        self.show()
        items = self.elements()
        if items:
            self.centerOn(self.used_rect().center())
        else:
            self.centerOn(0, 0)

    def closeEvent(self, event):
        # QUndoStack merkt sich den "sauberen" Stand (setClean beim Speichern);
        # jede Änderung danach macht ihn "unsauber"
        if self.board and not self.undo_stack.isClean() and not self.confirm_close():
            event.ignore()  # Fenster bleibt offen
            return
        self.releaseKeyboard()
        # Beim Abbau löscht Qt die Szene vor dem Undo-Stack; der meldet dabei noch
        # Änderungen. Ohne Trennen liefe update_bars() gegen eine gelöschte Szene
        self.undo_stack.indexChanged.disconnect(self.on_undo_index_changed)
        super().closeEvent(event)

    def resizeEvent(self, event):
        # Die endgültige Größe kann erst nach __init__ kommen, darum hier neu platzieren
        super().resizeEvent(event)
        if hasattr(self, "main_bar"):  # kann schon im Konstruktor kommen
            self.place_bars()
        if not self.board:
            self.fit_overlay()

    def elements(self):
        """Alle Elemente von unten nach oben (Reihenfolge beim Speichern)."""
        return [i for i in self.scene_.items(Qt.AscendingOrder)
                if isinstance(i, (ShapeElement, TextElement))]

    # --- Tastatur ---
    def event(self, event):
        # Tab/Shift+Tab würde Qt sonst für den Fokuswechsel zwischen Widgets schlucken
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        if self.editing_text:
            # Während der Texteingabe gehen die Tasten an den Text. Ausnahmen: Esc beendet,
            # Größen-Tasten (Alt+…) ändern die Schriftgröße, statt einen Buchstaben zu tippen
            action = self.settings.keymap.action_for(event)
            if key == Qt.Key_Escape:
                self.finish_text()
            elif action and action.startswith(ACTIONS_WHILE_TYPING) and action in self.actions:
                self.actions[action]()
            else:
                super().keyPressEvent(event)  # QGraphicsView reicht die Taste an die Szene weiter
            return
        if key == Qt.Key_Escape:  # fest, damit man das Tool immer verlassen kann
            if self.selected_element():  # erst die Auswahl aufheben, dann beenden
                self.scene_.clearSelection()
                self.update_bars()
            elif not self.board:  # Whiteboard schließt nur mit Strg+Q / Fenster schließen
                self.close()
            return
        action = self.settings.keymap.action_for(event)
        if action in self.actions:  # Plätze ohne Werkzeug/Farbe haben keinen Handler
            self.actions[action]()
