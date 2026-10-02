#!/usr/bin/env python3
"""GUI test multi-selection: three rectangles, Ctrl+A, rubber band, Shift+click, move
and delete them together; the history entry contains the result.

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
    return summary()


if __name__ == "__main__":
    sys.exit(main())
