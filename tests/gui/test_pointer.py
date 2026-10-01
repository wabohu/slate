#!/usr/bin/env python3
"""GUI-Test Zeigen: e = Spotlight (abgedunkelt außer um die Maus), Shift+E = Lupe,
Klicks zeichnen dabei nichts, Esc beendet erst das Zeigen, dann das Tool.

    python tests/gui/test_pointer.py

Bildschirmfotos: tests/gui/out/pointer/ (ansehen!). Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, summary, wait  # noqa: E402

MOUSE = (900, 500)
FAR = (150, 150)        # weit weg von der Maus: im Spotlight abgedunkelt


def brightness(color):
    from PySide6.QtGui import QColor
    c = QColor(color)
    return c.red() + c.green() + c.blue()


def main():
    with Session("pointer") as s:
        sink_out = s.start_keysink()  # heller Hintergrund im Screenshot: Abdunkeln gut messbar
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.key("alt+Escape")
        check("Overlay gestartet", wait(lambda: s.annotate_pids(), 10))
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        s.move(*MOUSE)
        time.sleep(0.5)
        far_before = s.pixel(*FAR, name="00-normal")
        near_before = s.pixel(MOUSE[0] + 60, MOUSE[1], name="00-normal")

        s.key("e")
        s.move(MOUSE[0] + 1, MOUSE[1])  # Bewegung löst das Neuzeichnen aus
        time.sleep(0.4)
        far = s.pixel(*FAR, name="01-spotlight")
        near = s.pixel(MOUSE[0] + 60, MOUSE[1], name="01-spotlight")
        check("Spotlight: weit weg abgedunkelt", brightness(far) < brightness(far_before) - 60)
        check("Spotlight: um die Maus hell", near == near_before)

        s.drag(800, 400, 1000, 600)  # darf nichts zeichnen
        s.key("shift+e")
        s.move(*MOUSE)
        time.sleep(0.4)
        s.screenshot("02-lupe")
        check("Lupe: Spotlight aus (weit weg wieder hell)", s.pixel(*FAR) == far_before)

        s.key("Escape")
        time.sleep(0.3)
        check("Esc beendet das Zeigen, nicht das Tool", pid in s.annotate_pids())
        s.key("Escape")
        check("zweites Esc beendet das Tool", wait(lambda: not s.annotate_pids(), 5))
        check("beim Zeigen nichts gezeichnet (kein Verlaufseintrag)", s.history_entries() == [])
        check("Testfenster unberührt", sink_out.read_text() == "")

        # Lupe vergrößert wirklich: senkrechte Rechteckkante bei x=1000, Maus 20 px links davon.
        # Mit Vergrößerung 2 erscheint die Kante in der Lupe bei x≈1020.
        s.key("alt+Escape")
        wait(lambda: s.annotate_pids(), 10)
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(1000, 300, 1200, 700)
        s.move(980, 500)
        time.sleep(0.3)
        plain = [s.pixel(x, 500, name="03-ohne-lupe") for x in range(1014, 1027, 3)]
        s.key("shift+e")
        s.move(981, 500)
        time.sleep(0.4)
        lens = [s.pixel(x, 500, name="04-lupe-kante") for x in range(1014, 1027, 3)]
        check("Lupe: Kante erscheint vergrößert weiter rechts", lens != plain)
        s.key("Escape")
        s.key("Escape")
        wait(lambda: not s.annotate_pids(), 5)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
