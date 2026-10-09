"""Settings: default values and everything read from the config at startup.

Settings collects the values that do not change during a session (size levels,
palette, bar colors, step sizes …). What changes (current tool, color, level,
whiteboard background) belongs to the Canvas; it starts with the default_* values.

Missing or unusable values never cause a crash: a hint on stderr, then the default value.
"""
import sys
from pathlib import Path

from PySide6.QtGui import QColor

from colors import load_palette
from config import get_float, get_int, get_int_list, get_list, get_str
from export import default_output_dir
from history import default_history_dir
from keymap import KeyMap
from tools import RECT_RADIUS, Tool, parse_tool, tool_order
from ui import Theme

# Fallbacks if your own config is missing or contains unusable values
DEFAULT_TOOL = Tool.FREEHAND
DEFAULT_COLOR = "red"

# Handles on the selection frame: edge length when drawing and grab radius when clicking.
# All three values in screen pixels for 1080 px screen height, independent of the zoom (Canvas.screen_px)
HANDLE_SIZE = 8
HANDLE_GRAB = 7
HIT_TOLERANCE = 6  # a click this far next to a stroke still counts as a hit (D2)

# Whiteboard view: zoom limits, factor per wheel notch, pixels per notch when panning
ZOOM_RANGE = (0.1, 8.0)
ZOOM_STEP = 1.07
WHEEL_PAN_STEP = 80

# Whiteboard: half the edge length of the "infinite" area, margin around the export ([board] background)
BOARD_EXTENT = 1_000_000
BOARD_EXPORT_MARGIN = 32
DEFAULT_BOARD_BACKGROUND = "background"
# Backgrounds to cycle through (Ctrl+B): Alacritty background (dark), paper white (light)
DEFAULT_BOARD_BACKGROUNDS = ("background", "#f8f6f0")

# Move the selection with hjkl ([move]): screen pixels per key press, normal and fine (Shift)
DEFAULT_MOVE_STEP = 10
DEFAULT_MOVE_STEP_FINE = 1
MOVE_STEP_RANGE = (1, 500)

# Rotate the selection with Q / Shift+Q: degrees per key press
ROTATE_STEP = 5
# Rotate handle above the frame: distance from the top edge (screen pixels for 1080 px, Canvas.screen_px)
ROTATE_HANDLE_OFFSET = 24

# Corner radius of new rectangles ([rect] in the config): screenshot and whiteboard
DEFAULT_RECT_RADIUS = 4
DEFAULT_RECT_RADIUS_BOARD = 20
RECT_RADIUS_RANGE = (0, 200)

# Fine adjustment via Alt+wheel: pixels per notch
WHEEL_TEXT_STEP = 2
WHEEL_STROKE_STEP = 1

# Bar colors ([ui]): names as in [colors] plus "background", or "#rrggbb"
DEFAULT_BAR_BACKGROUND = "background"  # background from Alacritty colors.primary
DEFAULT_BAR_FOREGROUND = "foreground"
DEFAULT_BAR_ACCENT = "blue"  # highlights, e.g. keys in the overview (?)
DEFAULT_BAR_HEADING = "magenta"  # headings, e.g. in the overview (?)
DEFAULT_BAR_OPACITY = 0.9

# Size in levels ([size]): Alt+A S D F picks level 1-4, used as stroke width
# for shapes and as font size for text (values in pixels)
SIZE_LEVELS = 4
DEFAULT_SIZE_LEVEL = 2  # 1-based as in the config
DEFAULT_STROKE_WIDTHS = (2, 3, 5, 8)  # screenshot mode: thinner, marks on a dense picture
DEFAULT_STROKE_WIDTHS_BOARD = (2, 4, 8, 12)
DEFAULT_TEXT_SIZES = (16, 28, 40, 64)
STROKE_WIDTH_RANGE = (1, 100)
TEXT_SIZE_RANGE = (6, 300)

