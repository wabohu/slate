#!/usr/bin/env python3
"""GUI test marker: c, click = circle, drag = circle with pointer line, second c = letters,
the history entry contains the markers.

    python tests/gui/test_marker.py

Screenshots: tests/gui/out/marker/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("marker") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("c")
        s.move(300, 300)
        s.run(["xdotool", "click", "1"])          # 1: circle only
        s.drag(500, 400, 620, 300)                # 2: tip at (500, 400), circle at (620, 300)
        s.move(800, 300)
        s.run(["xdotool", "click", "1"])          # 3
        s.key("c")                                # letters
        s.move(1000, 300)
        s.run(["xdotool", "click", "1"])          # A
        time.sleep(0.4)
        s.screenshot("01-marker")
        s.key("Return")
        check("quit", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        markers = [e for e in load_elements(entries[0]) if e.tool.name == "MARKER"] if entries else []
        check("four markers saved, three numbers and one letter",
              sorted(e.marker_kind for e in markers) == ["letter", "number", "number", "number"])
        with_line = [e for e in markers if e.points[0] != e.points[1]]
        check("exactly one with a pointer line", len(with_line) == 1)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
