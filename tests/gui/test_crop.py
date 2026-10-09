#!/usr/bin/env python3
"""GUI test crop: x, draw a frame, x again and drag the corner (adjust), then with the
select tool: click the edge, drag the corner twice (adjust repeatedly),
Enter -> the clipboard contains only the crop; the history entry shows the crop
and contains the whole screenshot.

    python tests/gui/test_crop.py

Screenshots: tests/gui/out/crop/ (look at them!). Exit code 0 = all ok.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, _qt_image, check, load_drawing, summary, wait  # noqa: E402


def main():
    with Session("crop") as s:
        s.start_keysink()  # white window: darkening outside easy to see and measure
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(500, 300, 700, 450)        # rectangle inside the later crop
        s.key("x")
        s.drag(400, 200, 1000, 600)       # crop 600 x 400
        time.sleep(0.3)
        shot = _qt_image(s.screenshot("01-crop"))
        check("darkened outside, light inside",
              shot.pixelColor(200, 100).lightness() < 200 and shot.pixelColor(900, 550).lightness() > 240)
        # Adjust afterwards: x shows handles, drag the bottom right corner -> 700 x 450
        s.key("x")
        s.move(700, 400)
        time.sleep(0.3)
        s.screenshot("02-handles")
        s.drag(1000, 600, 1100, 650)
        time.sleep(0.3)
        s.screenshot("03-adjusted")
        # Select tool: click the edge -> handles; drag the corner twice -> 750 x 480
        s.key("w")
        s.move(400, 400)
        s.run(["xdotool", "click", "1"])
        time.sleep(0.3)
        s.screenshot("04-selected")
        s.drag(1100, 650, 1130, 665)
        s.drag(1130, 665, 1150, 680)
        time.sleep(0.3)
        s.screenshot("05-adjusted-again")
        s.key("Return")
        check("quit", wait(lambda: not s.slate_pids(), 10))
        png = s.tmp / "clip.png"
        with open(png, "wb") as f:
            subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                           env=s.env, stdout=f, timeout=5)
        clip = _qt_image(png)
        check(f"clipboard: only the adjusted crop ({clip.width()} x {clip.height()})",
              (clip.width(), clip.height()) == (750, 480))
        entries = s.history_entries()
        if check("history entry exists", len(entries) == 1):
            shown = _qt_image(entries[0])
            background, elements = load_drawing(entries[0])
            check("history: image = crop, the whole screenshot embedded",
                  (shown.width(), shown.height()) == (750, 480) and background.width() == 1920)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
