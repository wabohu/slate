# slate

A screenshot annotation tool and whiteboard for Linux. I wanted something like
Epic Pen or Tekapoint on my own X11 desktop, something I could change whenever
it got in my way. This is it.

Press a hotkey and slate freezes the current monitor. Draw arrows, boxes and
notes on top, blur what nobody should see, then paste the result wherever it
needs to go. Without a screenshot it's a whiteboard for quick sketches and
diagrams.

It's made for the keyboard and a tiling window manager (herbstluftwm and sxhkd
in my case). It should run on any X11 setup, but I only use it on mine.
Wayland doesn't work.

## What it can do

**Drawing**
- Freehand, lines, arrows, rectangles, ellipses and text, also in a monospace
  font for code and commands
- Numbered or lettered markers that renumber themselves
- Blur to pixelate passwords, names and the like
- Erase an area by filling it with the color around it
- Text inside shapes and on arrows
- Spotlight and magnifier for pointing at things while sharing your screen

**Editing**
- Select one or many elements, move, resize, rotate, recolor, change their order
- Copy, paste and duplicate, also between a screenshot and a whiteboard
- Undo and redo for everything

**Saving**
- Copy to the clipboard or save as PNG, the whole screen or just a cropped area
- Saved files stay editable: the drawing data is stored inside the PNG, so any
  image viewer still shows a normal picture
- Every screenshot you've changed is kept in a history, so yesterday's
  annotation can still be edited today

**Whiteboard**
- Endless canvas with pan and zoom, dark or light background
- Arrows stick to shapes and follow them when you move things around
- On a light background colors are darkened automatically so they stay readable

**Setup**
- Colors and the monospace font come from your Alacritty config
- Keys, tools, colors and sizes can be changed in a TOML file
- Scales with the screen, so it stays usable on 4K

## Requirements

- Linux with X11
- Python 3 and PySide6 (Arch: `python-pyside6`)
- `xclip` for the clipboard
- Optional: `xdotool` and `herbstclient` to give the focus back on close,
  `notify-send` with a notification daemon like dunst, and `rofi` for prompts.
  Without them slate falls back to its own Qt dialogs.

## Getting started

```sh
git clone https://github.com/wabohu/slate.git
ln -s "$PWD/slate/slate.py" ~/.local/bin/slate

slate                # annotate a screenshot of the monitor under the mouse
slate --board        # empty whiteboard in a normal window
slate --last         # open the latest screenshot from the history
slate image.png      # open a saved drawing or any PNG
```

Put `slate` on a global hotkey, that's how it's meant to be used. Inside, `?`
shows all keys and Esc quits. The full list is in [docs/usage.md](docs/usage.md).

## Configuration

Settings live in `~/.config/slate/config.toml`. Every option is explained in
[config.example.toml](config.example.toml). You don't need the file at all,
anything missing falls back to the defaults.

## Tests

```sh
python tests/test_settings.py
python tests/test_document.py
python tests/regress.py
python tests/gui/run.py      # needs Xvfb, herbstluftwm, sxhkd, xdotool
```

## License

GPL-3.0, see [LICENSE](LICENSE).
