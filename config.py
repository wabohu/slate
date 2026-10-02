"""The tool's own configuration: ~/.config/slate/config.toml

Deliberately without Qt, run it directly to test:

    python config.py

If the file is missing or broken, there are simply empty values.
Whoever uses the values decides on the fallback.
"""
import os
import sys
import tomllib
from pathlib import Path


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "slate" / "config.toml"


def load_config(path=None):
    """Parsed config as a dict; an empty dict on any problem."""
    path = Path(path) if path else config_path()
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"[config] Cannot read {path}: {e}", file=sys.stderr)
        return {}


def get_list(config, section, key):
    """config[section][key] as a list of strings; missing/wrong/empty -> None."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, str)] or None


def get_str(config, section, key):
    """config[section][key] as a string; missing/wrong -> None."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    return value if isinstance(value, str) else None


def get_int(config, section, key):
    """config[section][key] as an int; missing/wrong -> None (True/False do not count as numbers)."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def get_float(config, section, key):
    """config[section][key] as a number (int or float); missing/wrong -> None."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def get_int_list(config, section, key):
    """config[section][key] as a list of ints; missing/wrong/empty -> None."""
    table = config.get(section)
    value = table.get(key) if isinstance(table, dict) else None
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        return None
    return value


if __name__ == "__main__":
    print(f"File: {config_path()}")
    cfg = load_config()
    print(f"Content: {cfg}")
    print(f"Colors:     order={get_list(cfg, 'colors', 'order')}  default={get_str(cfg, 'colors', 'default')}")
    print(f"Tools:      order={get_list(cfg, 'tools', 'order')}  default={get_str(cfg, 'tools', 'default')}")
    print(f"Size:       default={get_int(cfg, 'size', 'default')}  stroke={get_int_list(cfg, 'size', 'stroke')}  text={get_int_list(cfg, 'size', 'text')}")
