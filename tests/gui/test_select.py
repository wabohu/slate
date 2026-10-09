#!/usr/bin/env python3
"""GUI test multi-selection: three rectangles, Ctrl+A, rubber band, Shift+click, move
and delete them together; the history entry contains the result. Plus stacking order and
rotating with Q / Shift+Q and with the rotate handle (follows the mouse freely).

    python tests/gui/test_select.py

Screenshots: tests/gui/out/select/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("select") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("f")
        for x in (300, 700, 1100):
            s.drag(x, 300, x + 200, 450)
        s.key("ctrl+a")
        time.sleep(0.3)
        s.screenshot("01-all")
        s.drag(250, 250, 950, 500)               # rubber band around the first two
        time.sleep(0.3)
        s.screenshot("02-rubber-band")
        s.drag(500, 375, 520, 425)               # grab the edge of the first: both move
        s.key("Delete")                          # delete both
        time.sleep(0.3)
        s.screenshot("03-deleted")
        s.key("Return")
        check("quit", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        remaining = load_elements(entries[0]) if entries else []
        check(f"only the third rectangle remains ({len(remaining)})",
              len(remaining) == 1 and remaining[0].pos().x() > 1000)

        # Front/back: two overlapping markers, bring the lower one to the front
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("c")
        for x in (600, 625):
            s.move(x, 600)
            s.run(["xdotool", "click", "1"])
        s.key("w")
        s.move(585, 600)                         # left edge: only the first marker
        s.run(["xdotool", "click", "1"])
        s.key("ctrl+shift+Up")
        time.sleep(0.3)
        s.screenshot("04-marker-front")
        s.key("Return")
        wait(lambda: not s.slate_pids(), 10)
        entries = s.history_entries()
        markers = [e for e in load_elements(entries[-1])] if entries else []
        check("Ctrl+Shift+↑: the first marker is on top now",
              len(markers) == 2 and markers[-1].points[1].x() + markers[-1].pos().x() < 610)

        # Rotate: rectangle, W, click on its edge, 6 × Shift+Q = 30°, Q once = back to 25°
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(700, 300, 1100, 500)
        s.key("w")
        s.move(900, 300)                         # top edge of the rectangle
        s.run(["xdotool", "click", "1"])
        for _ in range(6):
            s.key("shift+q")
        s.key("q")
        time.sleep(0.3)
        s.screenshot("05-rotated")
        s.key("Return")
        wait(lambda: not s.slate_pids(), 10)
        entries = s.history_entries()
        rects = [e for e in load_elements(entries[-1]) if e.tool.name == "RECT"] if entries else []
        check(f"Shift+Q ×6, Q ×1: rectangle rotated by 25° ({[r.rotation() for r in rects]})",
              len(rects) == 1 and abs(rects[0].rotation() - 25) < 1e-6)

        # Rotate handle: 24 px above the top edge, straight above the middle (900, 400); drag it
        # to (1137, 409): from -90° (up) to atan2(9, 237) = 2.17°, so 92.17° without snapping
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(700, 300, 1100, 500)              # middle (900, 400)
        s.key("w")
        s.move(900, 300)
        s.run(["xdotool", "click", "1"])
        time.sleep(0.2)
        s.move(900, 276)
        time.sleep(0.2)
        s.screenshot("06-rotate-handle")
        s.run(["xdotool", "mousedown", "1", "mousemove", "1000", "300",
               "mousemove", "1137", "409", "mouseup", "1"])
        time.sleep(0.3)
        s.screenshot("07-rotated-by-handle")
        s.key("Return")
        wait(lambda: not s.slate_pids(), 10)
        entries = s.history_entries()
        rects = [e for e in load_elements(entries[-1]) if e.tool.name == "RECT"] if entries else []
        check(f"rotate handle: follows the mouse freely, about 92.17° ({[r.rotation() for r in rects]})",
              len(rects) == 1 and abs(rects[0].rotation() - 92.17) < 0.1)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
