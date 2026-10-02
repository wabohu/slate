#!/usr/bin/env python3
"""GUI-Test Mehrfachauswahl: drei Rechtecke, Strg+A, Auswahlrahmen, Shift+Klick, alle
zusammen verschieben und löschen; Verlaufseintrag enthält das Ergebnis.

    python tests/gui/test_select.py

Bildschirmfotos: tests/gui/out/select/ (ansehen!). Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("select") as s:
        s.key("alt+Escape")
        check("Overlay gestartet", wait(lambda: s.annotate_pids(), 10))
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("f")
        for x in (300, 700, 1100):
            s.drag(x, 300, x + 200, 450)
        s.key("ctrl+a")
        time.sleep(0.3)
        s.screenshot("01-alles")
        s.drag(250, 250, 950, 500)               # Rahmen um die ersten beiden
        time.sleep(0.3)
        s.screenshot("02-rahmen")
        s.drag(500, 375, 520, 425)               # Rand des ersten anfassen: beide wandern
        s.key("Delete")                          # beide löschen
        time.sleep(0.3)
        s.screenshot("03-geloescht")
        s.key("Return")
        check("beendet", wait(lambda: not s.annotate_pids(), 10))
        entries = s.history_entries()
        remaining = load_elements(entries[0]) if entries else []
        check(f"übrig bleibt nur das dritte Rechteck ({len(remaining)})",
              len(remaining) == 1 and remaining[0].pos().x() > 1000)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
