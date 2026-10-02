#!/usr/bin/env python3
"""GUI test whiteboard: start via hotkey, Esc/Enter do not close, Ctrl+B (light),
Ctrl+Q with rofi prompt (Cancel, Save), open again, Discard.

    python tests/gui/test_board.py

Runs in a separate invisible X server (harness.py), your session stays
untouched. Screenshots: tests/gui/out/board/. Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import SLATE, Session, check, load_drawing, summary, wait  # noqa: E402

PAPER = "#f8f6f0"         # light background from DEFAULT_BOARD_BACKGROUNDS
EMPTY = (960, 120)        # screen point where nothing is drawn


def board_window(s):
    """(PID, window) of the running whiteboard or (None, None)."""
    for pid in s.slate_pids():
        wins = s.windows_of(pid)
        if wins:
            return pid, wins[0]
    return None, None


def ask_rofi(s, text):
    """Wait until the rofi prompt is open, type text, Enter."""
    if not check(f"rofi prompt appears (for '{text}')", wait(lambda: s.rofi_open(), 5)):
        return
    time.sleep(0.2)
    s.type(text)
    s.key("Return")
    wait(lambda: not s.rofi_open(), 5)


def main():
    with Session("board") as s:
        # Start via hotkey, normal window managed by herbstluftwm
        s.key("alt+Delete")
        check("start via hotkey: whiteboard window there", wait(lambda: board_window(s)[1], 10))
        pid, win = board_window(s)
        check("whiteboard has the focus", wait(lambda: s.focus_id() == win))
        check("title: new", "Whiteboard – new" in (s.window_name(win) or ""))
        dark = s.pixel(*EMPTY, name="01-started")

        s.key("f")
        s.drag(500, 400, 900, 700)
        s.key("Escape")
        s.key("Return")
        time.sleep(0.5)
        check("Esc and Enter do not close the whiteboard", pid in s.slate_pids())

        # Ctrl+B: light background
        s.key("ctrl+b")
        check("Ctrl+B: background light", wait(lambda: s.pixel(*EMPTY, name="02-light") == PAPER, 3))
        check("it was dark before", dark != PAPER)

        # Ctrl+Q, unsaved: rofi asks. "can" = Cancel, the window stays
        s.key("ctrl+q")
        time.sleep(0.3)
        s.screenshot("03-rofi")
        ask_rofi(s, "can")
        time.sleep(0.5)
        check("rofi 'can' (Cancel): whiteboard stays open", pid in s.slate_pids())

        # Ctrl+Q, "sa" = Save: file created, window closed
        s.key("ctrl+q")
        ask_rofi(s, "sa")
        check("rofi 'sa' (Save): whiteboard closed", wait(lambda: pid not in s.slate_pids(), 5))
        saved = sorted((s.tmp / "output").glob("*_board.png"))
        check("saved as …_board.png", len(saved) == 1)
        if not saved:
            return summary()
        background, elements = load_drawing(saved[0])
        check("saved: light background, one rectangle",
              hasattr(background, "name") and background.name() == PAPER
              and [e.tool.name for e in elements] == ["RECT"])

        # Open again (like python slate.py file.png): as whiteboard, light, title = file
        s.spawn([str(SLATE), str(saved[0])], log="reopen")
        check("opened again", wait(lambda: board_window(s)[1], 10))
        pid, win = board_window(s)
        check("title names the file", saved[0].name in (s.window_name(win) or ""))
        check("opened again: background light", wait(lambda: s.pixel(*EMPTY, name="04-reopened") == PAPER, 3))

        # Without changes: Ctrl+Q closes without asking
        s.key("ctrl+q")
        time.sleep(0.5)
        check("unchanged: Ctrl+Q without prompt", not s.rofi_open())
        check("unchanged: closed", wait(lambda: pid not in s.slate_pids(), 5))

        # Change and discard: the file stays as saved
        s.spawn([str(SLATE), str(saved[0])], log="reopen2")
        wait(lambda: board_window(s)[1], 10)
        pid, win = board_window(s)
        wait(lambda: s.focus_id() == win)
        s.key("g")
        s.drag(1100, 400, 1400, 700)
        s.key("ctrl+q")
        ask_rofi(s, "di")
        check("rofi 'di' (Discard): closed", wait(lambda: pid not in s.slate_pids(), 5))
        _, elements = load_drawing(saved[0])
        check("discarded: file unchanged (only the rectangle)", [e.tool.name for e in elements] == ["RECT"])
    return summary()


if __name__ == "__main__":
    sys.exit(main())
