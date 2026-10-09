#!/usr/bin/env python3
"""GUI test connectors. Screenshot mode: an arrow drawn from the edge of a rectangle to the
edge of an ellipse stays free (no docking on screenshots). Whiteboard: the same arrow docks to
both (the target is highlighted while drawing); a double click on the arrow gives it a text;
moving the rectangle moves the arrow along; the saved file contains the docked arrow with its text.

    python tests/gui/test_connector.py

Screenshots: tests/gui/out/connector/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_drawing, load_elements, summary, wait  # noqa: E402


def draw_scene(s):
    """Rectangle (middle 450, 400), ellipse (middle 1250, 400), an arrow from the rectangle's
    right edge to the ellipse's left edge; screenshot 01 while the mouse is still pressed."""
    s.key("f")
    s.drag(300, 300, 600, 500)
    s.key("g")
    s.drag(1100, 300, 1400, 500)
    s.key("d")
    s.run(["xdotool", "mousemove", "605", "400", "mousedown", "1",
           "mousemove", "850", "400", "mousemove", "1095", "405"])
    time.sleep(0.3)
    s.screenshot("01-docking-hint")
    s.run(["xdotool", "mouseup", "1"])
    time.sleep(0.2)


def shapes(elements):
    """{tool name: element} of the shapes among elements."""
    return {e.tool.name: e for e in elements if hasattr(e, "tool")}


def main():
    # Screenshot mode: nothing docks
    with Session("connector") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        draw_scene(s)
        s.key("Return")
        check("quit", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        kinds = shapes(load_elements(entries[-1]) if entries else [])
        check(f"screenshot: the arrow stays free ({sorted(kinds)})",
              "ARROW" in kinds and kinds["ARROW"].ends == [None, None])

    # Whiteboard: docks, follows, carries a text
    with Session("connector-board") as s:
        s.key("alt+Delete")
        check("whiteboard started", wait(lambda: s.slate_pids() and s.windows_of(s.slate_pids()[0]), 10))
        time.sleep(0.4)
        draw_scene(s)
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
        s.key("ctrl+s")
        saved = []
        wait(lambda: saved.extend(sorted((s.tmp / "output").glob("*_board.png"))) or saved, 5)
        kinds = shapes(load_drawing(saved[0])[1] if saved else [])
        if check(f"saved: rectangle, ellipse, arrow ({sorted(kinds)})",
                 sorted(kinds) == ["ARROW", "ELLIPSE", "RECT"]):
            arrow, rect, oval = kinds["ARROW"], kinds["RECT"], kinds["ELLIPSE"]
            start = arrow.mapToScene(arrow.points[0])
            middle = rect.sceneBoundingRect().center()
            check("the arrow is docked to both", arrow.ends == [rect.id, oval.id])
            check(f"it followed the rectangle down (start {start.y():.0f}, rectangle {middle.y():.0f})",
                  abs(start.y() - middle.y()) < 60)
            check("the arrow carries the text 'SQL'",
                  arrow.label is not None and arrow.label.toPlainText() == "SQL")
        s.key("ctrl+q")
        check("quit", wait(lambda: not s.slate_pids(), 10))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
