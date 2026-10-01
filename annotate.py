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
import sys

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QPainter,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
)

from colors import load_palette
from commands import AddItemCommand, EditTextCommand, MoveItemCommand, PropertyCommand, RemoveItemCommand
from config import get_int, get_int_list, get_list, get_str, load_config
from elements import ShapeElement, TextElement
from keymap import KeyMap
from tools import Tool, parse_tool, tool_icon, tool_order
from export import copy_to_clipboard, default_output_dir, render_scene, save_png
from ui import MainBar, PaletteBar, SizeBar, Toast, ToolBar


# --- Einstellungen -----------------------------------------------------------
# Fallbacks, wenn die eigene Config fehlt oder unbrauchbare Werte enthält
DEFAULT_TOOL = Tool.FREEHAND
DEFAULT_COLOR = "red"

# Größe in Stufen ([size]): Alt+A S D F wählt Stufe 1-4, gilt als Strichstärke
# für Formen und als Schriftgröße für Text (Werte in Pixeln)
SIZE_LEVELS = 4
DEFAULT_SIZE_LEVEL = 2  # 1-basiert wie in der Config
DEFAULT_STROKE_WIDTHS = (2, 4, 8, 12)
DEFAULT_TEXT_SIZES = (16, 28, 40, 64)
STROKE_WIDTH_RANGE = (1, 100)
TEXT_SIZE_RANGE = (6, 300)


# Aktionen, die auch während der Texteingabe als Taste wirken (Präfixe der Aktionsnamen).
# Nur Tasten, die beim Tippen kein Zeichen erzeugen sollen, sonst fehlen Buchstaben im Text
ACTIONS_WHILE_TYPING = ("size_",)


def size_values(values, default, value_range, name):
    """Genau SIZE_LEVELS Zahlen im erlaubten Bereich, sonst die Standardwerte."""
    if values is None:
        return list(default)
    low, high = value_range
    if len(values) != SIZE_LEVELS or not all(low <= v <= high for v in values):
        print(f"[size] {name} braucht {SIZE_LEVELS} Werte zwischen {low} und {high}, "
              f"nehme {list(default)}", file=sys.stderr)
        return list(default)
    return list(values)


# --- Capture -----------------------------------------------------------------
def grab_screen():
    """Screenshot des Monitors unter dem Mauszeiger (X11)."""
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    return screen, screen.grabWindow(0)


