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
from pathlib import Path

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
    QMessageBox,
)

from colors import load_palette
from commands import AddItemCommand, EditTextCommand, MoveItemCommand, PropertyCommand, RemoveItemCommand
from config import get_float, get_int, get_int_list, get_list, get_str, load_config
from elements import ShapeElement, TextElement
from keymap import KeyMap
from tools import Tool, parse_tool, tool_icon, tool_order
from document import build_document, load_document, save_document
from export import copy_to_clipboard, default_output_dir, new_file_path, render_scene, save_png
from ui import MainBar, PaletteBar, SizeBar, Theme, Toast, ToolBar


# --- Einstellungen -----------------------------------------------------------
# Fallbacks, wenn die eigene Config fehlt oder unbrauchbare Werte enthält
DEFAULT_TOOL = Tool.FREEHAND
DEFAULT_COLOR = "red"

# Griffe am Auswahlrahmen: Kantenlänge beim Zeichnen und Fangradius beim Anklicken (Pixel)
HANDLE_SIZE = 8
HANDLE_GRAB = 7

# Whiteboard: halbe Kantenlänge der "unendlichen" Fläche, Rand um den Export ([board] background)
BOARD_EXTENT = 1_000_000
BOARD_EXPORT_MARGIN = 32
DEFAULT_BOARD_BACKGROUND = "background"

# Feineinstellung per Alt+Mausrad: Pixel pro Raste
WHEEL_TEXT_STEP = 2
WHEEL_STROKE_STEP = 1

# Farben der Leiste ([ui]): Namen wie in [colors] plus "background", oder "#rrggbb"
DEFAULT_BAR_BACKGROUND = "background"  # Hintergrund aus Alacritty colors.primary
DEFAULT_BAR_FOREGROUND = "foreground"
DEFAULT_BAR_OPACITY = 0.9

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


