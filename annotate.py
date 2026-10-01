#!/usr/bin/env python3
"""Mini-Annotationstool (Meilenstein 1-5)

- Macht einen Screenshot des Monitors, auf dem der Mauszeiger steht
- Zeigt ihn eingefroren im Vollbild
- Linke Maustaste gedrückt halten und ziehen zum Zeichnen
- A S D F G T: Werkzeug, Tasten und Reihenfolge aus der Config
  (Standard: Freihand, Linie, Pfeil, Rechteck, Kreis/Ellipse, Text)
- Text: klicken, tippen; Esc oder Klick daneben beendet die Eingabe.
  Vorhandenen Text ziehen = verschieben, Doppelklick = bearbeiten
- Shift+A S D F G Z X C V B: Farbe, in der Reihenfolge der Farbleiste
- Tab / Shift+Tab: durch die Farbpalette blättern, Klick auf die Leiste unten wählt
- R / Shift+R: Undo / Redo (Tasten in der Config einstellbar)
- Esc: beenden (während einer Texteingabe: nur die Eingabe beenden)
"""
import argparse
import sys

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QPixmap,
    QBrush,
    QColor,
    QCursor,
    QGuiApplication,
    QPainter,
    QPen,
    QPolygonF,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
)

from canvas_board import BoardMixin
from canvas_output import OutputMixin
from colors import contrast
from commands import AddItemCommand, EditTextCommand, MoveItemCommand, PropertyCommand, RemoveItemCommand
from config import load_config
from elements import ShapeElement, TextElement
from tools import Tool, tool_icon
from document import load_document
from settings import (BOARD_EXTENT, HANDLE_GRAB, HANDLE_SIZE, HIT_TOLERANCE,
                      SIZE_LEVELS, STROKE_WIDTH_RANGE, TEXT_SIZE_RANGE, WHEEL_STROKE_STEP,
                      WHEEL_TEXT_STEP, Settings, clamp)
from ui import MainBar, PaletteBar, SizeBar, Toast, ToolBar

# Aktionen, die auch während der Texteingabe als Taste wirken (Präfixe der Aktionsnamen).
# Nur Tasten, die beim Tippen kein Zeichen erzeugen sollen, sonst fehlen Buchstaben im Text
ACTIONS_WHILE_TYPING = ("size_",)


# --- Capture -----------------------------------------------------------------
def grab_screen():
    """Screenshot des Monitors unter dem Mauszeiger (X11)."""
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    return screen, screen.grabWindow(0)


