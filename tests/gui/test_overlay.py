#!/usr/bin/env python3
"""GUI test screenshot overlay: start via hotkey, focus, sxhkd hotkeys, drawing,
focus back after Esc, history entry.

    python tests/gui/test_overlay.py

Runs in a separate invisible X server (harness.py), your session stays
untouched. Screenshots: tests/gui/out/overlay/. Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import SLATE, Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("overlay") as s:
        empty = s.run([str(SLATE), "--last"])
        check("--last with empty history: exit code 1, no window", empty.returncode == 1 and not s.slate_pids())
        sink_out = s.start_keysink()
        sink = s.window_named("keysink")
        check("initial state: test window has the focus", wait(lambda: s.focus_id() == sink))
        s.type("a")
        check("initial state: keys arrive in the test window", wait(lambda: sink_out.read_text() == "a"))

        # Start via hotkey (sxhkd -> slate.py)
        s.key("alt+Escape")
        check("start via hotkey: slate running", wait(lambda: s.slate_pids(), 10))
        pid = (s.slate_pids() or [0])[0]
        check("start via hotkey: overlay visible", wait(lambda: s.windows_of(pid), 10))
        overlay = s.windows_of(pid)
        check("overlay has the focus right away", wait(lambda: s.focus_id() in overlay))
        s.screenshot("01-started")

        # Draw: rectangle (key F), the mouse stays over the overlay afterwards
        s.key("f")
        s.drag(500, 300, 900, 600)
        time.sleep(0.3)
        s.screenshot("02-rectangle")

        # sxhkd hotkeys arrive although the overlay is open
        s.key("super+k")
        check("hotkey run while the overlay is open",
              wait(lambda: (s.tmp / "hotkey-fired").exists()))

        # A hotkey puts the focus on another window, the mouse is over the overlay:
        # the overlay takes it back, keys work without a click
        s.key("super+j")
        time.sleep(0.5)
        check("focus back at the overlay after a hotkey without a click", wait(lambda: s.focus_id() in overlay, 2))
        s.key("g")  # ellipse: only works if the key arrives at the overlay
        s.drag(1000, 300, 1300, 600)
        time.sleep(0.3)
        s.screenshot("03-ellipse-after-hotkey")
        check("test window got nothing", sink_out.read_text() == "a")

        # Esc: quit, focus back to the test window
        s.key("Escape")
        check("Esc quits the overlay", wait(lambda: not s.slate_pids(), 10))
        check("focus back at the test window after Esc", wait(lambda: s.focus_id() == sink))
        s.type("b")
        check("keys arrive in the test window again afterwards", wait(lambda: sink_out.read_text() == "ab"))
        s.screenshot("04-after-esc")

        # History: one entry with rectangle and ellipse
        entries = s.history_entries()
        check("history: one entry", len(entries) == 1)
        tools = sorted(e.tool.name for e in load_elements(entries[0])) if entries else []
        check(f"history: rectangle and ellipse saved ({', '.join(tools)})", tools == ["ELLIPSE", "RECT"])

        # --last opens the newest history entry (e.g. via a hotkey)
        s.spawn([str(SLATE), "--last"], log="last")
        check("--last opens the latest screenshot", wait(lambda: s.slate_pids(), 10))
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.screenshot("05-last")
        s.key("Escape")
        check("--last: Esc quits", wait(lambda: not s.slate_pids(), 5))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