def clamp(value, value_range):
    low, high = value_range
    return max(low, min(high, value))


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
        self.theme = self.load_theme(config)
        if board:
            # Der Szenen-Hintergrund wird mitgerendert, landet also auch im Export
            self.board_color = QColor(board_color) if board_color else \
                self.config_color(config, "board", "background", DEFAULT_BOARD_BACKGROUND)
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
        self.viewport().setMouseTracking(True)  # Mausbewegung auch ohne Taste (Zeiger über Griffen)

        # Gemeinsame Leiste unten mittig: Werkzeuge | Farben | Größe (Klick wählt aus).
        # Auswahl-Werkzeug fest vorne, dann die Zeichenwerkzeuge in Config-Reihenfolge
        self.bar_tools = [Tool.SELECT] + self.tools
        labels = [self.keymap.label("tool_select")]
        labels += [self.keymap.label(f"tool_{i}") for i in range(1, len(self.tools) + 1)]
        self.tool_bar = ToolBar([tool_icon(t) for t in self.bar_tools], labels, self.theme)
        # lambda: der Leisten-Index wird in das passende Werkzeug übersetzt
        self.tool_bar.selected.connect(lambda i: self.set_tool(self.bar_tools[i]))
        self.palette_bar = PaletteBar(self.swatches, self.theme)
        self.palette_bar.selected.connect(self.set_color)
        self.size_bar = SizeBar(SIZE_LEVELS, self.theme)
        self.size_bar.selected.connect(self.set_size)
        self.main_bar = MainBar([self.tool_bar, self.palette_bar, self.size_bar], self.theme, self)
        self.place_bars()

        self.toast = Toast(self.theme, self)  # kurze Meldungen, z. B. nach dem Speichern

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
            "save": self.save_drawing,
            "quit": self.close,
            "export_png": self.export_image,
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

    def config_color(self, config, section, key, default):
        """Farbe aus der Config: Name aus der Palette, "background" oder "#rrggbb"."""
        name = get_str(config, section, key) or default
        value = self.palette_.lookup(name)
        if value is None:
            print(f"[{section}] {key}: unbekannte Farbe {name!r}, nehme {default!r}", file=sys.stderr)
            value = self.palette_.lookup(default)
        return QColor(value)

    def load_theme(self, config):
        """Leistenfarben aus [ui]; unbekannte Namen oder Werte -> Alacritty-Farben."""
        def color(key, default):
            return self.config_color(config, "ui", key, default)

        opacity = get_float(config, "ui", "bar_opacity")
        if opacity is None or not 0 <= opacity <= 1:
            if opacity is not None:
                print(f"[ui] bar_opacity={opacity} außerhalb 0-1, nehme {DEFAULT_BAR_OPACITY}", file=sys.stderr)
            opacity = DEFAULT_BAR_OPACITY
        return Theme(color("bar_background", DEFAULT_BAR_BACKGROUND),
                     color("bar_foreground", DEFAULT_BAR_FOREGROUND), opacity)

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
        self.viewport().update()  # Rahmen und Griffe neu zeichnen (drawForeground)
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

    def show_window(self):
        """Whiteboard als normales Fenster zeigen, Ansicht auf die Elemente richten."""
        self.show()
        items = self.elements()
        if items:
            self.centerOn(self.used_rect().center())
        else:
            self.centerOn(0, 0)

    def update_title(self):
        name = Path(self.document_path).name if self.document_path else "neu"
        self.setWindowTitle(f"annotate – Whiteboard – {name}")

    def confirm_close(self):
        """Ungespeicherte Änderungen? Fragen: Speichern, Verwerfen oder Abbrechen."""
        answer = QMessageBox.question(
            self, "annotate", "Das Whiteboard hat ungespeicherte Änderungen. Speichern?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            self.save_drawing()
            return self.undo_stack.isClean()  # nur schließen, wenn das Speichern geklappt hat
        return answer == QMessageBox.Discard

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

    # --- Ausgabe ---
    def render_image(self):
        """Screenshot plus Zeichnungen als QImage, ohne Leiste und ohne Textcursor."""
        if self.editing_text:
            self.finish_text()
        self.scene_.clearSelection()  # sonst wäre der gestrichelte Auswahlrahmen im Bild
        self.update_bars()
        if self.board:  # nur der benutzte Bereich, Maßstab 1:1
            rect = self.used_rect()
            return render_scene(self.scene_, rect, rect.size().toSize())
        return render_scene(self.scene_, self.export_rect, self.export_size)

    def used_rect(self):
        """Whiteboard: Bereich aller Elemente plus Rand; leer = sichtbarer Ausschnitt."""
        items = self.elements()
        if not items:
            return QRectF(self.mapToScene(self.viewport().rect()).boundingRect().toAlignedRect())
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-BOARD_EXPORT_MARGIN, -BOARD_EXPORT_MARGIN,
                             BOARD_EXPORT_MARGIN, BOARD_EXPORT_MARGIN)
        return QRectF(rect.toAlignedRect())  # auf ganze Pixel, damit das Bild nicht verschwimmt

    def copy_image(self):
        ok, message = copy_to_clipboard(self.render_image())
        self.toast.show_message(message)
        return ok

    def copy_and_quit(self):
        """Enter: kopieren und beenden; im Whiteboard nur kopieren (Fenster bleibt)."""
        if self.copy_image() and not self.board:
            self.close()

    def export_image(self):
        """Sauberes PNG ohne Bearbeitungsdaten, immer als neue Datei."""
        _, message = save_png(self.render_image(), self.output_dir)
        self.toast.show_message(message)

    def elements(self):
        """Alle Elemente von unten nach oben (Reihenfolge beim Speichern)."""
        return [i for i in self.scene_.items(Qt.AscendingOrder)
                if isinstance(i, (ShapeElement, TextElement))]

    def save_drawing(self):
        """Bearbeitbare Zeichnung: beim ersten Mal neue Datei, danach dieselbe überschreiben."""
        rendered = self.render_image()
        try:
            path = self.document_path or new_file_path(self.output_dir, "_board" if self.board else "")
        except OSError as e:
            self.toast.show_message(f"Speichern fehlgeschlagen: {e}")
            return
        background = self.board_color if self.board else self.background_image
        ok, message = save_document(path, rendered, build_document(background, self.elements()))
        if ok:
            self.document_path = path
            self.undo_stack.setClean()  # Stand merken: ab hier "nichts ungespeichert"
            if self.board:
                self.update_title()
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

    # --- Griffe ---
    def handle_at(self, pos):
        """Nummer des Griffs der Auswahl an Szenenposition pos oder None."""
        item = self.selected_element()
        if item is None or self.tool != Tool.SELECT or self.editing_text:
            return None
        for i, local in enumerate(item.handle_points()):
            point = item.mapToScene(local)
            if abs(point.x() - pos.x()) <= HANDLE_GRAB and abs(point.y() - pos.y()) <= HANDLE_GRAB:
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
        painter.setRenderHint(QPainter.Antialiasing)
        if len(points) == 4:  # Rahmen durch die Ecken (bei Linien nur die Endpunkte)
            frame = QPen(self.theme.foreground, 1, Qt.DashLine)
            frame.setCosmetic(True)  # immer 1 Pixel, unabhängig von Zoom/Transformation
            painter.setPen(frame)
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF(points))
        fill = QColor(self.theme.background)
        fill.setAlpha(255)
        painter.setPen(QPen(self.theme.foreground, 1.5))
        painter.setBrush(QBrush(fill))
        half = HANDLE_SIZE / 2
        for p in points:
            painter.drawRect(QRectF(p.x() - half, p.y() - half, HANDLE_SIZE, HANDLE_SIZE))

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
        """Alt+Mausrad: Größe fein einstellen (Auswahl oder gerade getippter Text)."""
        if not event.modifiers() & Qt.AltModifier:
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
            elif not self.board:  # Whiteboard schließt nur mit Strg+Q / Fenster schließen
                self.close()
            return
        action = self.keymap.action_for(event)
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
        canvas.toast.show_message(message)
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
