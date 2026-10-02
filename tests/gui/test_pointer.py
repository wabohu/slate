#!/usr/bin/env python3
"""GUI test pointing: e = spotlight (darkened except around the mouse), Shift+E = magnifier,
clicks draw nothing meanwhile, Esc first ends pointing, then the tool.

    python tests/gui/test_pointer.py

Screenshots: tests/gui/out/pointer/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, summary, wait  # noqa: E402

MOUSE = (900, 500)
FAR = (150, 150)        # far from the mouse: darkened by the spotlight


def brightness(color):
    from PySide6.QtGui import QColor
    c = QColor(color)
    return c.red() + c.green() + c.blue()


def main():
    with Session("pointer") as s:
        sink_out = s.start_keysink()  # light background in the screenshot: darkening easy to measure
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        s.move(*MOUSE)
        time.sleep(0.5)
        far_before = s.pixel(*FAR, name="00-normal")
        near_before = s.pixel(MOUSE[0] + 60, MOUSE[1], name="00-normal")

        s.key("e")
        s.move(MOUSE[0] + 1, MOUSE[1])  # movement triggers the repaint
        time.sleep(0.4)
        far = s.pixel(*FAR, name="01-spotlight")
        near = s.pixel(MOUSE[0] + 60, MOUSE[1], name="01-spotlight")
        check("spotlight: darkened far away", brightness(far) < brightness(far_before) - 60)
        check("spotlight: light around the mouse", near == near_before)

        s.drag(800, 400, 1000, 600)  # must not draw anything
        s.key("shift+e")
        s.move(*MOUSE)
        time.sleep(0.4)
        s.screenshot("02-magnifier")
        check("magnifier: spotlight off (light again far away)", s.pixel(*FAR) == far_before)

        s.key("Escape")
        time.sleep(0.3)
        check("Esc ends pointing, not the tool", pid in s.slate_pids())
        s.key("Escape")
        check("second Esc quits the tool", wait(lambda: not s.slate_pids(), 5))
        check("nothing drawn while pointing (no history entry)", s.history_entries() == [])
        check("test window untouched", sink_out.read_text() == "")

        # The magnifier really magnifies: vertical rectangle edge at x=1000, mouse 20 px to its left.
        # With magnification 2 the edge appears in the magnifier at x≈1020.
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(1000, 300, 1200, 700)
        s.move(980, 500)
        time.sleep(0.3)
        plain = [s.pixel(x, 500, name="03-without-magnifier") for x in range(1014, 1027, 3)]
        s.key("shift+e")
        s.move(981, 500)
        time.sleep(0.4)
        lens = [s.pixel(x, 500, name="04-magnifier-edge") for x in range(1014, 1027, 3)]
        check("magnifier: edge appears magnified further right", lens != plain)
        s.key("Escape")
        s.key("Escape")
        wait(lambda: not s.slate_pids(), 5)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
