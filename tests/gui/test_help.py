#!/usr/bin/env python3
"""GUI test key overview: ? opens it (F1 does not), any key only closes it (Esc then does
not quit the tool), a click closes it; in screenshot mode and in the whiteboard.

    python tests/gui/test_help.py

Screenshots: tests/gui/out/help/ (look at the overview!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, summary, wait  # noqa: E402

CENTER = (960, 540)  # the panel lies here when it is open


def main():
    with Session("help") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.5)
        closed = s.pixel(*CENTER, name="00-closed")

        s.key("F1")
        time.sleep(0.4)
        check("F1 opens nothing", s.pixel(*CENTER) == closed)
        s.key("question")
        check("? opens the overview", wait(lambda: s.pixel(*CENTER, name="01-open") != closed, 3))
        s.key("Escape")
        time.sleep(0.4)
        check("Esc only closes the overview", s.pixel(*CENTER) == closed and pid in s.slate_pids())

        s.key("question")  # ? = Shift+/ on the US layout
        check("? opens it again", wait(lambda: s.pixel(*CENTER) != closed, 3))
        s.move(50, 50)
        s.run(["xdotool", "click", "1"])  # click next to the panel
        time.sleep(0.4)
        check("click closes the overview", s.pixel(*CENTER) == closed and pid in s.slate_pids())

        # Bar: off at first in screenshot mode, b shows it and hides it again
        # (pixel in the middle of the bar at the bottom)
        empty = s.pixel(960, 1037, name="03-without-bar")
        s.key("b")
        check("screenshot: bar off at first, b shows it",
              wait(lambda: s.pixel(960, 1037, name="04-with-bar") != empty, 3))
        s.key("b")
        check("b hides it again", wait(lambda: s.pixel(960, 1037) == empty, 3))

        s.key("Escape")
        check("afterwards Esc quits the tool", wait(lambda: not s.slate_pids(), 5))

        # Whiteboard: own entries (view, background), no history
        s.key("alt+Delete")
        check("whiteboard started", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.5)
        # Check a whole row: a single point may happen to lie on a color field in the
        # background color
        from harness import _qt_image
        shot = _qt_image(s.screenshot("05-whiteboard-start"))
        background = shot.pixelColor(960, 900)
        differing = sum(shot.pixelColor(x, 1027) != background for x in range(300, 1620, 4))
        check("whiteboard: bar visible from the start", differing > 100)
        s.key("question")
        time.sleep(0.4)
        s.screenshot("02-whiteboard")
        s.key("Escape")
        time.sleep(0.3)
        check("whiteboard: Esc only closes the overview", pid in s.slate_pids())
        s.key("ctrl+q")
        check("whiteboard quit", wait(lambda: not s.slate_pids(), 5))

    # 4K: the panel scales along (look at the screenshot: appears as large as at 1080p)
    with Session("help-4k", size="3840x2160") as s:
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.5)
        closed = s.pixel(1920, 1080, name="00-closed")
        s.key("question")
        check("4K: overview open", wait(lambda: s.pixel(1920, 1080, name="01-open") != closed, 3))
        s.key("Escape")
        s.key("Escape")
        check("4K: quit", wait(lambda: not s.slate_pids(), 5))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