# --- Zeichenfläche -----------------------------------------------------------
class Canvas(BoardMixin, OutputMixin, QGraphicsView):
    """Zeichenfläche für Screenshot und Whiteboard. Weitere Methoden in den Mixins:
    canvas_board.py (Whiteboard-Ansicht und -Hintergrund), canvas_output.py (Kopieren,
    Speichern, Meldungen); siehe docs/plan-aufteilung.md."""

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

    def delete_selected(self):
        item = self.selected_element()
        if item:
            item.setSelected(False)  # sonst wäre es nach einem Undo noch markiert
            self.undo_stack.push(RemoveItemCommand(self.scene_, item, "Löschen"))

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

    def show_window(self):
        """Whiteboard als normales Fenster zeigen, Ansicht auf die Elemente richten."""
        self.show()
        items = self.elements()
        if items:
            self.centerOn(self.used_rect().center())
        else:
            self.centerOn(0, 0)

    def selection_colors(self):
        """(Linie, Füllung) für Auswahlrahmen und Griffe: die Leistenfarbe mit mehr
        Kontrast zum Whiteboard-Hintergrund als Linie, damit sie auf hell und dunkel sichtbar ist."""
        line, fill = QColor(self.settings.theme.foreground), QColor(self.settings.theme.background)
        if self.board and contrast(fill.name(), self.board_color.name()) > \
                contrast(line.name(), self.board_color.name()):
            line, fill = fill, line
        fill.setAlpha(255)
        line.setAlpha(255)
        return line, fill

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

    def elements(self):
        """Alle Elemente von unten nach oben (Reihenfolge beim Speichern)."""
        return [i for i in self.scene_.items(Qt.AscendingOrder)
                if isinstance(i, (ShapeElement, TextElement))]

    # --- Text ---
    def start_text(self, pos):
        """Neues Textobjekt an pos anlegen und direkt zum Tippen fokussieren."""
        item = TextElement(pos, self.pen_color, self.text_size)
        # Klickpunkt ungefähr auf Höhe der Zeilenmitte
        item.setPos(pos - QPointF(0, item.boundingRect().height() / 2))
        self.scene_.addItem(item)
        self.edit_text(item, old=None)

    def edit_text(self, item, old):
        """Item zum Tippen öffnen. old = (Text, Farbe, Größe) vorher, None bei neuem Text."""
        self.scene_.clearSelection()  # beim Tippen keinen Auswahlrahmen zeigen
        item.start_editing()
        self.editing_text = item
        self.editing_old = old

    def finish_text(self):
        """Eingabe beenden und als Undo-Schritt ablegen; leerer Text verschwindet."""
        item, old = self.editing_text, self.editing_old
        self.editing_text = self.editing_old = None
        item.stop_editing()
        new = (item.toPlainText(), item.color, item.font_size)
        empty = not new[0].strip()

        if old is None:  # neuer Text
            if empty:
                self.scene_.removeItem(item)
            else:
                self.undo_stack.push(AddItemCommand(self.scene_, item, "Text hinzufügen"))
        elif empty:
            # Makro: mehrere Befehle, die mit einem Undo gemeinsam zurückgenommen werden
            self.undo_stack.beginMacro("Text löschen")
            self.undo_stack.push(EditTextCommand(item, old, new))
            self.undo_stack.push(RemoveItemCommand(self.scene_, item))
            self.undo_stack.endMacro()
        elif new != old:
            self.undo_stack.push(EditTextCommand(item, old, new))

    def text_at(self, pos):
        """Oberstes Textobjekt an der Szenenposition pos oder None."""
        for item in self.scene_.items(pos):  # sortiert von oben nach unten
            if isinstance(item, TextElement):
                return item
        return None

    # --- Griffe ---
    def handle_at(self, pos):
        """Nummer des Griffs der Auswahl an Szenenposition pos oder None."""
        item = self.selected_element()
        if item is None or self.tool != Tool.SELECT or self.editing_text:
            return None
        grab = HANDLE_GRAB / self.zoom()  # Fangradius in Szenen-Einheiten
        for i, local in enumerate(item.handle_points()):
            point = item.mapToScene(local)
            if abs(point.x() - pos.x()) <= grab and abs(point.y() - pos.y()) <= grab:
                return i
        return None

    def update_cursor(self, pos):
        """Mauszeiger im Auswahl-Werkzeug: Pfeil, über Griffen ein Größen-Pfeil."""
        if self.tool != Tool.SELECT:
            return
        handle = self.handle_at(pos)
        item = self.selected_element()
        if handle is None:
            cursor = Qt.ArrowCursor
        elif isinstance(item, ShapeElement) and item.tool in (Tool.LINE, Tool.ARROW):
            cursor = Qt.SizeAllCursor
        else:  # Ecken 0/2 diagonal ↖↘, 1/3 diagonal ↗↙
            cursor = Qt.SizeFDiagCursor if handle in (0, 2) else Qt.SizeBDiagCursor
        self.viewport().setCursor(cursor)

    def drawForeground(self, painter, rect):
        """Rahmen und Griffe der Auswahl über allem zeichnen.

        Qt-Konzept: drawForeground gehört zur Ansicht, nicht zur Szene. Was hier
        gezeichnet wird, landet darum nie im exportierten Bild (scene.render).
        """
        item = self.selected_element()
        if item is None or self.tool != Tool.SELECT or self.editing_text:
            return
        points = [item.mapToScene(p) for p in item.handle_points()]
        line, fill = self.selection_colors()
        painter.setRenderHint(QPainter.Antialiasing)
        if len(points) == 4:  # Rahmen durch die Ecken (bei Linien nur die Endpunkte)
            frame = QPen(line, 1, Qt.DashLine)
            frame.setCosmetic(True)  # immer 1 Pixel, unabhängig von Zoom/Transformation
            painter.setPen(frame)
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF(points))
        outline = QPen(line, 1.5)
        outline.setCosmetic(True)
        painter.setPen(outline)
        painter.setBrush(QBrush(fill))
        size = HANDLE_SIZE / self.zoom()  # auf dem Bildschirm immer gleich groß
        for p in points:
            painter.drawRect(QRectF(p.x() - size / 2, p.y() - size / 2, size, size))

    # --- Maus ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton and self.board:
            self.panning = event.position()  # Ansicht verschieben beginnt
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if event.button() != Qt.LeftButton:
            return
        pos = self.mapToScene(event.position().toPoint())

        if self.editing_text:
            if self.editing_text.contains(self.editing_text.mapFromScene(pos)):
                # Klick in den gerade bearbeiteten Text: Qt setzt Cursor bzw. markiert
                self.passthrough = True
                super().mousePressEvent(event)
                return
            # Klick daneben beendet die Eingabe nur
            self.finish_text()
            if self.tool in (Tool.TEXT, Tool.SELECT):
                return

        if self.tool == Tool.SELECT:
            handle = self.handle_at(pos)
            if handle is not None:  # Griff anfassen = Größe ändern
                item = self.selected_element()
                self.resizing = (item, handle, item.geometry())
                return
            # Element anklicken = auswählen und zum Verschieben anfassen; daneben = abwählen
            item = self.element_at(pos)
            self.scene_.clearSelection()
            if item:
                item.setSelected(True)
                self.dragging = item
                self.drag_start = item.pos()
                self.drag_offset = pos - item.pos()
            self.update_bars()
            return

        if self.tool == Tool.TEXT:
            item = self.text_at(pos)
            if item:  # vorhandenen Text anfassen zum Verschieben
                self.dragging = item
                self.drag_start = item.pos()
                self.drag_offset = pos - item.pos()
            else:
                self.start_text(pos)
            return

        if self.current_item is not None:  # vorige Form ohne Loslassen (z. B. Doppelklick)
            self.finish_shape(pos)
        self.start_pos = pos
        self.current_item = ShapeElement(self.tool, pos, self.pen_color, self.pen_width,
                                         radius=self.settings.rect_radius)
        self.scene_.addItem(self.current_item)

    def mouseDoubleClickEvent(self, event):
        # Qt schickt beim zweiten Klick statt mousePressEvent ein DoubleClick-Event
        pos = self.mapToScene(event.position().toPoint())
        if self.editing_text:
            if self.editing_text.contains(self.editing_text.mapFromScene(pos)):
                self.passthrough = True
                super().mouseDoubleClickEvent(event)  # im Editor: Wort markieren
            else:
                self.mousePressEvent(event)  # daneben: Eingabe beenden wie bei einem Klick
            return
        item = self.text_at(pos) if self.tool in (Tool.TEXT, Tool.SELECT) else None
        left = event.button() == Qt.LeftButton
        if item and left:
            self.dragging = None
            self.edit_text(item, old=(item.toPlainText(), item.color, item.font_size))
        elif left and self.tool == Tool.SELECT and self.element_at(pos) is None:
            # Auswahl-Werkzeug, Doppelklick auf leere Stelle: neuer Text (wie Excalidraw).
            # Nur hier, in Zeichenwerkzeugen hätte der erste Klick schon etwas gezeichnet
            self.dragging = None
            self.start_text(pos)
        else:
            self.mousePressEvent(event)  # sonst wie ein normaler Klick behandeln

    def mouseMoveEvent(self, event):
        if self.panning is not None:
            delta = event.position() - self.panning
            self.panning = event.position()
            self.pan_by(delta.x(), delta.y())
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
            self.dragging.setPos(pos - self.drag_offset)
            self.viewport().update()  # Griffe wandern mit
            return
        if self.current_item is None:
            self.update_cursor(pos)  # nur Bewegung ohne Taste
            return
        # Werkzeug des Elements, nicht self.tool: ein Tastendruck mitten im Ziehen ändert nichts mehr
        if self.current_item.tool == Tool.FREEHAND:
            self.current_item.add_point(pos)
        else:
            self.current_item.set_end(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self.panning is not None:
            self.panning = None
            self.viewport().setCursor(Qt.ArrowCursor if self.tool == Tool.SELECT else Qt.CrossCursor)
            return
        if event.button() != Qt.LeftButton:
            return
        if self.passthrough:
            self.passthrough = False
            super().mouseReleaseEvent(event)
            return
        if self.resizing:
            item, _, start = self.resizing
            self.resizing = None
            if item.geometry() != start:  # nur echte Änderung ist ein Undo-Schritt
                self.undo_stack.push(PropertyCommand(item.set_geometry, start, item.geometry(), "Größe ändern"))
            return
        if self.dragging:
            item, start = self.dragging, self.drag_start
            self.dragging = self.drag_start = self.drag_offset = None
            if item.pos() != start:  # nur echtes Verschieben ist ein Undo-Schritt
                self.undo_stack.push(MoveItemCommand(item, start, item.pos()))
            return
        if self.current_item is None:
            return
        self.finish_shape(self.mapToScene(event.position().toPoint()))

    def finish_shape(self, pos):
        """Aufgezogene Form abschließen: als Undo-Schritt ablegen oder, wenn zu klein, verwerfen."""
        # Versehentlicher Klick ohne Ziehen: leere Form wieder wegwerfen
        too_small = (pos - self.start_pos).manhattanLength() < 3
        if self.current_item.tool != Tool.FREEHAND and too_small:
            self.scene_.removeItem(self.current_item)
        else:
            self.undo_stack.push(AddItemCommand(self.scene_, self.current_item))
        self.current_item = None
        self.start_pos = None

    # --- Mausrad ---
    def wheelEvent(self, event):
        """Alt+Mausrad: Größe fein einstellen. Whiteboard: Mausrad verschiebt, Strg+Mausrad zoomt."""
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
        # Mit Alt meldet Qt das Mausrad unter Linux als waagerecht, darum beide Achsen
        delta = event.angleDelta()
        self.wheel_rest += delta.y() or delta.x()
        steps = int(self.wheel_rest / 120)  # 120 = eine Raste
        if steps == 0:
            return
        self.wheel_rest -= steps * 120
        self.adjust_size(steps)

    def move_selected(self, dx, dy, fine):
        """Auswahl um einen Schritt (Bildschirm-Pixel, zoomunabhängig) verschieben."""
        item = self.selected_element()
        if item is None:
            return
        step = self.settings.move_steps[fine] / self.zoom()
        old = item.pos()
        self.undo_stack.push(MoveItemCommand(item, old, old + QPointF(dx * step, dy * step),
                                             "Verschieben", mergeable=True))
        self.update_bars()  # Griffe mitbewegen; beim Zusammenfassen meldet der Stack nichts

    def adjust_size(self, steps):
        """Größe um steps Rasten ändern, unabhängig von den Stufen."""
        if self.editing_text:  # Undo-Schritt entsteht beim Beenden der Eingabe
            item = self.editing_text
            item.set_font_size(clamp(item.font_size + steps * WHEEL_TEXT_STEP, TEXT_SIZE_RANGE))
            return
        item = self.selected_element()
        if isinstance(item, TextElement):
            setter, old = item.set_font_size, item.font_size
            new = clamp(old + steps * WHEEL_TEXT_STEP, TEXT_SIZE_RANGE)
        elif isinstance(item, ShapeElement):
            setter, old = item.set_width, item.width
            new = clamp(old + steps * WHEEL_STROKE_STEP, STROKE_WIDTH_RANGE)
        else:
            self.toast.show_message("Alt+Mausrad: erst ein Element auswählen (W)")
            return
        if new != old:
            self.undo_stack.push(PropertyCommand(setter, old, new, "Größe ändern", mergeable=True))
            self.update_bars()  # beim Zusammenfassen meldet der Stack keine Änderung

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


# --- Start -------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Screenshot-Annotationstool")
    parser.add_argument("file", nargs="?",
                        help="gespeicherte Zeichnung oder beliebiges PNG öffnen statt Screenshot")
    parser.add_argument("--board", action="store_true",
                        help="leeres Whiteboard in einem normalen Fenster statt Screenshot")
    args, qt_args = parser.parse_known_args()  # Rest (z. B. Qt-Optionen) an Qt weiterreichen
    app = QApplication(sys.argv[:1] + qt_args)

    if args.file:
        background, elements, is_drawing, message = load_document(args.file)
        if background is None:
            print(message, file=sys.stderr)
            sys.exit(1)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if isinstance(background, QColor):  # gespeichertes Whiteboard
            canvas = Canvas(screen, None, elements, document_path=args.file,
                            board=True, board_color=background)
            canvas.show_window()
        else:
            # Eigene Zeichnung: Strg+S überschreibt sie. Fremdes Bild: Strg+S legt eine neue Datei an
            canvas = Canvas(screen, QPixmap.fromImage(background), elements,
                            document_path=args.file if is_drawing else None)
            canvas.show_overlay()
        canvas.report(message)
    elif args.board:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        canvas = Canvas(screen, None, board=True)
        canvas.show_window()
    else:
        screen, pixmap = grab_screen()  # erst grabben, dann Fenster zeigen!
        canvas = Canvas(screen, pixmap)
        canvas.show_overlay()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
