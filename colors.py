"""Farbpalette aus der Alacritty-Konfiguration lesen.

Bewusst ohne Qt, damit man das Modul direkt in der Konsole testen kann:

    python colors.py

Alles, was schiefgehen kann (Datei fehlt, kaputtes TOML, falsche Werte),
führt zu einem Fallback auf die Standardpalette, nie zu einer Exception.
"""
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

COLOR_NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")

# Ungefähr die Alacritty-Defaults (Tomorrow Night)
DEFAULT_NORMAL = {
    "black": "#1d1f21", "red": "#cc6666", "green": "#b5bd68", "yellow": "#f0c674",
    "blue": "#81a2be", "magenta": "#b294bb", "cyan": "#8abeb7", "white": "#c5c8c6",
}
DEFAULT_BRIGHT = {
    "black": "#666666", "red": "#d54e53", "green": "#b9ca4a", "yellow": "#e7c547",
    "blue": "#7aa6da", "magenta": "#c397d8", "cyan": "#70c0b1", "white": "#eaeaea",
}
DEFAULT_FOREGROUND = "#d8d8d8"

# Alacritty erlaubt verschachtelte Imports, begrenzt die Tiefe aber auch
MAX_IMPORT_DEPTH = 5

_HEX_RE = re.compile(r"^(?:#|0x)([0-9a-fA-F]{6})$")


@dataclass
class Palette:
    normal: dict = field(default_factory=lambda: dict(DEFAULT_NORMAL))
    bright: dict = field(default_factory=lambda: dict(DEFAULT_BRIGHT))
    foreground: str = DEFAULT_FOREGROUND
    source: str = "Standardpalette"  # woher die Farben kamen (nur zur Info)

    def lookup(self, name):
        """'red' -> normal, 'bright_red' / 'bright red' -> bright, 'foreground'. Sonst None."""
        key = name.strip().lower().replace(" ", "_").replace("-", "_")
        if key == "foreground":
            return self.foreground
        if key.startswith("bright_"):
            return self.bright.get(key[len("bright_"):])
        return self.normal.get(key)

    def swatches(self, order=None):
        """Farben für die Leiste.

        Mit order (Liste von Namen, z. B. aus der eigenen Config) genau diese
        Farben in dieser Reihenfolge. Unbekannte Namen werden übersprungen.
        Ohne order oder wenn nichts Gültiges übrig bleibt: normal, bright,
        foreground ohne Duplikate.
        """
        if order:
            result = []
            for name in order:
                color = self.lookup(name)
                if color:
                    result.append(color)
                else:
                    print(f"[colors] Unbekannter Farbname: {name!r}", file=sys.stderr)
            if result:
                return result
        result = []
        for name in COLOR_NAMES:
            result.append(self.normal[name])
        for name in COLOR_NAMES:
            result.append(self.bright[name])
        result.append(self.foreground)
        return list(dict.fromkeys(result))  # Reihenfolge bleibt erhalten


def normalize_color(value):
    """'#RRGGBB' oder '0xRRGGBB' -> '#rrggbb'. Alles andere -> None."""
    if not isinstance(value, str):
        return None
    match = _HEX_RE.match(value.strip())
    return f"#{match.group(1).lower()}" if match else None


def find_config():
    """Erste existierende Alacritty-Config in der offiziellen Suchreihenfolge."""
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
        print(f"[colors] Kann {path} nicht lesen: {e}", file=sys.stderr)
        return {}


def _import_list(data):
    """Imports aus general.import (neu) bzw. top-level import (alt)."""
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
    """~ und $VARS expandieren, relative Pfade relativ zur importierenden Datei."""
    path = Path(os.path.expandvars(os.path.expanduser(entry)))
    if not path.is_absolute():
        path = base_dir / path
    return path


def _merge_colors(target, data):
    """Farbwerte aus einer geparsten Datei in target übernehmen (überschreibt)."""
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
        color = normalize_color(primary.get("foreground"))
        if color:
            target["foreground"] = color


def _load_file(path, target, depth, seen):
    """Erst alle Imports (in Reihenfolge), dann die Datei selbst -> Datei gewinnt."""
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
            print(f"[colors] Import nicht gefunden: {imported}", file=sys.stderr)
    _merge_colors(target, data)


def load_palette(config_path=None):
    """Palette aus der Alacritty-Config; fehlende Werte kommen aus den Defaults."""
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
        palette.source = str(path)
    except Exception as e:  # letzte Sicherung: Farben sind nie ein Grund abzustürzen
        print(f"[colors] Fehler beim Laden der Palette: {e}", file=sys.stderr)
        return Palette()
    return palette


if __name__ == "__main__":
    p = load_palette(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"Quelle: {p.source}")
    for name in COLOR_NAMES:
        print(f"  {name:8} normal {p.normal[name]}   bright {p.bright[name]}")
    print(f"  foreground {p.foreground}")
    print(f"Leiste ({len(p.swatches())}): {' '.join(p.swatches())}")
