#!/usr/bin/env python3
"""GUI-Test Kopieren zwischen Fenstern: im Screenshot Elemente auswählen, Strg+C, beenden;
im Whiteboard Strg+V an der Maus, Strg+D verdoppelt; gespeichertes Whiteboard prüfen.
Dazu: Ausschnitt mit Marker per Enter ins Whiteboard (Bild + bearbeitbarer Marker) und ein
fremdes Bild aus der Zwischenablage.

    python tests/gui/test_clipboard.py

Bildschirmfotos: tests/gui/out/clipboard/ (ansehen!). Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Session, check, load_drawing, summary, wait  # noqa: E402


def main():
    with Session("clipboard") as s:
        s.key("alt+Escape")
        check("Overlay gestartet", wait(lambda: s.slate_pids(), 10))
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("f")
        s.drag(300, 300, 500, 450)
        s.key("c")
        s.move(700, 400)
        s.run(["xdotool", "click", "1"])
        s.key("ctrl+a")
        s.key("ctrl+c")
        s.key("Escape")          # Auswahl aufheben
        s.key("Escape")          # beenden; die Zwischenablage hält xclip
        check("Screenshot beendet", wait(lambda: not s.slate_pids(), 10))

        s.key("alt+Delete")
        check("Whiteboard gestartet", wait(lambda: s.slate_pids(), 10))
        pid = s.slate_pids()[0]
        wait(lambda: s.windows_of(pid), 10)
        time.sleep(0.6)
        s.move(900, 500)
        s.key("ctrl+v")
        time.sleep(0.4)
        s.key("ctrl+d")          # eingefügte Auswahl verdoppeln
        time.sleep(0.4)
        s.screenshot("01-eingefuegt")
        s.key("ctrl+s")
        saved = []
        wait(lambda: saved.extend(sorted((s.tmp / "output").glob("*_board.png"))) or saved, 5)
        if check("Whiteboard gespeichert", bool(saved)):
            _, elements = load_drawing(saved[0])
            tools = sorted(e.tool.name for e in elements)
            check(f"eingefügt und verdoppelt: 2 Rechtecke, 2 Marker ({tools})",
                  tools == ["MARKER", "MARKER", "RECT", "RECT"])
            labels = []
            for e in elements:
                if e.tool.name == "MARKER":
                    labels.append(e.marker_order)
            check("Marker zählen im Whiteboard weiter (verschiedene Reihenfolge)", len(set(labels)) == 2)
        s.key("ctrl+q")
        wait(lambda: not s.slate_pids(), 5)

    # Ausschnitt mit Markern ins Whiteboard: Marker setzen, y, Enter; im Whiteboard Strg+V
    # -> Bild-Element mit dem Screenshot-Teil, der Marker bleibt eigenes Element.
    # Danach ein fremdes Bild (wie aus dem Browser) einfügen.
    with Session("clipboard-ausschnitt") as s:
        s.start_keysink()  # heller Inhalt im Screenshot
        wait(lambda: s.focus_id() == s.window_named("keysink"))
        s.type("Hallo Klasse")
        s.key("alt+Escape")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.4)
        s.key("c")
        s.move(400, 500)
        s.run(["xdotool", "click", "1"])
        s.key("y")
        s.drag(100, 400, 700, 650)          # Ausschnitt um Text und Marker
        s.key("Return")
        check("Screenshot kopiert und beendet", wait(lambda: not s.slate_pids(), 10))
        s.key("alt+Delete")
        wait(lambda: s.slate_pids(), 10)
        wait(lambda: s.windows_of(s.slate_pids()[0]), 10)
        time.sleep(0.6)
        # Das Testfenster teilt sich den Bildschirm mit dem Whiteboard (gekachelt, obere Hälfte);
        # Fokus folgt der Maus, darum die Maus ins Whiteboard (untere Hälfte)
        s.move(700, 800)
        time.sleep(0.3)
        s.key("ctrl+v")
        time.sleep(0.4)
        foreign = s.tmp / "fremd.png"
        s.run(["convert", "-size", "160x90", "xc:orange", str(foreign)])
        # xclip bleibt im Hintergrund und hält die Zwischenablage: Ausgaben nicht an uns binden
        s.run(["sh", "-c", f"xclip -selection clipboard -t image/png -i < {foreign} >/dev/null 2>&1"])
        time.sleep(0.3)
        s.move(1400, 900)
        s.key("ctrl+v")
        time.sleep(0.4)
        s.screenshot("02-ausschnitt-im-whiteboard")
        s.key("ctrl+s")
        saved = []
        wait(lambda: saved.extend(sorted((s.tmp / "output").glob("*_board*.png"))) or saved, 5)
        if check("Whiteboard gespeichert", bool(saved)):
            _, elements = load_drawing(saved[0])
            kinds = [type(e).__name__ + (":" + e.tool.name if hasattr(e, "tool") else "") for e in elements]
            check(f"Ausschnitt als Bild, Marker bearbeitbar, fremdes Bild ({kinds})",
                  kinds == ["ImageElement", "ShapeElement:MARKER", "ImageElement"]
                  and elements[0].size.toTuple() == (600.0, 250.0)
                  and elements[2].size.toTuple() == (160.0, 90.0))
        s.key("ctrl+q")
        wait(lambda: not s.slate_pids(), 5)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
