"""Eigene Konfiguration des Tools: ~/.config/annotate/config.toml

Bewusst ohne Qt, zum Testen direkt aufrufen:

    python config.py

Fehlt die Datei oder ist sie kaputt, gibt es einfach leere Werte.
Wer die Werte benutzt, entscheidet selbst über den Fallback.
"""
import os
import sys
import tomllib
from pathlib import Path


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "annotate" / "config.toml"


def load_config(path=None):
    """Geparste Config als dict; bei jedem Problem ein leeres dict."""
    path = Path(path) if path else config_path()
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"[config] Kann {path} nicht lesen: {e}", file=sys.stderr)
        return {}


def get_list(config, section, key):
    """config[section][key] als Liste von Strings; fehlt/falsch/leer -> None."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, str)] or None


def get_str(config, section, key):
    """config[section][key] als String; fehlt/falsch -> None."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    return value if isinstance(value, str) else None


def get_int(config, section, key):
    """config[section][key] als int; fehlt/falsch -> None (True/False zählen nicht als Zahl)."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


if __name__ == "__main__":
    print(f"Datei: {config_path()}")
    cfg = load_config()
    print(f"Inhalt: {cfg}")
    print(f"Farben:     order={get_list(cfg, 'colors', 'order')}  default={get_str(cfg, 'colors', 'default')}")
    print(f"Werkzeuge:  order={get_list(cfg, 'tools', 'order')}  default={get_str(cfg, 'tools', 'default')}")
    print(f"Text:       size={get_int(cfg, 'text', 'size')}")
