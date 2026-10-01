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
    check("Screenshot: Eckenradius, kein Whiteboard-Hintergrund",
          s.rect_radius == RECT_RADIUS and s.board_background is None and s.board_backgrounds is None)

    # Whiteboard: eigener Radius, Hintergründe aus der Standardliste
    b, _ = quiet(st.Settings, {}, True)
    check("Whiteboard: Eckenradius", b.rect_radius == st.DEFAULT_RECT_RADIUS_BOARD)
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
    check("kaputt: Hinweise auf stderr", "[size]" in hints and "[ui]" in hints and "[rect]" in hints)

    # Gültige Werte werden übernommen
    good = {
        "size": {"stroke": [1, 3, 5, 7], "default": 4},
        "colors": {"light": {"red": "#112233"}},
        "ui": {"messages": "toast", "dialogs": "qt"},
        "rect": {"radius": 0},
        "move": {"step": 25, "step_fine": 2},
        "output": {"dir": "~/irgendwo"},
    }
    s, _ = quiet(st.Settings, good, False)
    check("gültig: übernommen", s.stroke_widths == [1, 3, 5, 7] and s.default_size_level == 3
          and s.rect_radius == 0 and s.move_steps == {False: 25, True: 2}
          and not s.use_dunst and not s.use_rofi and s.output_dir == "~/irgendwo"
          and s.light_overrides == {s.palette.lookup("red"): "#112233"})

    print("\nAlles OK." if not failures else f"\n{len(failures)} Fehler.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
