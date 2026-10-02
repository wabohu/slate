#!/usr/bin/env python3
"""slate: screenshot annotation tool and whiteboard (startup).

    python slate.py              annotate a screenshot of the monitor under the mouse
    python slate.py image.png    open a saved drawing or any PNG
    python slate.py --board      empty whiteboard in a normal window
    python slate.py --last       open the latest screenshot from the history

Usage: docs/usage.md. The drawing surface is in canvas.py.
Must stay executable: ~/.local/bin/slate is a symlink to it (sxhkd).
"""
import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QApplication

from canvas import Canvas
from document import load_document
import history
from config import load_config
from history import is_entry
from notify import notify
from settings import Settings


# --- Capture -----------------------------------------------------------------
def grab_screen():
    """Screenshot of the monitor under the mouse pointer (X11)."""
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    return screen, screen.grabWindow(0)


# --- Start -------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Screenshot annotation tool and whiteboard")
    parser.add_argument("file", nargs="?",
                        help="open a saved drawing or any PNG instead of a screenshot")
    parser.add_argument("--board", action="store_true",
                        help="empty whiteboard in a normal window instead of a screenshot")
    parser.add_argument("--last", action="store_true",
                        help="open the latest screenshot from the history (e.g. via a hotkey)")
    args, qt_args = parser.parse_known_args()  # pass the rest (e.g. Qt options) on to Qt
    app = QApplication(sys.argv[:1] + qt_args)

    if args.last:  # newest history entry; folder from the config ([history] dir)
        entries = history.entries(Settings(load_config(), False).history_dir)
        if not entries:
            message = "History is empty"
            print(message, file=sys.stderr)
            notify(message)  # often started without a terminal (hotkey), so also as a notification
            sys.exit(1)
        args.file = str(entries[-1])

    if args.file:
        background, elements, is_drawing, message, crop = load_document(args.file, with_crop=True)
        if background is None:
            print(message, file=sys.stderr)
            sys.exit(1)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if isinstance(background, QColor):  # saved whiteboard
            canvas = Canvas(screen, None, elements, document_path=args.file,
                            board=True, board_color=background)
            canvas.show_window()
        else:
            # Own drawing: Ctrl+S overwrites it. Other image: Ctrl+S creates a new file
            # History entry: changes land there automatically, Ctrl+S creates (as with a
            # fresh screenshot) a separate file in the output folder
            canvas = Canvas(screen, QPixmap.fromImage(background), elements,
                            document_path=args.file if is_drawing else None)
            canvas.set_crop(crop)  # saved crop (key y), stays editable
            if is_entry(args.file, canvas.settings.history_dir):
                canvas.document_path = None
                canvas.start_history(Path(args.file).expanduser().resolve())
            canvas.show_overlay()
        canvas.report(message)
    elif args.board:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        canvas = Canvas(screen, None, board=True)
        canvas.show_window()
    else:
        screen, pixmap = grab_screen()  # grab first, then show the window!
        canvas = Canvas(screen, pixmap)
        canvas.show_overlay()
        canvas.start_history()  # new entry in the history
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