# Pointing ([pointer]): radii of spotlight (e) and magnifier (Shift+E), for 1080 px screen height
DEFAULT_SPOTLIGHT_RADIUS = 90
DEFAULT_LENS_RADIUS = 100
POINTER_RADIUS_RANGE = (20, 600)
DEFAULT_SPOTLIGHT_DIM = 45    # darkening outside the spotlight in percent
SPOTLIGHT_DIM_RANGE = (0, 100)
DEFAULT_LENS_ZOOM = 2.0       # magnification of the magnifier
LENS_ZOOM_RANGE = (1.1, 10.0)

# History ([history]): save every screenshot automatically, browse with ← →
DEFAULT_HISTORY_KEEP = 100   # this many entries stay, older ones get deleted when a new one is created
HISTORY_KEEP_RANGE = (1, 100_000)


def clamp(value, value_range):
    low, high = value_range
    return max(low, min(high, value))


def size_values(values, default, value_range, name):
    """Exactly SIZE_LEVELS numbers in the allowed range, otherwise the default values."""
    if values is None:
        return list(default)
    low, high = value_range
    if len(values) != SIZE_LEVELS or not all(low <= v <= high for v in values):
        print(f"[size] {name} needs {SIZE_LEVELS} values between {low} and {high}, "
              f"using {list(default)}", file=sys.stderr)
        return list(default)
    return list(values)

