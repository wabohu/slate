#!/usr/bin/env python3
"""GUI test connectors: rectangle and ellipse, an arrow drawn from the edge of one to the edge
of the other docks to both (the target is highlighted while drawing); a double click on the
arrow gives it a text; moving the rectangle moves the arrow along; the history entry contains
the docked arrow with its text.

    python tests/gui/test_connector.py

Screenshots: tests/gui/out/connector/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("connector") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(300, 300, 600, 500)               # rectangle, middle (450, 400)
        s.key("g")
        s.drag(1100, 300, 1400, 500)             # ellipse, middle (1250, 400)
        s.key("d")                               # arrow from the rectangle's right edge ...
        s.run(["xdotool", "mousemove", "605", "400", "mousedown", "1",
               "mousemove", "850", "400", "mousemove", "1095", "405"])
        time.sleep(0.3)
        s.screenshot("01-docking-hint")          # ... to the ellipse's left edge, still pressed
        s.run(["xdotool", "mouseup", "1"])
        time.sleep(0.2)
        s.key("w")
        s.move(850, 400)                         # middle of the arrow: double click = text on it
        s.run(["xdotool", "click", "--repeat", "2", "--delay", "80", "1"])
        time.sleep(0.3)
        s.type("SQL")
        s.key("Escape")
        time.sleep(0.2)
        s.drag(300, 400, 300, 600)               # grab the left edge: rectangle 200 px down
        time.sleep(0.3)
        s.screenshot("02-moved")
        s.key("Return")
        check("quit", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        elements = load_elements(entries[-1]) if entries else []
        kinds = {e.tool.name: e for e in elements if hasattr(e, "tool")}
        if check(f"history: rectangle, ellipse, arrow ({sorted(kinds)})",
                 sorted(kinds) == ["ARROW", "ELLIPSE", "RECT"]):
            arrow, rect, oval = kinds["ARROW"], kinds["RECT"], kinds["ELLIPSE"]
            start = arrow.mapToScene(arrow.points[0])
            check("the arrow is docked to both", arrow.ends == [rect.id, oval.id])
            check(f"it followed the rectangle down ({start.y():.0f})", start.y() > 450)
            check("the arrow carries the text 'SQL'",
                  arrow.label is not None and arrow.label.toPlainText() == "SQL")
    return summary()


if __name__ == "__main__":
    sys.exit(main())
