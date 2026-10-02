"""History (roadmap 10): every screenshot as an editable PNG in its own folder.

An entry is the same file as when saving with Ctrl+S (document.py): finished
image plus embedded editing data. The file name contains the time of the
screenshot (slate_2026-10-01_14-03-22.png), so sorting by name is
the chronological order. The modification date is no good for this, because older entries
are rewritten when they are edited further.

This file only handles the files; when to save and browse is decided by
canvas_history.py.
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from export import new_file_path

_NAME_RE = re.compile(r"^slate_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:_\d+)?\.png$")


def default_history_dir():
    """~/.local/share/slate/history or $XDG_DATA_HOME/slate/history."""
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "slate" / "history"


def entries(directory):
    """All entries, oldest first. Missing folder = empty history."""
    try:
        files = [p for p in Path(directory).expanduser().iterdir() if _NAME_RE.match(p.name)]
    except OSError:
        return []
    return sorted(files, key=lambda p: p.name)


def new_entry(directory):
    """Path for a new entry (the folder gets created). May raise OSError."""
    return new_file_path(directory)


def is_entry(path, directory):
    """Is path in the history folder and named like an entry?"""
    try:
        path = Path(path).expanduser().resolve()
        return path.parent == Path(directory).expanduser().resolve() and bool(_NAME_RE.match(path.name))
    except OSError:
        return False


def prune(directory, keep):
    """Delete the oldest entries so that at most keep are left. Returns: number deleted."""
    files = entries(directory)
    old = files[:max(0, len(files) - keep)]  # not [:-keep]: with keep=0 that would be empty
    removed = 0
    for path in old:
        try:
            path.unlink()
            removed += 1
        except OSError as e:
            print(f"[history] Cannot delete {path}: {e}", file=sys.stderr)
    return removed


def label(path):
    """Time from the file name for display, e.g. '2026-10-01 14:03'."""
    match = _NAME_RE.match(Path(path).name)
    if not match:
        return Path(path).name
    stamp = datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
    return stamp.strftime("%Y-%m-%d %H:%M")
