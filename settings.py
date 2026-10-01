"""Einstellungen: Standardwerte und alles, was beim Start aus der Config gelesen wird.

Settings sammelt die Werte, die sich während einer Sitzung nicht ändern (Größen-Stufen,
Palette, Leistenfarben, Schrittweiten …). Was sich ändert (aktuelles Werkzeug, Farbe,
Stufe, Whiteboard-Hintergrund), gehört der Canvas; sie startet mit den default_*-Werten.

Fehlende oder unbrauchbare Werte führen nie zum Absturz: Hinweis auf stderr, Standardwert.
"""
import sys

from PySide6.QtGui import QColor

from colors import load_palette
from config import get_float, get_int, get_int_list, get_list, get_str
from export import default_output_dir
from keymap import KeyMap
from tools import RECT_RADIUS, Tool, parse_tool, tool_order
from ui import Theme

# Fallbacks, wenn die eigene Config fehlt oder unbrauchbare Werte enthält
DEFAULT_TOOL = Tool.FREEHAND
DEFAULT_COLOR = "red"

# Griffe am Auswahlrahmen: Kantenlänge beim Zeichnen und Fangradius beim Anklicken.
# Alle drei Werte in Bildschirm-Pixeln, unabhängig vom Zoom
HANDLE_SIZE = 8
HANDLE_GRAB = 7
HIT_TOLERANCE = 6  # so weit neben einem Strich zählt ein Klick noch als Treffer (D2)

# Whiteboard-Ansicht: Zoomgrenzen, Faktor pro Mausrad-Raste, Pixel pro Raste beim Verschieben
ZOOM_RANGE = (0.1, 8.0)
ZOOM_STEP = 1.07
WHEEL_PAN_STEP = 80

# Whiteboard: halbe Kantenlänge der "unendlichen" Fläche, Rand um den Export ([board] background)
BOARD_EXTENT = 1_000_000
BOARD_EXPORT_MARGIN = 32
DEFAULT_BOARD_BACKGROUND = "background"
# Hintergründe zum Durchblättern (Strg+B): Alacritty-Hintergrund (dunkel), Papierweiß (hell)
DEFAULT_BOARD_BACKGROUNDS = ("background", "#f8f6f0")

# Auswahl mit hjkl verschieben ([move]): Bildschirm-Pixel pro Tastendruck, normal und fein (Shift)
DEFAULT_MOVE_STEP = 10
DEFAULT_MOVE_STEP_FINE = 1
MOVE_STEP_RANGE = (1, 500)

# Eckenradius neuer Rechtecke ([rect] in der Config): Screenshot bzw. Whiteboard
DEFAULT_RECT_RADIUS_BOARD = 20
RECT_RADIUS_RANGE = (0, 200)

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

