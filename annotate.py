#!/usr/bin/env python3
"""annotate: Screenshot-Annotationstool und Whiteboard (Start).

    python annotate.py              Screenshot des Monitors unter der Maus markieren
    python annotate.py bild.png     gespeicherte Zeichnung oder beliebiges PNG öffnen
    python annotate.py --board      leeres Whiteboard in einem normalen Fenster

Bedienung: docs/bedienung.md. Die Zeichenfläche steht in canvas.py.
Muss ausführbar bleiben: ~/.local/bin/annotate-board ist ein Symlink hierauf (sxhkd).
"""
import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QApplication

from canvas import Canvas
from document import load_document
from history import is_entry


# --- Capture -----------------------------------------------------------------
def grab_screen():
    """Screenshot des Monitors unter dem Mauszeiger (X11)."""
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    return screen, screen.grabWindow(0)


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
            # Verlaufseintrag: Änderungen landen automatisch dort, Strg+S legt (wie beim
            # frischen Screenshot) eine eigene Datei im Ausgabeordner an
            canvas = Canvas(screen, QPixmap.fromImage(background), elements,
                            document_path=args.file if is_drawing else None)
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
        screen, pixmap = grab_screen()  # erst grabben, dann Fenster zeigen!
        canvas = Canvas(screen, pixmap)
        canvas.show_overlay()
        canvas.start_history()  # neuer Eintrag im Verlauf
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
