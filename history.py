"""Verlauf (Roadmap 10): jeder Screenshot als bearbeitbares PNG in einem eigenen Ordner.

Ein Eintrag ist dieselbe Datei wie beim Speichern mit Strg+S (document.py): fertiges
Bild plus eingebettete Bearbeitungsdaten. Der Dateiname enthält den Zeitpunkt des
Screenshots (annotate_2026-10-01_14-03-22.png), darum ist die Sortierung nach Namen
die zeitliche Reihenfolge. Das Änderungsdatum taugt dafür nicht, weil ältere Einträge
beim Weiterbearbeiten neu geschrieben werden.

Hier steht nur der Umgang mit Dateien; wann gespeichert und geblättert wird, regelt
canvas_history.py.
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from export import new_file_path

_NAME_RE = re.compile(r"^annotate_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:_\d+)?\.png$")


def default_history_dir():
    """~/.local/share/annotate/history bzw. $XDG_DATA_HOME/annotate/history."""
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "annotate" / "history"


def entries(directory):
    """Alle Einträge, ältester zuerst. Fehlender Ordner = leerer Verlauf."""
    try:
        files = [p for p in Path(directory).expanduser().iterdir() if _NAME_RE.match(p.name)]
    except OSError:
        return []
    return sorted(files, key=lambda p: p.name)


def new_entry(directory):
    """Pfad für einen neuen Eintrag (Ordner wird angelegt). Kann OSError auslösen."""
    return new_file_path(directory)


def is_entry(path, directory):
    """Liegt path im Verlaufsordner und heißt wie ein Eintrag?"""
    try:
        path = Path(path).expanduser().resolve()
        return path.parent == Path(directory).expanduser().resolve() and bool(_NAME_RE.match(path.name))
    except OSError:
        return False


def prune(directory, keep):
    """Älteste Einträge löschen, sodass höchstens keep übrig bleiben. Rückgabe: Anzahl gelöscht."""
    files = entries(directory)
    old = files[:max(0, len(files) - keep)]  # nicht [:-keep]: bei keep=0 wäre das leer
    removed = 0
    for path in old:
        try:
            path.unlink()
            removed += 1
        except OSError as e:
            print(f"[history] Kann {path} nicht löschen: {e}", file=sys.stderr)
    return removed


def label(path):
    """Zeitpunkt aus dem Dateinamen zum Anzeigen, z. B. '01.10. 14:03'."""
    match = _NAME_RE.match(Path(path).name)
    if not match:
        return Path(path).name
    stamp = datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
    return stamp.strftime("%d.%m. %H:%M")