class Settings:
    def __init__(self, config, board):
        """config: geparste config.toml (dict, darf leer sein); board: Whiteboard statt Screenshot."""
        # Werkzeuge: Reihenfolge, Tasten und Startwerkzeug aus der Config
        self.tools = tool_order(get_list(config, "tools", "order"))
        self.default_tool = parse_tool(get_str(config, "tools", "default") or "") or DEFAULT_TOOL
        # Tastenbelegung zentral in keymap.py, Overrides aus [keys] der Config
        self.keymap = KeyMap(config)

        # Größen-Stufen aus [size]; Strichstärke und Schriftgröße ergeben sich aus der Stufe
        self.stroke_widths = size_values(
            get_int_list(config, "size", "stroke"), DEFAULT_STROKE_WIDTHS, STROKE_WIDTH_RANGE, "stroke")
        self.text_sizes = size_values(
            get_int_list(config, "size", "text"), DEFAULT_TEXT_SIZES, TEXT_SIZE_RANGE, "text")
        level = get_int(config, "size", "default") or DEFAULT_SIZE_LEVEL
        if not 1 <= level <= SIZE_LEVELS:
            print(f"[size] default={level} außerhalb 1-{SIZE_LEVELS}, nehme {DEFAULT_SIZE_LEVEL}", file=sys.stderr)
            level = DEFAULT_SIZE_LEVEL
        self.default_size_level = level - 1  # intern 0-basiert
        # Alte Schreibweise [text] size: gilt als Schriftgröße der Startstufe
        legacy = get_int(config, "text", "size")
        if legacy is not None and get_int_list(config, "size", "text") is None:
            low, high = TEXT_SIZE_RANGE
            if low <= legacy <= high:
                self.text_sizes[self.default_size_level] = legacy

        # Farbwerte aus der Alacritty-Config (Fallback: Standardpalette),
        # Auswahl, Reihenfolge und Startfarbe aus der eigenen Config
        self.palette = load_palette()
        self.swatches = self.palette.swatches(get_list(config, "colors", "order"))
        self.colors = [QColor(c) for c in self.swatches]
        default_color = get_str(config, "colors", "default") or DEFAULT_COLOR
        self.default_color_index = self.index_of(self.palette.lookup(default_color))
        self.theme = self.load_theme(config)
        self.light_overrides = self.load_light_overrides(config)

        # Whiteboard: Start-Hintergrund und Liste für Strg+B (im Screenshot-Modus None)
        self.board_background = self.board_backgrounds = None
        if board:
            self.board_background = self.config_color(config, "board", "background", DEFAULT_BOARD_BACKGROUND)
            self.board_backgrounds = self.load_board_backgrounds(config)

        # Meldungen und Nachfragen: dunst/rofi oder Qt ([ui] messages, dialogs)
        self.use_dunst = self.config_choice(config, "messages", ("dunst", "toast"))
        self.use_rofi = self.config_choice(config, "dialogs", ("rofi", "qt"))
        self.rofi_theme = get_str(config, "ui", "rofi_theme")  # None = rofi/annotate.rasi im Projekt

        # Eckenradius neuer Rechtecke aus [rect], im Whiteboard eigener Wert
        self.rect_radius = self.config_radius(config, "radius_board", DEFAULT_RECT_RADIUS_BOARD) \
            if board else self.config_radius(config, "radius", RECT_RADIUS)

        # Schrittweiten für hjkl aus [move]
        self.move_steps = {
            False: self.config_step(config, "step", DEFAULT_MOVE_STEP),
            True: self.config_step(config, "step_fine", DEFAULT_MOVE_STEP_FINE),
        }

        # Ausgabe: Zielordner für PNGs ([output] dir), ~ ist erlaubt
        self.output_dir = get_str(config, "output", "dir") or default_output_dir()

    def config_choice(self, config, key, choices):
        """[ui] key muss einer der choices sein; True = die erste (externe) Variante."""
        value = get_str(config, "ui", key) or choices[0]
        if value not in choices:
            print(f"[ui] {key}={value!r} unbekannt, erlaubt: {', '.join(choices)}; nehme {choices[0]!r}",
                  file=sys.stderr)
            value = choices[0]
        return value == choices[0]

    def config_radius(self, config, key, default):
        """Eckenradius aus [rect]; außerhalb RECT_RADIUS_RANGE -> Standard."""
        value = get_int(config, "rect", key)
        if value is None:
            return default
        low, high = RECT_RADIUS_RANGE
        if not low <= value <= high:
            print(f"[rect] {key}={value} außerhalb {low}-{high}, nehme {default}", file=sys.stderr)
            return default
        return value

    def config_step(self, config, key, default):
        """Schrittweite aus [move]; außerhalb MOVE_STEP_RANGE -> Standard."""
        value = get_int(config, "move", key)
        if value is None:
            return default
        low, high = MOVE_STEP_RANGE
        if not low <= value <= high:
            print(f"[move] {key}={value} außerhalb {low}-{high}, nehme {default}", file=sys.stderr)
            return default
        return value

    def config_color(self, config, section, key, default):
        """Farbe aus der Config: Name aus der Palette, "background" oder "#rrggbb"."""
        name = get_str(config, section, key) or default
        value = self.palette.lookup(name)
        if value is None:
            print(f"[{section}] {key}: unbekannte Farbe {name!r}, nehme {default!r}", file=sys.stderr)
            value = self.palette.lookup(default)
        return QColor(value)

    def load_board_backgrounds(self, config):
        """Liste aus [board] backgrounds (Namen wie in [colors], "background", "#rrggbb");
        unbekannte Einträge überspringen, nichts Gültiges -> DEFAULT_BOARD_BACKGROUNDS."""
        names = get_list(config, "board", "backgrounds") or []
        colors = []
        for name in names:
            value = self.palette.lookup(name)
            if value is None:
                print(f"[board] backgrounds: unbekannte Farbe {name!r}", file=sys.stderr)
            else:
                colors.append(QColor(value))
        if not colors:
            colors = [QColor(self.palette.lookup(name)) for name in DEFAULT_BOARD_BACKGROUNDS]
        return colors

    def load_light_overrides(self, config):
        """[colors.light]: eigene helle Varianten, z. B. yellow = "#8f5e15".
        Ergebnis: Grundfarbe -> helle Variante (beides "#rrggbb"); Fehler überspringen."""
        colors_table = config.get("colors") if isinstance(config.get("colors"), dict) else {}
        table = colors_table.get("light")
        if not isinstance(table, dict):
            return {}
        overrides = {}
        for name, value in table.items():
            base = self.palette.lookup(name)
            light = self.palette.lookup(value) if isinstance(value, str) else None
            if base is None or light is None:
                print(f"[colors.light] {name} = {value!r}: unbekannte Farbe, übersprungen", file=sys.stderr)
            else:
                overrides[base] = light
        return overrides

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
