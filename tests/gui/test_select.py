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
        check("Overlay gestartet", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
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
        check("beendet", wait(lambda: not s.slate_pids(), 10))
        entries = s.history_entries()
        remaining = load_elements(entries[0]) if entries else []
        check(f"übrig bleibt nur das dritte Rechteck ({len(remaining)})",
              len(remaining) == 1 and remaining[0].pos().x() > 1000)

        # Vorder-/Hintergrund: zwei überlappende Marker, den unteren ganz nach vorne holen
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("c")
        for x in (600, 625):
            s.move(x, 600)
            s.run(["xdotool", "click", "1"])
        s.key("w")
        s.move(585, 600)                         # linker Rand: nur der erste Marker
        s.run(["xdotool", "click", "1"])
        s.key("ctrl+shift+Up")
        time.sleep(0.3)
        s.screenshot("04-marker-vorne")
        s.key("Return")
        wait(lambda: not s.slate_pids(), 10)
        entries = s.history_entries()
        markers = [e for e in load_elements(entries[-1])] if entries else []
        check("Strg+Shift+↑: der erste Marker liegt jetzt oben",
              len(markers) == 2 and markers[-1].points[1].x() + markers[-1].pos().x() < 610)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
