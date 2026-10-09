#!/usr/bin/env python3
"""GUI test copying between windows: select elements in the screenshot, Ctrl+C, quit;
in the whiteboard Ctrl+V at the mouse, Ctrl+D duplicates; check the saved whiteboard.
Also: crop with a marker via Enter into the whiteboard (image + editable marker) and a
foreign image from the clipboard.

    python tests/gui/test_clipboard.py

Screenshots: tests/gui/out/clipboard/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_drawing, summary, wait  # noqa: E402


def main():
    with Session("clipboard") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(300, 300, 500, 450)
        s.key("c")
        s.move(700, 400)
        s.run(["xdotool", "click", "1"])
        s.key("ctrl+a")
        s.key("ctrl+c")
        s.key("Escape")          # deselect
        s.key("Escape")          # quit; xclip holds the clipboard
        check("screenshot quit", wait(lambda: not s.slate_pids(), 10))

        s.key("alt+Delete")
        check("whiteboard started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.6)
        s.move(900, 500)
        s.key("ctrl+v")
        time.sleep(0.4)
        s.key("ctrl+d")          # duplicate the pasted selection
        time.sleep(0.4)
        s.screenshot("01-pasted")
        s.key("ctrl+s")
        saved = []
        wait(lambda: saved.extend(sorted((s.tmp / "output").glob("*_board.png"))) or saved, 5)
        if check("whiteboard saved", bool(saved)):
            _, elements = load_drawing(saved[0])
            tools = sorted(e.tool.name for e in elements)
            check(f"pasted and duplicated: 2 rectangles, 2 markers ({tools})",
                  tools == ["MARKER", "MARKER", "RECT", "RECT"])
            labels = []
            for e in elements:
                if e.tool.name == "MARKER":
                    labels.append(e.marker_order)
            check("markers count on in the whiteboard (different order)", len(set(labels)) == 2)
        s.key("ctrl+q")
        wait(lambda: not s.slate_pids(), 5)

    # Crop with markers into the whiteboard: set a marker, y, Enter; in the whiteboard Ctrl+V
    # -> image element with the screenshot part, the marker stays a separate element.
    # Then paste a foreign image (as if from the browser).
    with Session("clipboard-crop") as s:
        s.start_keysink()  # light content in the screenshot
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.type("Hello class")
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("c")
        s.move(400, 500)
        s.run(["xdotool", "click", "1"])
        s.key("x")
        s.drag(100, 400, 700, 650)          # crop around text and marker
        s.key("Return")
        check("screenshot copied and quit", wait(lambda: not s.slate_pids(), 10))
        s.key("alt+Delete")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.6)
        # The test window shares the screen with the whiteboard (tiled, upper half);
        # focus follows the mouse, so move the mouse into the whiteboard (lower half)
        s.move(700, 800)
        time.sleep(0.3)
        s.key("ctrl+v")
        time.sleep(0.4)
        foreign = s.tmp / "foreign.png"
        s.run(["convert", "-size", "160x90", "xc:orange", str(foreign)])
        # xclip stays in the background and holds the clipboard: do not bind its output to us
        s.run(["sh", "-c", f"xclip -selection clipboard -t image/png -i < {foreign} >/dev/null 2>&1"])
        time.sleep(0.3)
        s.move(1400, 900)
        s.key("ctrl+v")
        time.sleep(0.4)
        s.screenshot("02-crop-in-whiteboard")
        s.key("ctrl+s")
        saved = []
        wait(lambda: saved.extend(sorted((s.tmp / "output").glob("*_board*.png"))) or saved, 5)
        if check("whiteboard saved", bool(saved)):
            _, elements = load_drawing(saved[0])
            kinds = [type(e).__name__ + (":" + e.tool.name if hasattr(e, "tool") else "") for e in elements]
            check(f"crop as image, marker editable, foreign image ({kinds})",
                  kinds == ["ImageElement", "ShapeElement:MARKER", "ImageElement"]
                  and elements[0].size.toTuple() == (600.0, 250.0)
                  and elements[2].size.toTuple() == (160.0, 90.0))
        s.key("ctrl+q")
        wait(lambda: not s.slate_pids(), 5)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
