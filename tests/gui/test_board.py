#!/usr/bin/env python3
"""GUI-Test Whiteboard: Start per Hotkey, Esc/Enter schließen nicht, Strg+B (hell),
Strg+Q mit rofi-Nachfrage (Abbrechen, Speichern), wieder öffnen, Verwerfen.

    python tests/gui/test_board.py

Läuft in einem eigenen unsichtbaren X-Server (harness.py), deine Sitzung bleibt
unberührt. Bildschirmfotos: tests/gui/out/board/. Rückgabewert 0 = alles ok.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import SLATE, Session, check, load_drawing, summary, wait  # noqa: E402

PAPER = "#f8f6f0"         # heller Hintergrund aus DEFAULT_BOARD_BACKGROUNDS
EMPTY = (960, 120)        # Bildschirmpunkt, an dem nichts gezeichnet wird


def board_window(s):
    """(PID, Fenster) des laufenden Whiteboards oder (None, None)."""
    for pid in s.slate_pids():
        wins = s.windows_of(pid)
        if wins:
            return pid, wins[0]
    return None, None


def ask_rofi(s, text):
    """Warten, bis die rofi-Nachfrage offen ist, text tippen, Enter."""
    if not check(f"rofi-Nachfrage erscheint (für '{text}')", wait(lambda: s.rofi_open(), 5)):
        return
    time.sleep(0.2)
    s.type(text)
    s.key("Return")
    wait(lambda: not s.rofi_open(), 5)


def main():
    with Session("board") as s:
        # Start per Hotkey, normales Fenster von herbstluftwm
        s.key("alt+Delete")
        check("Start per Hotkey: Whiteboard-Fenster da", wait(lambda: board_window(s)[1], 10))
        pid, win = board_window(s)
        check("Whiteboard hat den Fokus", wait(lambda: s.focus_id() == win))
        check("Titel: neu", "Whiteboard – neu" in (s.window_name(win) or ""))
        dark = s.pixel(*EMPTY, name="01-gestartet")

        s.key("f")
        s.drag(500, 400, 900, 700)
        s.key("Escape")
        s.key("Return")
        time.sleep(0.5)
        check("Esc und Enter schließen das Whiteboard nicht", pid in s.slate_pids())

        # Strg+B: heller Hintergrund
        s.key("ctrl+b")
        check("Strg+B: Hintergrund hell", wait(lambda: s.pixel(*EMPTY, name="02-hell") == PAPER, 3))
        check("vorher war er dunkel", dark != PAPER)

        # Strg+Q, ungespeichert: rofi fragt. "ab" = Abbrechen, Fenster bleibt
        s.key("ctrl+q")
        time.sleep(0.3)
        s.screenshot("03-rofi")
        ask_rofi(s, "ab")
        time.sleep(0.5)
        check("rofi 'ab' (Abbrechen): Whiteboard bleibt offen", pid in s.slate_pids())

        # Strg+Q, "sp" = Speichern: Datei angelegt, Fenster zu
        s.key("ctrl+q")
        ask_rofi(s, "sp")
        check("rofi 'sp' (Speichern): Whiteboard geschlossen", wait(lambda: pid not in s.slate_pids(), 5))
        saved = sorted((s.tmp / "output").glob("*_board.png"))
        check("gespeichert als …_board.png", len(saved) == 1)
        if not saved:
            return summary()
        background, elements = load_drawing(saved[0])
        check("gespeichert: heller Hintergrund, ein Rechteck",
              hasattr(background, "name") and background.name() == PAPER
              and [e.tool.name for e in elements] == ["RECT"])

        # Wieder öffnen (wie python slate.py datei.png): als Whiteboard, hell, Titel = Datei
        s.spawn([str(SLATE), str(saved[0])], log="reopen")
        check("wieder geöffnet", wait(lambda: board_window(s)[1], 10))
        pid, win = board_window(s)
        check("Titel nennt die Datei", saved[0].name in (s.window_name(win) or ""))
        check("wieder geöffnet: Hintergrund hell", wait(lambda: s.pixel(*EMPTY, name="04-wieder-offen") == PAPER, 3))

        # Ohne Änderung: Strg+Q schließt ohne Nachfrage
        s.key("ctrl+q")
        time.sleep(0.5)
        check("unverändert: Strg+Q ohne Nachfrage", not s.rofi_open())
        check("unverändert: geschlossen", wait(lambda: pid not in s.slate_pids(), 5))

        # Ändern und verwerfen: Datei bleibt wie gespeichert
        s.spawn([str(SLATE), str(saved[0])], log="reopen2")
        wait(lambda: board_window(s)[1], 10)
        pid, win = board_window(s)
        wait(lambda: s.focus_id() == win)
        s.key("g")
        s.drag(1100, 400, 1400, 700)
        s.key("ctrl+q")
        ask_rofi(s, "vw")
        check("rofi 'vw' (Verwerfen): geschlossen", wait(lambda: pid not in s.slate_pids(), 5))
        _, elements = load_drawing(saved[0])
        check("verworfen: Datei unverändert (nur das Rechteck)", [e.tool.name for e in elements] == ["RECT"])
    return summary()


if __name__ == "__main__":
    sys.exit(main())
