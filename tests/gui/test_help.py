#!/usr/bin/env python3
"""GUI-Test Tastenübersicht: ? öffnet sie (F1 nicht), jede Taste schließt nur sie (Esc beendet
dann nicht das Tool), Klick schließt sie; im Screenshot-Modus und im Whiteboard.

    python tests/gui/test_help.py

Bildschirmfotos: tests/gui/out/help/ (Übersicht ansehen!). Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, summary, wait  # noqa: E402

CENTER = (960, 540)  # dort liegt das Panel, wenn es offen ist


def main():
    with Session("help") as s:
        s.key("alt+Escape")
        check("Overlay gestartet", wait(lambda: s.annotate_pids(), 10))
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.5)
        closed = s.pixel(*CENTER, name="00-ohne")

        s.key("F1")
        time.sleep(0.4)
        check("F1 öffnet nichts", s.pixel(*CENTER) == closed)
        s.key("question")
        check("? öffnet die Übersicht", wait(lambda: s.pixel(*CENTER, name="01-offen") != closed, 3))
        s.key("Escape")
        time.sleep(0.4)
        check("Esc schließt nur die Übersicht", s.pixel(*CENTER) == closed and pid in s.annotate_pids())

        s.key("question")  # ? = Shift+/ auf US-Layout
        check("? öffnet sie wieder", wait(lambda: s.pixel(*CENTER) != closed, 3))
        s.move(50, 50)
        s.run(["xdotool", "click", "1"])  # Klick neben das Panel
        time.sleep(0.4)
        check("Klick schließt die Übersicht", s.pixel(*CENTER) == closed and pid in s.annotate_pids())

        s.key("Escape")
        check("danach beendet Esc das Tool", wait(lambda: not s.annotate_pids(), 5))

        # Whiteboard: eigene Einträge (Ansicht, Hintergrund), kein Verlauf
        s.key("alt+Delete")
        check("Whiteboard gestartet", wait(lambda: s.annotate_pids(), 10))
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.5)
        s.key("question")
        time.sleep(0.4)
        s.screenshot("02-whiteboard")
        s.key("Escape")
        time.sleep(0.3)
        check("Whiteboard: Esc schließt nur die Übersicht", pid in s.annotate_pids())
        s.key("ctrl+q")
        check("Whiteboard beendet", wait(lambda: not s.annotate_pids(), 5))

    # 4K: Panel skaliert mit (Bildschirmfoto ansehen: gleich groß wirkend wie bei 1080p)
    with Session("help-4k", size="3840x2160") as s:
        s.key("alt+Escape")
        wait(lambda: s.annotate_pids(), 10)
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.5)
        closed = s.pixel(1920, 1080, name="00-ohne")
        s.key("question")
        check("4K: Übersicht offen", wait(lambda: s.pixel(1920, 1080, name="01-offen") != closed, 3))
        s.key("Escape")
        s.key("Escape")
        check("4K: beendet", wait(lambda: not s.annotate_pids(), 5))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
