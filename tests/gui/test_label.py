#!/usr/bin/env python3
"""GUI test labels (text in shapes): rectangle, W, double click into its empty inside,
type, Esc, move the rectangle by its edge; the history entry contains the label, and it
moved along with the shape.

    python tests/gui/test_label.py

Screenshots: tests/gui/out/label/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("label") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(700, 300, 1100, 500)              # rectangle, middle (900, 400)
        s.key("w")
        s.move(900, 400)                         # empty inside
        s.run(["xdotool", "click", "--repeat", "2", "--delay", "80", "1"])
        time.sleep(0.3)
        s.type("Server")
        time.sleep(0.2)
        s.screenshot("01-typing")
        s.key("Escape")
        s.drag(900, 300, 900, 200)               # grab the top edge: move the rectangle up 100 px
        time.sleep(0.3)
        s.screenshot("02-moved")
        s.key("Return")
        check("quit", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        rects = [e for e in load_elements(entries[-1]) if e.tool.name == "RECT"] if entries else []
        if check(f"history: one rectangle ({len(rects)})", len(rects) == 1):
            rect = rects[0]
            check("the rectangle carries the label 'Server'",
                  rect.label is not None and rect.label.toPlainText() == "Server")
            check(f"moved by its edge: 100 px up ({rect.pos().y()})", abs(rect.pos().y() - 200) < 1)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
