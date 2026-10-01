#!/usr/bin/env python3
"""Test Einstellungen: Settings aus verschiedenen Configs, ohne Fenster.

    python tests/test_settings.py

Prüft, dass fehlende oder unbrauchbare Werte nie abstürzen, sondern zum Standardwert
führen. Nutzt die isolierte Umgebung aus regress.py (leeres HOME, Standardpalette).
Rückgabewert 0 = alles ok, 1 = Fehler.
"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regress  # noqa: E402,F401  (setzt HOME, Config und QT_QPA_PLATFORM)

from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402

failures = []


def check(name, condition):
    print(f"{'OK  ' if condition else 'FEHLER'}  {name}")
    if not condition:
        failures.append(name)


def quiet(func, *args):
    """Aufruf ohne die erwarteten Hinweise auf stderr; liefert (Ergebnis, Hinweise)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        result = func(*args)
    return result, err.getvalue()


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841  (KeyMap braucht Qt)
    import settings as st
    from tools import RECT_RADIUS, Tool

    # Leere Config: alles Standard, kein Absturz
    s, _ = quiet(st.Settings, {}, False)
    check("leer: Größen-Stufen", s.stroke_widths == list(st.DEFAULT_STROKE_WIDTHS)
          and s.text_sizes == list(st.DEFAULT_TEXT_SIZES))
    check("leer: Startstufe", s.default_size_level == st.DEFAULT_SIZE_LEVEL - 1)
    check("leer: Startwerkzeug", s.default_tool == st.DEFAULT_TOOL)
    check("leer: Startfarbe", s.swatches[s.default_color_index] == s.palette.lookup(st.DEFAULT_COLOR))
    check("leer: Schrittweiten", s.move_steps == {False: st.DEFAULT_MOVE_STEP, True: st.DEFAULT_MOVE_STEP_FINE})
    check("leer: dunst und rofi", s.use_dunst and s.use_rofi and s.rofi_theme is None)
    from history import default_history_dir
    check("leer: Verlauf an, Standardordner, 100", s.history_enabled and s.history_dir == default_history_dir()
          and s.history_keep == st.DEFAULT_HISTORY_KEEP)
    check("leer: Leiste im Screenshot-Modus aus", s.show_bar is False)
    check("Screenshot: Eckenradius, kein Whiteboard-Hintergrund",
          s.rect_radius == RECT_RADIUS and s.board_background is None and s.board_backgrounds is None)

    # Whiteboard: eigener Radius, Hintergründe aus der Standardliste
    b, _ = quiet(st.Settings, {}, True)
    check("Whiteboard: Eckenradius", b.rect_radius == st.DEFAULT_RECT_RADIUS_BOARD)
    check("Whiteboard: Leiste an", b.show_bar is True)
    flipped, _ = quiet(st.Settings, {"ui": {"show_bar": True, "show_bar_board": False}}, False)
    flipped_b, _ = quiet(st.Settings, {"ui": {"show_bar": True, "show_bar_board": False}}, True)
    broken, _ = quiet(st.Settings, {"ui": {"show_bar": "ja"}}, False)
    check("Leiste aus [ui] show_bar / show_bar_board, kaputt -> Standard",
          flipped.show_bar and not flipped_b.show_bar and broken.show_bar is False)
    check("Whiteboard: Hintergründe", len(b.board_backgrounds) == len(st.DEFAULT_BOARD_BACKGROUNDS)
          and b.board_background == b.board_backgrounds[0])

    # Unbrauchbare Werte: Standard plus Hinweis
    bad = {
        "tools": {"order": "kein Array", "default": "zauberstab"},
        "size": {"stroke": [1, 2], "text": [1, 2, 3, 4], "default": 9},
        "colors": {"order": ["gibtsnicht"], "default": "lila", "light": {"red": "kaputt", "blue": 5}},
        "ui": {"bar_opacity": 3, "bar_background": "quatsch", "messages": "brieftaube", "dialogs": 1},
        "board": {"background": "nope", "backgrounds": ["auch nicht", 7]},
        "rect": {"radius": -1, "radius_board": 999},
        "move": {"step": 0, "step_fine": "fein"},
        "keys": {"undo": 5, "gibtsnicht": "x"},
        "history": {"enabled": "ja", "keep": 0, "dir": 42},
    }
    s, hints = quiet(st.Settings, bad, True)
    check("kaputt: Größen-Stufen", s.stroke_widths == list(st.DEFAULT_STROKE_WIDTHS)
          and s.text_sizes == list(st.DEFAULT_TEXT_SIZES) and s.default_size_level == st.DEFAULT_SIZE_LEVEL - 1)
    check("kaputt: Werkzeuge", s.default_tool == st.DEFAULT_TOOL and Tool.FREEHAND in s.tools)
    check("kaputt: Farbleiste nicht leer", len(s.swatches) > 0 and 0 <= s.default_color_index < len(s.swatches))
    check("kaputt: helle Varianten übersprungen", s.light_overrides == {})
    expected_bg = QColor(s.palette.lookup(st.DEFAULT_BAR_BACKGROUND))
    expected_bg.setAlphaF(st.DEFAULT_BAR_OPACITY)  # Theme legt die Deckkraft in die Hintergrundfarbe
    check("kaputt: Leistenfarben", s.theme.background == expected_bg)
    check("kaputt: dunst und rofi", s.use_dunst and s.use_rofi)
    check("kaputt: Whiteboard-Hintergründe", len(s.board_backgrounds) == len(st.DEFAULT_BOARD_BACKGROUNDS)
          and s.board_background == QColor(s.palette.lookup(st.DEFAULT_BOARD_BACKGROUND)))
    check("kaputt: Eckenradius", s.rect_radius == st.DEFAULT_RECT_RADIUS_BOARD)
    check("kaputt: Schrittweiten", s.move_steps == {False: st.DEFAULT_MOVE_STEP, True: st.DEFAULT_MOVE_STEP_FINE})
    check("kaputt: Verlauf", s.history_enabled and s.history_keep == st.DEFAULT_HISTORY_KEEP
          and s.history_dir == default_history_dir())
    check("kaputt: Hinweise auf stderr", "[size]" in hints and "[ui]" in hints and "[rect]" in hints)

    # Gültige Werte werden übernommen
    good = {
        "size": {"stroke": [1, 3, 5, 7], "default": 4},
        "colors": {"light": {"red": "#112233"}},
        "ui": {"messages": "toast", "dialogs": "qt"},
        "rect": {"radius": 0},
        "move": {"step": 25, "step_fine": 2},
        "output": {"dir": "~/irgendwo"},
        "history": {"enabled": False, "keep": 5, "dir": "~/verlauf"},
    }
    s, _ = quiet(st.Settings, good, False)
    check("gültig: übernommen", s.stroke_widths == [1, 3, 5, 7] and s.default_size_level == 3
          and s.rect_radius == 0 and s.move_steps == {False: 25, True: 2}
          and not s.use_dunst and not s.use_rofi and s.output_dir == "~/irgendwo"
          and s.light_overrides == {s.palette.lookup("red"): "#112233"}
          and not s.history_enabled and s.history_keep == 5 and s.history_dir == Path.home() / "verlauf")

    # Tastenübersicht (?): jede Aktion beschrieben, Inhalt je Modus
    import shortcuts
    from keymap import DEFAULT_KEYS, KeyMap
    missing = [a for a in DEFAULT_KEYS if a not in shortcuts.DESCRIPTIONS and not shortcuts.GROUPED.match(a)]
    check(f"Übersicht: jede Aktion hat eine Beschreibung {missing or ''}", not missing)
    keymap = KeyMap({"keys": {"undo": "u"}, "tools": {"order": ["rect", "text"]}})
    shot = dict(shortcuts.sections(keymap, [Tool.RECT, Tool.TEXT], 9, 4, board=False))
    board = dict(shortcuts.sections(keymap, [Tool.RECT, Tool.TEXT], 9, 4, board=True))
    flat = lambda sec: {(k, t) for entries in sec.values() for k, t in entries}  # noqa: E731
    check("Übersicht: eigene Belegung und Werkzeug-Reihenfolge",
          ("u", "Rückgängig") in flat(shot) and ("a", "Rechteck") in flat(shot) and ("s", "Text") in flat(shot)
          and shot["Werkzeuge"][0] == ("w", "Auswahl"))
    check("Übersicht: Plätze zusammengefasst", ("shift+a s d f g z x c v", "Farbe aus der Leiste") in flat(shot)
          and ("alt+a s d f", "Größe in Stufen") in flat(shot) and ("h j k l", "verschieben") in flat(shot))
    check("Übersicht: nur was im Modus gilt", "Verlauf" in shot and "Verlauf" not in board
          and "Ansicht" in board and "Ansicht" not in shot)
    check("Übersicht: alle Tasten einer Aktion, klein, deutsche Namen",
          ("?", "diese Übersicht") in flat(shot) and ("entf, backspace", "löschen") in flat(shot)
          and ("enter", "Bild kopieren und beenden") in flat(shot) and ("strg+s", "bearbeitbar speichern") in flat(shot)
          and ("←", "älterer Screenshot") in flat(shot) and ("strg+shift+b", "Hintergrund zurück") in flat(board))
    ov = shortcuts.overview(keymap, [Tool.RECT, Tool.TEXT], 9, 4, board=False)
    check("Panel-Daten: Werkzeuge mit Auswahl vorne, Farben und Größen je Taste",
          ov["tools"] == [(Tool.SELECT, "w"), (Tool.RECT, "a"), (Tool.TEXT, "s")]
          and ov["colors"] == list("asdfgzxcv") and ov["sizes"] == list("asdf")
          and ov["color_hint"] == "shift + …, tab / shift+tab blättert" and ov["size_hint"].startswith("alt + …"))
    names = [name for name, _ in ov["lists"]]
    check("Panel-Daten: Bildgruppen nicht doppelt in den Listen",
          not {"Werkzeuge", "Farbe und Größe", "Maus"} & set(names) and ov["mouse"] and "Ausgabe" in names)
    plain = st.Settings({}, False)
    check("Theme: Akzent blau, Überschrift magenta (Standard)",
          plain.theme.accent == QColor(plain.palette.lookup("blue"))
          and plain.theme.heading == QColor(plain.palette.lookup("magenta")))
    own, _ = quiet(st.Settings, {"ui": {"bar_heading": "yellow", "bar_accent": "quatsch"}}, False)
    check("Theme: Überschrift aus [ui] bar_heading, unbekannter Akzent -> Standard",
          own.theme.heading == QColor(own.palette.lookup("yellow")) and own.theme.accent == plain.theme.accent)

    print("\nAlles OK." if not failures else f"\n{len(failures)} Fehler.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
