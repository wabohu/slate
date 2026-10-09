#!/usr/bin/env python3
"""Settings test: Settings from different configs, without a window.

    python tests/test_settings.py

Checks that missing or unusable values never crash but lead to the default value.
Uses the isolated environment from regress.py (empty HOME, default palette).
Exit code 0 = all ok, 1 = failures.
"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regress  # noqa: E402,F401  (sets HOME, config and QT_QPA_PLATFORM)

from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402

failures = []


def check(name, condition):
    print(f"{'OK  ' if condition else 'FAIL  '}  {name}")
    if not condition:
        failures.append(name)


def quiet(func, *args):
    """Call without the expected hints on stderr; returns (result, hints)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        result = func(*args)
    return result, err.getvalue()


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841  (KeyMap needs Qt)
    import settings as st
    from tools import RECT_RADIUS, Tool

    # Empty config: everything default, no crash
    s, _ = quiet(st.Settings, {}, False)
    check("empty: size levels", s.stroke_widths == list(st.DEFAULT_STROKE_WIDTHS)
          and s.text_sizes == list(st.DEFAULT_TEXT_SIZES))
    check("empty: start level", s.default_size_level == st.DEFAULT_SIZE_LEVEL - 1)
    check("empty: start tool", s.default_tool == st.DEFAULT_TOOL)
    check("empty: start color", s.swatches[s.default_color_index] == s.palette.lookup(st.DEFAULT_COLOR))
    check("empty: step sizes", s.move_steps == {False: st.DEFAULT_MOVE_STEP, True: st.DEFAULT_MOVE_STEP_FINE})
    check("empty: dunst and rofi", s.use_dunst and s.use_rofi and s.rofi_theme is None)
    from history import default_history_dir
    check("empty: history on, default folder, 100", s.history_enabled and s.history_dir == default_history_dir()
          and s.history_keep == st.DEFAULT_HISTORY_KEEP)
    check("empty: bar off in screenshot mode", s.show_bar is False)
    check("empty: spotlight 90 px / 45 %, magnifier 100 px / 2x", s.spotlight_radius == 90 and s.lens_radius == 100
          and s.spotlight_dim == 45 and s.lens_zoom == 2.0)
    tuned, hints2 = quiet(st.Settings, {"pointer": {"spotlight_dim": 30, "lens_zoom": 3, "lens_radius": 0.5}}, False)
    check("dimming and magnification from [pointer], integer as zoom ok, fraction as radius not",
          tuned.spotlight_dim == 30 and tuned.lens_zoom == 3.0 and tuned.lens_radius == 100 and "lens_radius" in hints2)
    own, hints = quiet(st.Settings, {"pointer": {"spotlight_radius": 140, "lens_radius": "big"}}, False)
    wrong, _ = quiet(st.Settings, {"pointer": {"spotlight_radius": 5000}}, False)
    check("radii from [pointer], invalid -> default with a hint",
          own.spotlight_radius == 140 and own.lens_radius == 100 and "lens_radius" in hints
          and wrong.spotlight_radius == 90)
    check("screenshot: corner radius, no whiteboard background",
          s.rect_radius == st.DEFAULT_RECT_RADIUS and s.board_background is None and s.board_backgrounds is None)

    # Whiteboard: own radius, backgrounds from the default list
    b, _ = quiet(st.Settings, {}, True)
    check("whiteboard: corner radius", b.rect_radius == st.DEFAULT_RECT_RADIUS_BOARD)
    check("whiteboard: own stroke widths", b.stroke_widths == list(st.DEFAULT_STROKE_WIDTHS_BOARD))
    own_s, _ = quiet(st.Settings, {"size": {"stroke": [1, 2, 3, 4], "stroke_board": [5, 6, 7, 8]}}, False)
    own_b, _ = quiet(st.Settings, {"size": {"stroke": [1, 2, 3, 4], "stroke_board": [5, 6, 7, 8]}}, True)
    check("stroke widths: stroke in screenshot mode, stroke_board in the whiteboard",
          own_s.stroke_widths == [1, 2, 3, 4] and own_b.stroke_widths == [5, 6, 7, 8])
    check("whiteboard: bar on", b.show_bar is True)
    flipped, _ = quiet(st.Settings, {"ui": {"show_bar": True, "show_bar_board": False}}, False)
    flipped_b, _ = quiet(st.Settings, {"ui": {"show_bar": True, "show_bar_board": False}}, True)
    broken, _ = quiet(st.Settings, {"ui": {"show_bar": "yes"}}, False)
    check("bar from [ui] show_bar / show_bar_board, broken -> default",
          flipped.show_bar and not flipped_b.show_bar and broken.show_bar is False)
    check("whiteboard: backgrounds", len(b.board_backgrounds) == len(st.DEFAULT_BOARD_BACKGROUNDS)
          and b.board_background == b.board_backgrounds[0])

    # Unusable values: default plus a hint
    bad = {
        "tools": {"order": "not an array", "default": "magic_wand"},
        "size": {"stroke": [1, 2], "text": [1, 2, 3, 4], "default": 9},
        "colors": {"order": ["nonexistent"], "default": "purple", "light": {"red": "broken", "blue": 5}},
        "ui": {"bar_opacity": 3, "bar_background": "nonsense", "messages": "carrier_pigeon", "dialogs": 1},
        "board": {"background": "nope", "backgrounds": ["neither", 7]},
        "rect": {"radius": -1, "radius_board": 999},
        "move": {"step": 0, "step_fine": "fine"},
        "keys": {"undo": 5, "nonexistent": "x"},
        "history": {"enabled": "yes", "keep": 0, "dir": 42},
    }
    s, hints = quiet(st.Settings, bad, True)
    check("broken: size levels", s.stroke_widths == list(st.DEFAULT_STROKE_WIDTHS_BOARD)
          and s.text_sizes == list(st.DEFAULT_TEXT_SIZES) and s.default_size_level == st.DEFAULT_SIZE_LEVEL - 1)
    check("broken: tools", s.default_tool == st.DEFAULT_TOOL and Tool.FREEHAND in s.tools)
    check("broken: color bar not empty", len(s.swatches) > 0 and 0 <= s.default_color_index < len(s.swatches))
    check("broken: light variants skipped", s.light_overrides == {})
    expected_bg = QColor(s.palette.lookup(st.DEFAULT_BAR_BACKGROUND))
    expected_bg.setAlphaF(st.DEFAULT_BAR_OPACITY)  # Theme puts the opacity into the background color
    check("broken: bar colors", s.theme.background == expected_bg)
    check("broken: dunst and rofi", s.use_dunst and s.use_rofi)
    check("broken: whiteboard backgrounds", len(s.board_backgrounds) == len(st.DEFAULT_BOARD_BACKGROUNDS)
          and s.board_background == QColor(s.palette.lookup(st.DEFAULT_BOARD_BACKGROUND)))
    check("broken: corner radius", s.rect_radius == st.DEFAULT_RECT_RADIUS_BOARD)
    check("broken: step sizes", s.move_steps == {False: st.DEFAULT_MOVE_STEP, True: st.DEFAULT_MOVE_STEP_FINE})
    check("broken: history", s.history_enabled and s.history_keep == st.DEFAULT_HISTORY_KEEP
          and s.history_dir == default_history_dir())
    check("broken: hints on stderr", "[size]" in hints and "[ui]" in hints and "[rect]" in hints)

    # Valid values are taken over
    good = {
        "size": {"stroke": [1, 3, 5, 7], "default": 4},
        "colors": {"light": {"red": "#112233"}},
        "ui": {"messages": "toast", "dialogs": "qt"},
        "rect": {"radius": 0},
        "move": {"step": 25, "step_fine": 2},
        "output": {"dir": "~/somewhere"},
        "history": {"enabled": False, "keep": 5, "dir": "~/my-history"},
    }
    s, _ = quiet(st.Settings, good, False)
    check("valid: taken over", s.stroke_widths == [1, 3, 5, 7] and s.default_size_level == 3
          and s.rect_radius == 0 and s.move_steps == {False: 25, True: 2}
          and not s.use_dunst and not s.use_rofi and s.output_dir == "~/somewhere"
          and s.light_overrides == {s.palette.lookup("red"): "#112233"}
          and not s.history_enabled and s.history_keep == 5 and s.history_dir == Path.home() / "my-history")

    # Monospace font: [text] mono_font, otherwise the terminal font from Alacritty
    import tempfile

    import colors
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        both = base / "both.toml"
        both.write_text('[font.normal]\nfamily = "Plain Mono"\n[font.bold]\nfamily = "Bold Mono"\n')
        normal_only = base / "normal.toml"
        normal_only.write_text('[font.normal]\nfamily = "Plain Mono"\n')
        imported = base / "main.toml"
        imported.write_text('[general]\nimport = ["normal.toml"]\n[colors.primary]\nbackground = "#000000"\n')
        none = base / "none.toml"
        none.write_text('[font]\nsize = 12\n')
        broken = base / "broken.toml"
        broken.write_text('[font.normal\nfamily = ')
        fonts = [colors.load_terminal_font(p) for p in (both, normal_only, imported, none)]
        broken_font, _ = quiet(colors.load_terminal_font, broken)
    check(f"terminal font: bold first, else normal, via import, none -> None ({fonts})",
          fonts == ["Bold Mono", "Plain Mono", "Plain Mono", None] and broken_font is None)
    own_font = st.Settings({"text": {"mono_font": "My Mono"}}, False)
    check("monospace: [text] mono_font, empty = terminal font (none in the test: system font)",
          own_font.mono_family == "My Mono" and st.Settings({"text": {"mono_font": ""}}, False).mono_family is None
          and s.mono_family is None)

    # Key overview (?): every action described, content per mode
    import shortcuts
    from keymap import DEFAULT_KEYS, KeyMap
    missing = [a for a in DEFAULT_KEYS if a not in shortcuts.DESCRIPTIONS and not shortcuts.GROUPED.match(a)]
    check(f"overview: every action has a description {missing or ''}", not missing)
    keymap = KeyMap({"keys": {"undo": "u"}, "tools": {"order": ["rect", "text"]}})
    shot = dict(shortcuts.sections(keymap, [Tool.RECT, Tool.TEXT], 9, 4, board=False))
    board = dict(shortcuts.sections(keymap, [Tool.RECT, Tool.TEXT], 9, 4, board=True))
    flat = lambda sec: {(k, t) for entries in sec.values() for k, t in entries}  # noqa: E731
    check("overview: own bindings and tool order",
          ("u", "undo") in flat(shot) and ("a", "Rectangle") in flat(shot) and ("s", "Text") in flat(shot)
          and shot["Tools"][0] == ("w", "Select"))
    check("overview: slots combined", ("shift+a s d f g z x c v", "color from the bar") in flat(shot)
          and ("alt+a s d f", "size in levels") in flat(shot) and ("h j k l", "move") in flat(shot))
    check("overview: only what applies in the mode", "History" in shot and "History" not in board
          and "View" in board and "View" not in shot)
    check("overview: all keys of an action, lower case, own names",
          ("?", "this overview") in flat(shot) and ("del, backspace", "delete (nothing selected: clear the crop area)") in flat(shot)
          and ("del, backspace", "delete") in flat(board)
          and ("enter", "copy image and quit") in flat(shot) and ("ctrl+s", "save editable") in flat(shot)
          and ("←", "older screenshot") in flat(shot) and ("ctrl+shift+b", "previous background") in flat(board))
    ov = shortcuts.overview(keymap, [Tool.RECT, Tool.TEXT], 9, 4, board=False)
    check("panel data: tools with Select first, colors and sizes per key",
          ov["tools"] == [(Tool.SELECT, "w"), (Tool.RECT, "a"), (Tool.TEXT, "s"), (Tool.MARKER, "c"), (Tool.BLUR, "z")]
          and ov["colors"] == list("asdfgzxcv") and ov["sizes"] == list("asdf")
          and ov["color_hint"] == "shift + …, tab / shift+tab cycles" and ov["size_hint"].startswith("alt + …"))
    keys = ov["keyboard"]
    listed = {k for _, entries in ov["lists"] for k, _ in entries}
    check("panel data: keyboard picture with tools, single keys and Shift, not repeated in the lists",
          keys["w"]["plain"] == (Tool.SELECT, "Select") and keys["a"]["plain"][0] == Tool.RECT
          and keys["q"]["plain"][1].startswith("rotate") and keys["q"]["shift"][1].startswith("rotate")
          and keys["x"]["plain"] == (None, "crop") and keys["tab"]["shift"] == (None, "color ←")
          and "u" not in keys and not {"q", "shift+q", "x", "b", "e", "w"} & listed and "?" in listed)
    board_keys = shortcuts.overview(keymap, [Tool.RECT, Tool.TEXT], 9, 4, board=True)["keyboard"]
    check("panel data: keyboard picture only with what applies (no crop, no blur on the whiteboard)",
          "x" not in board_keys and "z" not in board_keys and "e" in board_keys)
    names = [name for name, _ in ov["lists"]]
    check("panel data: picture groups not repeated in the lists",
          not {"Tools", "Color and size", "Mouse"} & set(names) and ov["mouse"] and "Output" in names)
    plain = st.Settings({}, False)
    check("theme: accent blue, heading magenta (default)",
          plain.theme.accent == QColor(plain.palette.lookup("blue"))
          and plain.theme.heading == QColor(plain.palette.lookup("magenta")))
    own, _ = quiet(st.Settings, {"ui": {"bar_heading": "yellow", "bar_accent": "nonsense"}}, False)
    check("theme: heading from [ui] bar_heading, unknown accent -> default",
          own.theme.heading == QColor(own.palette.lookup("yellow")) and own.theme.accent == plain.theme.accent)

    # scripts/sync_config.py: take over new entries, keep own values
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import tomllib

    import sync_config
    template = (
        '# Template\n\n[ui]\nbar = "background"   # comment with "#" in it\ncolor = "#f8f6f0"  # light\n'
        'new = true\n\n[colors.light]\n# yellow = "#8f5e15"\n\n[keys]\nundo = "r"\n')
    user = ('# My config\n[ui]\nbar = "#112233"\ncolor = "#f8f6f0"\nalt = 3\n'
            '[colors.light]\nyellow = "#000000"\n[keys]\nundo = ["u", "ctrl+z"]\n[own]\nx = "a # b"\n')
    text, added, own = sync_config.merge(template, user)
    merged = tomllib.loads(text)
    check("sync_config: new keys added, own values kept",
          added == [("ui", "new")] and merged["ui"] == {"bar": "#112233", "color": "#f8f6f0", "new": True, "alt": 3}
          and merged["keys"]["undo"] == ["u", "ctrl+z"] and merged["own"] == {"x": "a # b"})
    check("sync_config: comments of the template, own header, example replaced",
          text.startswith("# My config\n") and '# comment with "#" in it' in text
          and 'yellow = "#000000"' in text and '# yellow' not in text)
    check("sync_config: second run changes nothing", sync_config.merge(template, text)[0] == text)

    print("\nAll OK." if not failures else f"\n{len(failures)} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