class Settings:
    def __init__(self, config, board):
        """config: parsed config.toml (dict, may be empty); board: whiteboard instead of screenshot."""
        # Tools: order, keys and start tool from the config
        self.tools = tool_order(get_list(config, "tools", "order"))
        self.default_tool = parse_tool(get_str(config, "tools", "default") or "") or DEFAULT_TOOL
        # Key bindings central in keymap.py, overrides from [keys] of the config
        self.keymap = KeyMap(config)

        # Size levels from [size]; stroke width and font size follow from the level
        # Stroke widths: separate levels in the whiteboard ([size] stroke_board)
        stroke_key, stroke_default = ("stroke_board", DEFAULT_STROKE_WIDTHS_BOARD) if board \
            else ("stroke", DEFAULT_STROKE_WIDTHS)
        self.stroke_widths = size_values(
            get_int_list(config, "size", stroke_key), stroke_default, STROKE_WIDTH_RANGE, stroke_key)
        self.text_sizes = size_values(
            get_int_list(config, "size", "text"), DEFAULT_TEXT_SIZES, TEXT_SIZE_RANGE, "text")
        level = get_int(config, "size", "default") or DEFAULT_SIZE_LEVEL
        if not 1 <= level <= SIZE_LEVELS:
            print(f"[size] default={level} outside 1-{SIZE_LEVELS}, using {DEFAULT_SIZE_LEVEL}", file=sys.stderr)
            level = DEFAULT_SIZE_LEVEL
        self.default_size_level = level - 1  # 0-based internally
        # Old spelling [text] size: counts as the font size of the start level
        legacy = get_int(config, "text", "size")
        if legacy is not None and get_int_list(config, "size", "text") is None:
            low, high = TEXT_SIZE_RANGE
            if low <= legacy <= high:
                self.text_sizes[self.default_size_level] = legacy

        # Color values from the Alacritty config (fallback: default palette),
        # choice, order and start color from your own config
        self.palette = load_palette()
        self.swatches = self.palette.swatches(get_list(config, "colors", "order"))
        self.colors = [QColor(c) for c in self.swatches]
        default_color = get_str(config, "colors", "default") or DEFAULT_COLOR
        self.default_color_index = self.index_of(self.palette.lookup(default_color))
        self.theme = self.load_theme(config)
        self.light_overrides = self.load_light_overrides(config)

        # Whiteboard: start background and list for Ctrl+B (None in screenshot mode)
        self.board_background = self.board_backgrounds = None
        if board:
            self.board_background = self.config_color(config, "board", "background", DEFAULT_BOARD_BACKGROUND)
            self.board_backgrounds = self.load_board_backgrounds(config)

        # Messages and prompts: dunst/rofi or Qt ([ui] messages, dialogs)
        self.use_dunst = self.config_choice(config, "messages", ("dunst", "toast"))
        self.use_rofi = self.config_choice(config, "dialogs", ("rofi", "qt"))
        self.rofi_theme = get_str(config, "ui", "rofi_theme")  # None = rofi/slate.rasi in the project

        # Corner radius of new rectangles from [rect], separate value in the whiteboard
        self.rect_radius = self.config_radius(config, "radius_board", DEFAULT_RECT_RADIUS_BOARD) \
            if board else self.config_radius(config, "radius", DEFAULT_RECT_RADIUS)

        # Step sizes for hjkl from [move]
        self.move_steps = {
            False: self.config_step(config, "step", DEFAULT_MOVE_STEP),
            True: self.config_step(config, "step_fine", DEFAULT_MOVE_STEP_FINE),
        }

        # Output: target folder for PNGs ([output] dir), ~ is allowed
        self.output_dir = get_str(config, "output", "dir") or default_output_dir()

        # Bar at startup: off in screenshot mode, on in the whiteboard ([ui], b toggles)
        self.show_bar = self.config_bool(config, "ui", "show_bar_board", True) if board \
            else self.config_bool(config, "ui", "show_bar", False)

        # Pointing from [pointer]: radii of spotlight and magnifier
        self.spotlight_radius = self.config_int(config, "pointer", "spotlight_radius",
                                                DEFAULT_SPOTLIGHT_RADIUS, POINTER_RADIUS_RANGE)
        self.lens_radius = self.config_int(config, "pointer", "lens_radius", DEFAULT_LENS_RADIUS, POINTER_RADIUS_RANGE)
        self.spotlight_dim = self.config_int(config, "pointer", "spotlight_dim", DEFAULT_SPOTLIGHT_DIM,
                                             SPOTLIGHT_DIM_RANGE)
        self.lens_zoom = self.config_float(config, "pointer", "lens_zoom", DEFAULT_LENS_ZOOM, LENS_ZOOM_RANGE)

        # History from [history]: on/off, folder, count
        self.history_enabled = self.config_bool(config, "history", "enabled", True)
        self.history_dir = Path(get_str(config, "history", "dir") or default_history_dir()).expanduser()
        self.history_keep = self.config_keep(config)

    def config_choice(self, config, key, choices):
        """[ui] key must be one of choices; True = the first (external) variant."""
        value = get_str(config, "ui", key) or choices[0]
        if value not in choices:
            print(f"[ui] {key}={value!r} unknown, allowed: {', '.join(choices)}; using {choices[0]!r}",
                  file=sys.stderr)
            value = choices[0]
        return value == choices[0]

    def config_radius(self, config, key, default):
        """Corner radius from [rect]; outside RECT_RADIUS_RANGE -> default."""
        value = get_int(config, "rect", key)
        if value is None:
            return default
        low, high = RECT_RADIUS_RANGE
        if not low <= value <= high:
            print(f"[rect] {key}={value} outside {low}-{high}, using {default}", file=sys.stderr)
            return default
        return value

    def config_int(self, config, section, key, default, value_range):
        """config[section][key] as an integer in range; missing -> default, otherwise a hint, default."""
        value = get_int(config, section, key)
        if value is None:
            if isinstance(config.get(section), dict) and key in config[section]:
                print(f"[{section}] {key}={config[section][key]!r} is not an integer, using {default}",
                      file=sys.stderr)
            return default
        low, high = value_range
        if not low <= value <= high:
            print(f"[{section}] {key}={value} outside {low}-{high}, using {default}", file=sys.stderr)
            return default
        return value

    def config_float(self, config, section, key, default, value_range):
        """config[section][key] as a number (integers too) in range; missing -> default, otherwise a hint, default."""
        value = get_float(config, section, key)
        if value is None:
            if isinstance(config.get(section), dict) and key in config[section]:
                print(f"[{section}] {key}={config[section][key]!r} is not a number, using {default}", file=sys.stderr)
            return default
        low, high = value_range
        if not low <= value <= high:
            print(f"[{section}] {key}={value} outside {low}-{high}, using {default}", file=sys.stderr)
            return default
        return value

    def config_bool(self, config, section, key, default):
        """config[section][key] as true/false; missing -> default, not a bool -> a hint, default."""
        table = config.get(section)
        value = table.get(key, default) if isinstance(table, dict) else default
        if not isinstance(value, bool):
            print(f"[{section}] {key}={value!r} is not true/false, using {str(default).lower()}", file=sys.stderr)
            return default
        return value

    def config_keep(self, config):
        """[history] keep; outside HISTORY_KEEP_RANGE -> default."""
        value = get_int(config, "history", "keep")
        if value is None:
            return DEFAULT_HISTORY_KEEP
        low, high = HISTORY_KEEP_RANGE
        if not low <= value <= high:
            print(f"[history] keep={value} outside {low}-{high}, using {DEFAULT_HISTORY_KEEP}", file=sys.stderr)
            return DEFAULT_HISTORY_KEEP
        return value

    def config_step(self, config, key, default):
        """Step size from [move]; outside MOVE_STEP_RANGE -> default."""
        value = get_int(config, "move", key)
        if value is None:
            return default
        low, high = MOVE_STEP_RANGE
        if not low <= value <= high:
            print(f"[move] {key}={value} outside {low}-{high}, using {default}", file=sys.stderr)
            return default
        return value

    def config_color(self, config, section, key, default):
        """Color from the config: name from the palette, "background" or "#rrggbb"."""
        name = get_str(config, section, key) or default
        value = self.palette.lookup(name)
        if value is None:
            print(f"[{section}] {key}: unknown color {name!r}, using {default!r}", file=sys.stderr)
            value = self.palette.lookup(default)
        return QColor(value)

    def load_board_backgrounds(self, config):
        """List from [board] backgrounds (names as in [colors], "background", "#rrggbb");
        skip unknown entries, nothing valid -> DEFAULT_BOARD_BACKGROUNDS."""
        names = get_list(config, "board", "backgrounds") or []
        colors = []
        for name in names:
            value = self.palette.lookup(name)
            if value is None:
                print(f"[board] backgrounds: unknown color {name!r}", file=sys.stderr)
            else:
                colors.append(QColor(value))
        if not colors:
            colors = [QColor(self.palette.lookup(name)) for name in DEFAULT_BOARD_BACKGROUNDS]
        return colors

    def load_light_overrides(self, config):
        """[colors.light]: own light variants, e.g. yellow = "#8f5e15".
        Result: base color -> light variant (both "#rrggbb"); skip errors."""
        colors_table = config.get("colors") if isinstance(config.get("colors"), dict) else {}
        table = colors_table.get("light")
        if not isinstance(table, dict):
            return {}
        overrides = {}
        for name, value in table.items():
            base = self.palette.lookup(name)
            light = self.palette.lookup(value) if isinstance(value, str) else None
            if base is None or light is None:
                print(f"[colors.light] {name} = {value!r}: unknown color, skipped", file=sys.stderr)
            else:
                overrides[base] = light
        return overrides

    def load_theme(self, config):
        """Bar colors from [ui]; unknown names or values -> Alacritty colors."""
        def color(key, default):
            return self.config_color(config, "ui", key, default)

        opacity = get_float(config, "ui", "bar_opacity")
        if opacity is None or not 0 <= opacity <= 1:
            if opacity is not None:
                print(f"[ui] bar_opacity={opacity} outside 0-1, using {DEFAULT_BAR_OPACITY}", file=sys.stderr)
            opacity = DEFAULT_BAR_OPACITY
        return Theme(color("bar_background", DEFAULT_BAR_BACKGROUND),
                     color("bar_foreground", DEFAULT_BAR_FOREGROUND), opacity,
                     color("bar_accent", DEFAULT_BAR_ACCENT), color("bar_heading", DEFAULT_BAR_HEADING))

    def index_of(self, hex_color):
        """Position of a color in the bar; if it is missing, the first field."""
        return self.swatches.index(hex_color) if hex_color in self.swatches else 0