# --- Zeichenfläche -----------------------------------------------------------
class Canvas(QGraphicsView):
    def __init__(self, screen, pixmap):
        super().__init__()

        # Szene mit dem Screenshot als Hintergrund
        self.scene_ = QGraphicsScene(self)
        background = self.scene_.addPixmap(pixmap)
        # Für den Export: Bereich des Screenshots in der Szene und seine Größe in Pixeln
        self.export_rect = background.boundingRect()
        self.export_size = pixmap.size()
        self.setScene(self.scene_)

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

        config = load_config()

        # Werkzeuge: Reihenfolge, Tasten und Startwerkzeug aus der Config
        self.tools = tool_order(get_list(config, "tools", "order"))
        self.tool = parse_tool(get_str(config, "tools", "default") or "") or DEFAULT_TOOL
        # Tastenbelegung zentral in keymap.py, Overrides aus [keys] der Config
        self.keymap = KeyMap(config)

        # Größen-Stufen aus [size]; pen_width und text_size ergeben sich aus der Stufe
        self.stroke_widths = size_values(
            get_int_list(config, "size", "stroke"), DEFAULT_STROKE_WIDTHS, STROKE_WIDTH_RANGE, "stroke")
        self.text_sizes = size_values(
            get_int_list(config, "size", "text"), DEFAULT_TEXT_SIZES, TEXT_SIZE_RANGE, "text")
        level = get_int(config, "size", "default") or DEFAULT_SIZE_LEVEL
        if not 1 <= level <= SIZE_LEVELS:
            print(f"[size] default={level} außerhalb 1-{SIZE_LEVELS}, nehme {DEFAULT_SIZE_LEVEL}", file=sys.stderr)
            level = DEFAULT_SIZE_LEVEL
        self.size_level = level - 1  # intern 0-basiert
        # Alte Schreibweise [text] size: gilt als Schriftgröße der Startstufe
        legacy = get_int(config, "text", "size")
        if legacy is not None and get_int_list(config, "size", "text") is None:
            low, high = TEXT_SIZE_RANGE
            if low <= legacy <= high:
                self.text_sizes[self.size_level] = legacy

        # Farbwerte aus der Alacritty-Config (Fallback: Standardpalette),
        # Auswahl, Reihenfolge und Startfarbe aus der eigenen Config
        self.palette_ = load_palette()
        self.swatches = self.palette_.swatches(get_list(config, "colors", "order"))
        self.colors = [QColor(c) for c in self.swatches]
        default_color = get_str(config, "colors", "default") or DEFAULT_COLOR
        self.color_index = self.index_of(self.palette_.lookup(default_color))
        self.pen_color = self.colors[self.color_index]

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

        # Gemeinsame Leiste unten mittig: Werkzeuge | Farben | Größe (Klick wählt aus).
        # Auswahl-Werkzeug fest vorne, dann die Zeichenwerkzeuge in Config-Reihenfolge
        self.bar_tools = [Tool.SELECT] + self.tools
        labels = [self.keymap.label("tool_select")]
        labels += [self.keymap.label(f"tool_{i}") for i in range(1, len(self.tools) + 1)]
        self.tool_bar = ToolBar([tool_icon(t) for t in self.bar_tools], labels)
        # lambda: der Leisten-Index wird in das passende Werkzeug übersetzt
        self.tool_bar.selected.connect(lambda i: self.set_tool(self.bar_tools[i]))
        self.palette_bar = PaletteBar(self.swatches)
        self.palette_bar.selected.connect(self.set_color)
        self.size_bar = SizeBar(SIZE_LEVELS)
        self.size_bar.selected.connect(self.set_size)
        self.main_bar = MainBar([self.tool_bar, self.palette_bar, self.size_bar], self)
        self.place_bars()

        self.toast = Toast(self)  # kurze Meldungen, z. B. nach dem Speichern

        # Ausgabe: Zielordner für PNGs ([output] dir), ~ ist erlaubt
        self.output_dir = get_str(config, "output", "dir") or default_output_dir()

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
            "copy_image": self.copy_image,
            "save_png": self.save_image,
            "color_next": lambda: self.set_color(self.color_index + 1),
            "color_prev": lambda: self.set_color(self.color_index - 1),
        }
        for i in range(len(self.tools)):
            # Default-Argument i=i: sonst sähen alle Lambdas am Ende dasselbe (letzte) i
            self.actions[f"tool_{i + 1}"] = lambda i=i: self.set_tool(self.tools[i])
        for i in range(len(self.colors)):
            self.actions[f"color_{i + 1}"] = lambda i=i: self.set_color(i)
        for i in range(SIZE_LEVELS):
            self.actions[f"size_{i + 1}"] = lambda i=i: self.set_size(i)

    def index_of(self, hex_color):
        """Position einer Farbe in der Leiste; fehlt sie, das erste Feld."""
        return self.swatches.index(hex_color) if hex_color in self.swatches else 0

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

    def element_at(self, pos):
        """Oberstes Element an der Szenenposition pos oder None.

        scene.items(pos) prüft über shape(): bei Formen nur der Rand plus Toleranz (D2).
        """
        for item in self.scene_.items(pos):  # sortiert von oben nach unten
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
        item = self.selected_element()
        if item is None:
            self.palette_bar.set_active(self.color_index)
            self.size_bar.set_active(self.size_level)
            return
        name = item.color.name()
        self.palette_bar.set_active(self.swatches.index(name) if name in self.swatches else -1)
        if isinstance(item, ShapeElement):
            levels, value = self.stroke_widths, item.width
        else:
            levels, value = self.text_sizes, item.font_size
        self.size_bar.set_active(levels.index(value) if value in levels else -1)

    # Aktuelle Größe, abgeleitet aus der Stufe
    @property
    def pen_width(self):
        return self.stroke_widths[self.size_level]

    @property
    def text_size(self):
        return self.text_sizes[self.size_level]

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
        self.color_index = index % len(self.colors)
        self.pen_color = self.colors[self.color_index]
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

    def closeEvent(self, event):
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

    # --- Ausgabe ---
    def render_image(self):
        """Screenshot plus Zeichnungen als QImage, ohne Leiste und ohne Textcursor."""
        if self.editing_text:
            self.finish_text()
        self.scene_.clearSelection()  # sonst wäre der gestrichelte Auswahlrahmen im Bild
        self.update_bars()
        return render_scene(self.scene_, self.export_rect, self.export_size)

    def copy_image(self):
        ok, message = copy_to_clipboard(self.render_image())
        self.toast.show_message(message)
        return ok

    def copy_and_quit(self):
        if self.copy_image():
            self.close()

    def save_image(self):
        _, message = save_png(self.render_image(), self.output_dir)
        self.toast.show_message(message)

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

    # --- Maus ---
    def mousePressEvent(self, event):
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

        self.start_pos = pos
        self.current_item = ShapeElement(self.tool, pos, self.pen_color, self.pen_width)
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
        if item and event.button() == Qt.LeftButton:
            self.dragging = None
            self.edit_text(item, old=(item.toPlainText(), item.color, item.font_size))
        else:
            self.mousePressEvent(event)  # sonst wie ein normaler Klick behandeln

    def mouseMoveEvent(self, event):
        if self.passthrough:
            super().mouseMoveEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        if self.dragging:
            self.dragging.setPos(pos - self.drag_offset)
            return
        if self.current_item is None:
            return
        # Werkzeug des Elements, nicht self.tool: ein Tastendruck mitten im Ziehen ändert nichts mehr
        if self.current_item.tool == Tool.FREEHAND:
            self.current_item.add_point(pos)
        else:
            self.current_item.set_end(pos)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.passthrough:
            self.passthrough = False
            super().mouseReleaseEvent(event)
            return
        if self.dragging:
            item, start = self.dragging, self.drag_start
            self.dragging = self.drag_start = self.drag_offset = None
            if item.pos() != start:  # nur echtes Verschieben ist ein Undo-Schritt
                self.undo_stack.push(MoveItemCommand(item, start, item.pos()))
            return
        if self.current_item is None:
            return
        pos = self.mapToScene(event.position().toPoint())
        # Versehentlicher Klick ohne Ziehen: leere Form wieder wegwerfen
        too_small = (pos - self.start_pos).manhattanLength() < 3
        if self.current_item.tool != Tool.FREEHAND and too_small:
            self.scene_.removeItem(self.current_item)
        else:
            self.undo_stack.push(AddItemCommand(self.scene_, self.current_item))
        self.current_item = None
        self.start_pos = None

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
            action = self.keymap.action_for(event)
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
            else:
                self.close()
            return
        action = self.keymap.action_for(event)
        if action in self.actions:  # Plätze ohne Werkzeug/Farbe haben keinen Handler
            self.actions[action]()


# --- Start -------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    screen, pixmap = grab_screen()  # erst grabben, dann Fenster zeigen!
    canvas = Canvas(screen, pixmap)
    canvas.show_overlay()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
