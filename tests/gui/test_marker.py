#!/usr/bin/env python3
"""GUI-Test Marker: c, Klick = Kreis, Ziehen = Kreis mit Zeigelinie, zweites c = Buchstaben,
Verlaufseintrag enthält die Marker.

    python tests/gui/test_marker.py

Bildschirmfotos: tests/gui/out/marker/ (ansehen!). Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("marker") as s:
        s.key("alt+Escape")
        check("Overlay gestartet", wait(lambda: s.annotate_pids(), 10))
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("c")
        s.move(300, 300)
        s.run(["xdotool", "click", "1"])          # 1: nur Kreis
        s.drag(500, 400, 620, 300)                # 2: Spitze bei (500, 400), Kreis bei (620, 300)
        s.move(800, 300)
        s.run(["xdotool", "click", "1"])          # 3
        s.key("c")                                # Buchstaben
        s.move(1000, 300)
        s.run(["xdotool", "click", "1"])          # A
        time.sleep(0.4)
        s.screenshot("01-marker")
        s.key("Return")
        check("beendet", wait(lambda: not s.annotate_pids(), 10))
        entries = s.history_entries()
        markers = [e for e in load_elements(entries[0]) if e.tool.name == "MARKER"] if entries else []
        check("vier Marker gespeichert, drei Zahlen und ein Buchstabe",
              sorted(e.marker_kind for e in markers) == ["letter", "number", "number", "number"])
        with_line = [e for e in markers if e.points[0] != e.points[1]]
        check("genau einer mit Zeigelinie", len(with_line) == 1)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
