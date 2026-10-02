#!/usr/bin/env python3
"""GUI-Test Ausschnitt: y, Rahmen aufziehen, nochmal y und an der Ecke ziehen (anpassen),
Enter -> Zwischenablage enthält nur den Ausschnitt; Verlaufseintrag zeigt den Ausschnitt
und enthält den ganzen Screenshot.

    python tests/gui/test_crop.py

Bildschirmfotos: tests/gui/out/crop/ (ansehen!). Rückgabewert 0 = alles ok.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, _qt_image, check, load_drawing, summary, wait  # noqa: E402


def main():
    with Session("crop") as s:
        s.start_keysink()  # weißes Fenster: Abdunklung außerhalb gut sichtbar und messbar
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.key("alt+Escape")
        check("Overlay gestartet", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(500, 300, 700, 450)        # Rechteck im späteren Ausschnitt
        s.key("y")
        s.drag(400, 200, 1000, 600)       # Ausschnitt 600 x 400
        time.sleep(0.3)
        shot = _qt_image(s.screenshot("01-ausschnitt"))
        check("außerhalb abgedunkelt, innen hell",
              shot.pixelColor(200, 100).lightness() < 200 and shot.pixelColor(900, 550).lightness() > 240)
        # Nachträglich anpassen: y zeigt Griffe, Ecke unten rechts ziehen -> 700 x 450
        s.key("y")
        s.move(700, 400)
        time.sleep(0.3)
        s.screenshot("02-griffe")
        s.drag(1000, 600, 1100, 650)
        time.sleep(0.3)
        s.screenshot("03-angepasst")
        s.key("Return")
        check("beendet", wait(lambda: not s.slate_pids(), 10))
        png = s.tmp / "clip.png"
        with open(png, "wb") as f:
            subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                           env=s.env, stdout=f, timeout=5)
        clip = _qt_image(png)
        check(f"Zwischenablage: nur der angepasste Ausschnitt ({clip.width()} x {clip.height()})",
              (clip.width(), clip.height()) == (700, 450))
        entries = s.history_entries()
        if check("Verlaufseintrag vorhanden", len(entries) == 1):
            shown = _qt_image(entries[0])
            background, elements = load_drawing(entries[0])
            check("Verlauf: Bild = Ausschnitt, eingebettet der ganze Screenshot",
                  (shown.width(), shown.height()) == (700, 450) and background.width() == 1920)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
