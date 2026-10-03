# slate

Screenshot annotation tool and whiteboard for Linux (X11), similar to 
Tekapoint and Excalidraw.

A screenshot of the monitor is frozen and shown full screen, 
you can mark it up with shapes, arrows, text, numbered markers and blur parts of it. The result
goes to the clipboard or into a file that you can edit again later.

Built with Python and PySide6 (Qt 6), for keyboard-driven use under a tiling
window manager (developed with herbstluftwm and sxhkd).

> **Personal project**, tailored to my own workflow (X11, tiling WM,
> keyboard). It also runs elsewhere under X11, but without warranty and without
> support; Wayland is not supported. Feel free to fork and adapt it.

## Features

- Freehand, line, arrow, rectangle, ellipse, text, markers (1 2 3 / A B C),
  blur for pixelating
- Select, multi-select, move, resize, bring to front / send to back,
  undo/redo
- Crop, copy (Enter), export as PNG
- Editable files: a normal PNG, the editing data is embedded in the PNG itself
- History: changed screenshots are saved automatically, ← / → browses them
- Whiteboard mode (`--board`) with zoom and a pannable canvas
- Spotlight and magnifier for pointing
- Copy elements between screenshot and whiteboard
- Keys, colors, tools and sizes configurable via a TOML config,
  colors taken from the Alacritty config

## Requirements

- Linux with X11 (no Wayland)
- Python 3 and PySide6 (Arch: `python-pyside6`)
- `xclip` (clipboard)
- optional: `xdotool` and `herbstclient` (give the focus back on close),
  `notify-send` with a notification daemon such as dunst (messages),
  `rofi` (prompts). Without notify-send or rofi, slate uses its own Qt dialogs.

## Getting started

```sh
git clone https://github.com/wabohu/slate.git
ln -s "$PWD/slate/slate.py" ~/.local/bin/slate

slate                # annotate a screenshot of the monitor under the mouse
slate --board        # empty whiteboard in a normal window
slate --last         # open the latest screenshot from the history
slate image.png      # open a saved drawing or any PNG
```

It works best on a global hotkey, e.g. in sxhkd.

Inside the tool, `?` shows all shortcuts and Esc quits. In detail:
[docs/usage.md](docs/usage.md).

## Configuration

`~/.config/slate/config.toml`; a template with all values and explanations:
[config.example.toml](config.example.toml). If the file or a value is missing,
the defaults apply.

## Tests

```sh
python tests/test_settings.py
python tests/test_document.py
python tests/regress.py
python tests/gui/run.py      # needs Xvfb, herbstluftwm, sxhkd, xdotool
```

## License

GPL-3.0, see [LICENSE](LICENSE).
