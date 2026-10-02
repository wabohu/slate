#!/usr/bin/env python3
"""GUI-Test Screenshot-Overlay: Start per Hotkey, Fokus, sxhkd-Hotkeys, Zeichnen,
Fokus zurück nach Esc, Verlaufseintrag.

    python tests/gui/test_overlay.py

Läuft in einem eigenen unsichtbaren X-Server (harness.py), deine Sitzung bleibt
unberührt. Bildschirmfotos: tests/gui/out/overlay/. Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ANNOTATE, Session, check, load_elements, summary, wait  # noqa: E402


def main():
    with Session("overlay") as s:
        empty = s.run([str(ANNOTATE), "--last"])
        check("--last bei leerem Verlauf: Fehlercode 1, kein Fenster", empty.returncode == 1 and not s.annotate_pids())
        sink_out = s.start_keysink()
        sink = s.window_named("keysink")
        check("Ausgangslage: Testfenster hat den Fokus", wait(lambda: s.focus_id() == sink))
        s.type("a")
        check("Ausgangslage: Tasten kommen im Testfenster an", wait(lambda: sink_out.read_text() == "a"))

        # Start per Hotkey (sxhkd -> annotate.py)
        s.key("alt+Escape")
        check("Start per Hotkey: annotate läuft", wait(lambda: s.annotate_pids(), 10))
        pid = (s.annotate_pids() or [0])[0]
        check("Start per Hotkey: Overlay sichtbar", wait(lambda: s.windows_of(pid), 10))
        overlay = s.windows_of(pid)
        check("Overlay hat sofort den Fokus", wait(lambda: s.focus_id() in overlay))
        s.screenshot("01-gestartet")

        # Zeichnen: Rechteck (Taste F), Maus bleibt danach über dem Overlay
        s.key("f")
        s.drag(500, 300, 900, 600)
        time.sleep(0.3)
        s.screenshot("02-rechteck")

        # sxhkd-Hotkeys kommen an, obwohl das Overlay offen ist
        s.key("super+k")
        check("Hotkey bei offenem Overlay ausgeführt",
              wait(lambda: (s.tmp / "hotkey-fired").exists()))

        # Hotkey legt den Fokus auf ein anderes Fenster, Maus steht über dem Overlay:
        # Overlay holt ihn zurück, Tasten wirken ohne Klick
        s.key("super+j")
        time.sleep(0.5)
        check("Fokus nach Hotkey ohne Klick zurück beim Overlay", wait(lambda: s.focus_id() in overlay, 2))
        s.key("g")  # Ellipse: wirkt nur, wenn die Taste beim Overlay ankommt
        s.drag(1000, 300, 1300, 600)
        time.sleep(0.3)
        s.screenshot("03-ellipse-nach-hotkey")
        check("Testfenster hat nichts abbekommen", sink_out.read_text() == "a")

        # Esc: beenden, Fokus zurück ans Testfenster
        s.key("Escape")
        check("Esc beendet das Overlay", wait(lambda: not s.annotate_pids(), 10))
        check("Fokus nach Esc zurück beim Testfenster", wait(lambda: s.focus_id() == sink))
        s.type("b")
        check("Tasten kommen danach wieder im Testfenster an", wait(lambda: sink_out.read_text() == "ab"))
        s.screenshot("04-nach-esc")

        # Verlauf: ein Eintrag mit Rechteck und Ellipse
        entries = s.history_entries()
        check("Verlauf: ein Eintrag", len(entries) == 1)
        tools = sorted(e.tool.name for e in load_elements(entries[0])) if entries else []
        check(f"Verlauf: Rechteck und Ellipse gespeichert ({', '.join(tools)})", tools == ["ELLIPSE", "RECT"])

        # --last öffnet den neuesten Verlaufseintrag (z. B. per Hotkey)
        s.spawn([str(ANNOTATE), "--last"], log="last")
        check("--last öffnet den letzten Screenshot", wait(lambda: s.annotate_pids(), 10))
        wait(lambda: s.windows_of(s.annotate_pids()[0]), 10)
        time.sleep(0.4)
        s.screenshot("05-last")
        s.key("Escape")
        check("--last: Esc beendet", wait(lambda: not s.annotate_pids(), 5))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
