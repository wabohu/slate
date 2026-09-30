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
    QFont,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from colors import load_palette
from commands import AddItemCommand, EditTextCommand, MoveItemCommand, RemoveItemCommand
from config import get_int, get_list, get_str, load_config
from elements import ShapeElement
from tools import Tool, parse_tool, tool_icon, tool_order
from ui import PaletteBar, ToolBar


# --- Einstellungen -----------------------------------------------------------
# Fallbacks, wenn die eigene Config fehlt oder unbrauchbare Werte enthält
DEFAULT_TOOL = Tool.FREEHAND
DEFAULT_COLOR = "red"
# Taste an Position i wählt das Werkzeug an Position i von [tools] order
DEFAULT_TOOL_KEYS = ("a", "s", "d", "f", "g", "t")
DEFAULT_UNDO_KEY = "r"
DEFAULT_REDO_KEY = "shift+r"

# Schriftgröße des Text-Werkzeugs in Pixeln ([text] size), plus erlaubter Bereich
DEFAULT_TEXT_SIZE = 28
TEXT_SIZE_RANGE = (6, 300)


def parse_key(name):
    """Einzelne Taste ohne Modifier aus der Config ('t', 'R', ';') -> Qt-Key; sonst None.

    QKeySequence versteht die gleiche Schreibweise wie Qt-Menüs ("Ctrl+T").
    Hier sind nur einzelne Tasten erlaubt, weil Shift schon für die Farben belegt ist.
    """
    seq = QKeySequence(name.strip())
    if seq.count() != 1:
        return None
    combo = seq[0]
    if combo.keyboardModifiers() != Qt.NoModifier or combo.key() == Qt.Key_unknown:
        return None
    return combo.key()


def parse_shortcut(name):
    """Taste mit optionalen Modifiern ('r', 'shift+r', 'ctrl+z') -> QKeyCombination; sonst None.

    QKeyCombination ist Taste + Modifier in einem Wert, vergleichbar mit event.keyCombination().
    """
    seq = QKeySequence(name.strip())
    if seq.count() != 1 or seq[0].key() == Qt.Key_unknown:
        return None
    return seq[0]


def shortcut_or_default(name, default):
    """Tastenkürzel aus der Config oder, wenn fehlend/ungültig, der Standardwert."""
    combo = parse_shortcut(name) if name else None
    if name and combo is None:
        print(f"[keys] Ungültige Taste: {name!r}, nehme {default!r}", file=sys.stderr)
    return combo if combo is not None else parse_shortcut(default)


