#!/usr/bin/env python3
"""GUI-Test Unschärfe: Text im Testfenster, Screenshot, z, Bereich aufziehen -> verpixelt;
der Verlaufseintrag enthält auch im eingebetteten Rohbild nur die verpixelte Fassung.

    python tests/gui/test_blur.py

Bildschirmfotos: tests/gui/out/blur/ (ansehen!). Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_drawing, summary, wait  # noqa: E402

TEXT = "Passwort geheim123 " * 4


def contrast(image, y, x0, x1):
    """Helligkeitsspanne einer Bildzeile: Text = groß, verpixelt = klein."""
    values = [image.pixelColor(x, y).lightness() for x in range(x0, x1)]
    return max(values) - min(values)


def main():
    with Session("blur") as s:
        s.start_keysink()
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.type(TEXT)
        time.sleep(0.3)
        s.key("alt+Escape")
        check("Overlay gestartet", wait(lambda: s.annotate_pids(), 10))
        pid = s.annotate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.4)
        # Zeile mit dem Text finden (das Eingabefeld füllt das Fenster, Text steht mittig)
        before = s.screenshot("00-vorher")
        from harness import _qt_image
        img = _qt_image(before)
        row = next((y for y in range(img.height()) if contrast(img, y, 10, 300) > 150), None)
        if not check("Text im Screenshot gefunden", row is not None):
            return summary()  # ohne Text wären die übrigen Prüfungen ohne Aussage

        s.key("z")
        s.drag(4, max(0, row - 15), 330, row + 15)
        time.sleep(0.4)
        after = _qt_image(s.screenshot("01-verpixelt"))
        check("Bereich verpixelt (Text nicht mehr kontrastreich)", contrast(after, row, 10, 300) < 120)

        s.key("Return")  # kopieren und beenden -> Verlauf wird gespeichert
        check("beendet", wait(lambda: not s.annotate_pids(), 10))
        entries = s.history_entries()
        check("Verlaufseintrag vorhanden", len(entries) == 1)
        if entries:
            background, elements = load_drawing(entries[0])
            check("Verlauf: Unschärfe-Element gespeichert", [e.tool.name for e in elements] == ["BLUR"])
            check("Verlauf: auch das eingebettete Rohbild ist dort verpixelt",
                  contrast(background, row, 10, 300) < 120)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
