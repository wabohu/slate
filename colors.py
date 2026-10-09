"""Read the color palette (and the font, load_terminal_font) from the Alacritty configuration.

Deliberately without Qt, so the module can be tested directly in the console:

    python colors.py

Everything that can go wrong (missing file, broken TOML, wrong values)
leads to a fallback to the default palette, never to an exception.
"""
import colorsys
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

COLOR_NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")

# Roughly the Alacritty defaults (Tomorrow Night)
DEFAULT_NORMAL = {
    "black": "#1d1f21", "red": "#cc6666", "green": "#b5bd68", "yellow": "#f0c674",
    "blue": "#81a2be", "magenta": "#b294bb", "cyan": "#8abeb7", "white": "#c5c8c6",
}
DEFAULT_BRIGHT = {
    "black": "#666666", "red": "#d54e53", "green": "#b9ca4a", "yellow": "#e7c547",
    "blue": "#7aa6da", "magenta": "#c397d8", "cyan": "#70c0b1", "white": "#eaeaea",
}
DEFAULT_FOREGROUND = "#d8d8d8"
DEFAULT_BACKGROUND = "#1d1f21"

# Alacritty allows nested imports, but also limits the depth
MAX_IMPORT_DEPTH = 5

_HEX_RE = re.compile(r"^(?:#|0x)([0-9a-fA-F]{6})$")


@dataclass
class Palette:
    normal: dict = field(default_factory=lambda: dict(DEFAULT_NORMAL))
    bright: dict = field(default_factory=lambda: dict(DEFAULT_BRIGHT))
    foreground: str = DEFAULT_FOREGROUND
    background: str = DEFAULT_BACKGROUND  # only for the UI, not in the color bar
    source: str = "default palette"  # where the colors came from (for information only)

    def lookup(self, name):
        """'red' -> normal, 'bright_red' / 'bright red' -> bright, 'foreground',
        'background' or a color value '#rrggbb' directly. Otherwise None."""
        direct = normalize_color(name)
        if direct:
            return direct
        key = name.strip().lower().replace(" ", "_").replace("-", "_")
        if key == "foreground":
            return self.foreground
        if key == "background":
            return self.background
        if key.startswith("bright_"):
            return self.bright.get(key[len("bright_"):])
        return self.normal.get(key)

    def swatches(self, order=None):
        """Colors for the bar.

        With order (list of names, e.g. from the own config) exactly these
        colors in this order. Unknown names are skipped.
        Without order or if nothing valid is left: normal, bright,
        foreground without duplicates.
        """
        if order:
            result = []
            for name in order:
                color = self.lookup(name)
                if color:
                    result.append(color)
                else:
                    print(f"[colors] Unknown color name: {name!r}", file=sys.stderr)
            if result:
                return result
        result = []
        for name in COLOR_NAMES:
            result.append(self.normal[name])
        for name in COLOR_NAMES:
            result.append(self.bright[name])
        result.append(self.foreground)
        return list(dict.fromkeys(result))  # keeps the order


# Light backgrounds: darken colors until this contrast is reached
# (WCAG contrast ratio; 3.0 stays close to the original and is easy to read for strokes and bold
# text, 4.5 would be safe even for thin text, but looks darker and harsher)
LIGHT_CONTRAST = 3.0


def _channels(hex_color):
    return [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def luminance(hex_color):
    """Relative luminance according to WCAG, 0 (black) to 1 (white)."""
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in _channels(hex_color)]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    """Contrast ratio of two colors, 1 (equal) to 21 (black/white)."""
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def is_light(hex_color):
    """Light background = black text would be easier to read than white."""
    return contrast(hex_color, "#000000") > contrast(hex_color, "#ffffff")


def darken_for(hex_color, background, target=LIGHT_CONTRAST):
    """Darken a color until it has the contrast target on background.
    Hue and saturation stay, only the lightness drops (HLS color model)."""
    if contrast(hex_color, background) >= target:
        return hex_color
    hue, light, sat = colorsys.rgb_to_hls(*_channels(hex_color))
    while light > 0:
        light = max(0.0, light - 0.01)
        candidate = "#%02x%02x%02x" % tuple(round(c * 255) for c in colorsys.hls_to_rgb(hue, light, sat))
        if contrast(candidate, background) >= target:
            return candidate
    return "#000000"


def adapt_color(hex_color, background, overrides=None):
    """Color as it is shown on background. Dark background: unchanged
    (the Alacritty palette is made for it). Light: own value from overrides
    (base color -> light variant, from [colors.light]) or darkened automatically."""
    if not is_light(background):
        return hex_color
    if overrides and hex_color in overrides:
        return overrides[hex_color]
    return darken_for(hex_color, background)