# Shift+Taste -> Feld der Farbleiste (Position in dieser Liste = Index in der Leiste).
# Hat die Palette weniger Felder, sind die hinteren Kürzel einfach ohne Wirkung.
COLOR_KEYS = (
    Qt.Key_A, Qt.Key_S, Qt.Key_D, Qt.Key_F, Qt.Key_G,
    Qt.Key_Z, Qt.Key_X, Qt.Key_C, Qt.Key_V, Qt.Key_B,
)


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
        self.scene_.addPixmap(pixmap)
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
        # Ungültige Einträge bleiben als None stehen, damit die Positionen zu order passen
        self.tool_key_names = get_list(config, "tools", "keys") or list(DEFAULT_TOOL_KEYS)
        self.tool_keys = [parse_key(name) for name in self.tool_key_names]
        for name, key in zip(self.tool_key_names, self.tool_keys):
            if key is None:
                print(f"[keys] Ungültige Werkzeug-Taste: {name!r}", file=sys.stderr)
        # Undo/Redo dürfen Modifier haben (Standard Redo: Shift+R); sie haben Vorrang vor allen anderen Tasten
        self.undo_key = shortcut_or_default(get_str(config, "keys", "undo"), DEFAULT_UNDO_KEY)
        self.redo_key = shortcut_or_default(get_str(config, "keys", "redo"), DEFAULT_REDO_KEY)
        self.pen_width = 4

        # Textgröße aus der Config, außerhalb des Bereichs -> Standard
        size = get_int(config, "text", "size")
        low, high = TEXT_SIZE_RANGE
        if size is not None and not low <= size <= high:
            print(f"[text] size={size} außerhalb {low}-{high}, nehme {DEFAULT_TEXT_SIZE}", file=sys.stderr)
            size = None
        self.text_size = size or DEFAULT_TEXT_SIZE

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
        self.editing_text = None  # QGraphicsTextItem, solange getippt wird
        self.editing_old = None   # (Text, Farbe) vor dem Bearbeiten; None = neuer Text
        self.dragging = None      # Textobjekt, das gerade verschoben wird
        self.drag_offset = None   # Abstand Mauspunkt -> Item-Position beim Anfassen
        self.drag_start = None    # Item-Position vor dem Verschieben
        self.passthrough = False  # Maus-Events gehen an den Text-Editor (Cursor setzen, markieren)

        # Farbleiste unten; Klick darauf ruft set_color() auf
        self.palette_bar = PaletteBar(self.swatches, self)
        self.palette_bar.selected.connect(self.set_color)

        # Werkzeugleiste darüber, in Config-Reihenfolge; Klick wählt das Werkzeug
        labels = [
            name.upper() if i < len(self.tool_keys) and self.tool_keys[i] is not None else ""
            for i, name in enumerate(self.tool_key_names[:len(self.tools)])
        ]
        labels += [""] * (len(self.tools) - len(labels))  # Werkzeuge ohne Taste
        self.tool_bar = ToolBar([tool_icon(t) for t in self.tools], labels, self)
        # lambda: der Leisten-Index wird in das passende Werkzeug übersetzt
        self.tool_bar.selected.connect(lambda i: self.set_tool(self.tools[i]))
        self.place_bars()

        self.set_tool(self.tool)
        self.set_color(self.color_index)

    def index_of(self, hex_color):
        """Position einer Farbe in der Leiste; fehlt sie, das erste Feld."""
        return self.swatches.index(hex_color) if hex_color in self.swatches else 0

    def set_tool(self, tool):
        self.tool = tool
        # Startwerkzeug kann fehlen, wenn es nicht in [tools] order steht -> nichts markieren
        self.tool_bar.set_active(self.tools.index(tool) if tool in self.tools else -1)

    def set_color(self, index):
        """Farbe für neue Objekte; bereits gezeichnete behalten ihre Farbe."""
        self.color_index = index % len(self.colors)
        self.pen_color = self.colors[self.color_index]
        self.palette_bar.set_active(self.color_index)
        if self.editing_text:  # Farbwechsel während der Eingabe gilt für diesen Text
            self.editing_text.setDefaultTextColor(self.pen_color)

    def place_bars(self):
        """Farbleiste unten mittig, Werkzeugleiste mittig direkt darüber."""
        colors, tools = self.palette_bar, self.tool_bar
        colors.move((self.width() - colors.width()) // 2, self.height() - colors.height() - 20)
        tools.move((self.width() - tools.width()) // 2, colors.y() - tools.height() - 8)

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
        super().closeEvent(event)

    def resizeEvent(self, event):
        # Die endgültige Größe kann erst nach __init__ kommen, darum hier neu platzieren
        super().resizeEvent(event)
        if hasattr(self, "tool_bar"):  # kann schon im Konstruktor kommen
            self.place_bars()

    # --- Text ---
    def start_text(self, pos):
        """Neues Textobjekt an pos anlegen und direkt zum Tippen fokussieren."""
        item = QGraphicsTextItem()
        font = QFont()
        font.setPixelSize(self.text_size)
        font.setBold(True)
        item.setFont(font)
        item.setDefaultTextColor(self.pen_color)
        # Klickpunkt ungefähr auf Höhe der Zeilenmitte
        item.setPos(pos - QPointF(0, item.boundingRect().height() / 2))
        self.scene_.addItem(item)
        self.edit_text(item, old=None)

    def edit_text(self, item, old):
        """Item zum Tippen öffnen. old = (Text, Farbe) vorher, None bei neuem Text."""
        # TextEditorInteraction macht das Item zu einem kleinen Editor (Cursor, Tippen, Auswahl)
        item.setTextInteractionFlags(Qt.TextEditorInteraction)
        item.setFocus()  # Tastatureingaben gehen jetzt über die Szene an dieses Item
        self.editing_text = item
        self.editing_old = old

    def finish_text(self):
        """Eingabe beenden und als Undo-Schritt ablegen; leerer Text verschwindet."""
        item, old = self.editing_text, self.editing_old
        self.editing_text = self.editing_old = None
        item.setTextInteractionFlags(Qt.NoTextInteraction)
        item.clearFocus()
        new = (item.toPlainText(), item.defaultTextColor())
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
        elif new[0] != old[0] or new[1] != old[1]:
            self.undo_stack.push(EditTextCommand(item, old, new))

    def text_at(self, pos):
        """Oberstes Textobjekt an der Szenenposition pos oder None."""
        for item in self.scene_.items(pos):  # sortiert von oben nach unten
            if isinstance(item, QGraphicsTextItem):
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
            if self.tool == Tool.TEXT:
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
        item = self.text_at(pos) if self.tool == Tool.TEXT else None
        if item and event.button() == Qt.LeftButton:
            self.dragging = None
            self.edit_text(item, old=(item.toPlainText(), item.defaultTextColor()))
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
        mods = event.modifiers()
        if self.editing_text:
            # Während der Texteingabe gehen alle Tasten an den Text, nur Esc beendet
            if key == Qt.Key_Escape:
                self.finish_text()
            else:
                super().keyPressEvent(event)  # QGraphicsView reicht die Taste an die Szene weiter
            return
        combo = event.keyCombination()
        if key == Qt.Key_Escape:
            self.close()
        elif combo == self.undo_key:
            self.undo_stack.undo()
        elif combo == self.redo_key:
            self.undo_stack.redo()
        elif mods & Qt.ShiftModifier and key in COLOR_KEYS:
            # Muss vor TOOL_KEYS stehen, sonst würde Shift+A auch das Werkzeug wechseln
            index = COLOR_KEYS.index(key)
            if index < len(self.colors):
                self.set_color(index)
        elif key == Qt.Key_Backtab or (key == Qt.Key_Tab and mods & Qt.ShiftModifier):
            self.set_color(self.color_index - 1)
        elif key == Qt.Key_Tab:
            self.set_color(self.color_index + 1)
        elif key in self.tool_keys and not mods & Qt.ControlModifier:
            # Ohne Strg, damit z. B. ein späteres Strg+S nicht das Werkzeug wechselt
            index = self.tool_keys.index(key)
            if index < len(self.tools):
                self.set_tool(self.tools[index])


# --- Start -------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    screen, pixmap = grab_screen()  # erst grabben, dann Fenster zeigen!
    canvas = Canvas(screen, pixmap)
    canvas.show_overlay()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
