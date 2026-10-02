#!/usr/bin/env python3
"""GUI test blur: text in the test window, screenshot, z, drag an area -> pixelated;
the history entry contains only the pixelated version, also in the embedded raw image.

    python tests/gui/test_blur.py

Screenshots: tests/gui/out/blur/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_drawing, summary, wait  # noqa: E402

TEXT = "password secret123 " * 4


def contrast(image, y, x0, x1):
    """Lightness range of an image row: text = large, pixelated = small."""
    values = [image.pixelColor(x, y).lightness() for x in range(x0, x1)]
    return max(values) - min(values)


def main():
    with Session("blur") as s:
        s.start_keysink()
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.type(TEXT)
        time.sleep(0.3)
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        # Find the row with the text (the input field fills the window, the text is centered)
        before = s.screenshot("00-before")
        from harness import _qt_image
        img = _qt_image(before)
        row = next((y for y in range(img.height()) if contrast(img, y, 10, 300) > 150), None)
        if not check("text found in the screenshot", row is not None):
            return summary()  # without text the other checks would say nothing

        s.key("z")
        s.drag(4, max(0, row - 15), 330, row + 15)
        time.sleep(0.4)
        after = _qt_image(s.screenshot("01-pixelated"))
        check("area pixelated (text no longer high-contrast)", contrast(after, row, 10, 300) < 120)

        s.key("Return")  # copy and quit -> history gets saved
        check("quit", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        check("history entry exists", len(entries) == 1)
        if entries:
            background, elements = load_drawing(entries[0])
            check("history: blur element saved", [e.tool.name for e in elements] == ["BLUR"])
            check("history: the embedded raw image is pixelated there too",
                  contrast(background, row, 10, 300) < 120)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