def normalize_color(value):
    """'#RRGGBB' or '0xRRGGBB' -> '#rrggbb'. Anything else -> None."""
    if not isinstance(value, str):
        return None
    match = _HEX_RE.match(value.strip())
    return f"#{match.group(1).lower()}" if match else None


def find_config():
    """First existing Alacritty config in the official search order."""
    candidates = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidates.append(Path(xdg) / "alacritty" / "alacritty.toml")
    home = Path.home()
    candidates.append(home / ".config" / "alacritty" / "alacritty.toml")
    candidates.append(home / ".alacritty.toml")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _read_toml(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"[colors] Cannot read {path}: {e}", file=sys.stderr)
        return {}


def _import_list(data):
    """Imports from general.import (new) or top-level import (old)."""
    general = data.get("general")
    imports = general.get("import") if isinstance(general, dict) else None
    if imports is None:
        imports = data.get("import")
    if isinstance(imports, str):
        imports = [imports]
    if not isinstance(imports, list):
        return []
    return [i for i in imports if isinstance(i, str)]


def _resolve_import(entry, base_dir):
    """Expand ~ and $VARS, relative paths relative to the importing file."""
    path = Path(os.path.expandvars(os.path.expanduser(entry)))
    if not path.is_absolute():
        path = base_dir / path
    return path


def _merge_colors(target, data):
    """Take color values from a parsed file into target (overwrites)."""
    colors = data.get("colors")
    if not isinstance(colors, dict):
        return
    for section in ("normal", "bright"):
        values = colors.get(section)
        if not isinstance(values, dict):
            continue
        for name in COLOR_NAMES:
            color = normalize_color(values.get(name))
            if color:
                target[section][name] = color
    primary = colors.get("primary")
    if isinstance(primary, dict):
        for key in ("foreground", "background"):
            color = normalize_color(primary.get(key))
            if color:
                target[key] = color


def _merge_font(target, data):
    """Take font families ([font.normal] / [font.bold] family) into target["font"]."""
    font = data.get("font")
    if not isinstance(font, dict):
        return
    for style in ("normal", "bold"):
        values = font.get(style)
        family = values.get("family") if isinstance(values, dict) else None
        if isinstance(family, str) and family.strip():
            target.setdefault("font", {})[style] = family.strip()


def _load_file(path, target, depth, seen):
    """First all imports (in order), then the file itself -> the file wins."""
    path = path.resolve()
    if depth > MAX_IMPORT_DEPTH or path in seen:
        return
    seen.add(path)
    data = _read_toml(path)
    for entry in _import_list(data):
        imported = _resolve_import(entry, path.parent)
        if imported.is_file():
            _load_file(imported, target, depth + 1, seen)
        else:
            print(f"[colors] Import not found: {imported}", file=sys.stderr)
    _merge_colors(target, data)
    _merge_font(target, data)


def load_palette(config_path=None):
    """Palette from the Alacritty config; missing values come from the defaults."""
    palette = Palette()
    try:
        path = Path(config_path) if config_path else find_config()
        if path is None or not path.is_file():
            return palette
        target = {"normal": {}, "bright": {}}
        _load_file(path, target, depth=0, seen=set())
        palette.normal.update(target["normal"])
        palette.bright.update(target["bright"])
        palette.foreground = target.get("foreground", palette.foreground)
        palette.background = target.get("background", palette.background)
        palette.source = str(path)
    except Exception as e:  # last safety net: colors are never a reason to crash
        print(f"[colors] Error loading the palette: {e}", file=sys.stderr)
        return Palette()
    return palette


def load_terminal_font(config_path=None):
    """Font family of the terminal for monospace text: [font.bold] family (text in slate is
    bold), otherwise [font.normal] family; None without a config or entry."""
    try:
        path = Path(config_path) if config_path else find_config()
        if path is None or not path.is_file():
            return None
        target = {"normal": {}, "bright": {}}
        _load_file(path, target, depth=0, seen=set())
        fonts = target.get("font", {})
        return fonts.get("bold") or fonts.get("normal")
    except Exception as e:  # like the palette: the font is never a reason to crash
        print(f"[colors] Error loading the font: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    p = load_palette(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"Source: {p.source}")
    for name in COLOR_NAMES:
        print(f"  {name:8} normal {p.normal[name]}   bright {p.bright[name]}")
    print(f"  foreground {p.foreground}   background {p.background}")
    print(f"Bar ({len(p.swatches())}): {' '.join(p.swatches())}")
    paper = "#f8f6f0"
    print(f"On a light background ({paper}): "
          f"{' '.join(adapt_color(c, paper) for c in p.swatches())}")
