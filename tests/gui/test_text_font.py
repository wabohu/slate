#!/usr/bin/env python3
"""GUI test monospace text (Alt+V): a normal text, Alt+V, a monospace text, then a third text
that starts monospace and is switched back while typing (Alt+V types no "v"); the history
entry contains the font kinds.

    python tests/gui/test_text_font.py

Screenshots: tests/gui/out/text-font/ (look at them!). Exit code 0 = all ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_elements, summary, wait  # noqa: E402


def write(s, x, y, text):
    """Click with the text tool at (x, y) and type text (input stays open)."""
    s.move(x, y)
    s.run(["xdotool", "click", "1"])
    time.sleep(0.2)
    s.type(text)


def main():
    with Session("text-font") as s:
        s.key("alt+Escape")
        check("overlay started", wait(lambda: s.slate_pids(), 10))
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("t")
        write(s, 300, 300, "normal text")
        s.key("Escape")
        s.key("alt+v")                           # next text: monospace
        write(s, 300, 450, "ls -la /tmp")
        s.key("Escape")
        write(s, 300, 600, "mono")               # starts monospace ...
        s.key("alt+v")                           # ... and goes back to normal while typing
        s.type(" then normal")
        time.sleep(0.2)
        s.screenshot("01-texts")
        s.key("Escape")
        s.key("Return")
        check("quit", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        texts = sorted((e for e in load_elements(entries[-1]) if hasattr(e, "font_kind")),
                       key=lambda e: e.pos().y()) if entries else []
        found = [(t.toPlainText(), t.font_kind) for t in texts]
        check(f"history: font kinds saved ({found})",
              found == [("normal text", "normal"), ("ls -la /tmp", "mono"), ("mono then normal", "normal")])
    return summary()


if __name__ == "__main__":
    sys.exit(main())
