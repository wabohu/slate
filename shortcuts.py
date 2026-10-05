"""Content of the key overview (?): which key does what, by group.

sections() returns everything as lists (group -> keys, description); overview() arranges it
for the panel (ui.HelpPanel): tools, colors and sizes as a picture row, the rest as lists.
Keys are written in lower case (a s d, ctrl+s), modifiers and names as in the docs.

The keys come from the KeyMap, so with your own bindings from [keys] and the
tool order from [tools] order. Only what applies in the current mode (screenshot or
whiteboard) is shown. The panel itself is drawn by ui.HelpPanel.

New action in keymap.DEFAULT_KEYS = a description here in DESCRIPTIONS
(tests/test_settings.py checks that none is missing).
"""
import re

SCREENSHOT, BOARD = "screenshot", "board"
BOTH = (SCREENSHOT, BOARD)

# Action -> (group, description, modes). Tool, color and size slots and the
# hjkl keys are combined (see sections) and are therefore not listed one by one here.
DESCRIPTIONS = {
    "tool_select": ("Tools", "Select", BOTH),
    "tool_marker": ("Tools", "Marker (again: 1 2 3 / A B C)", BOTH),
    "tool_blur": ("Tools", "Blur", (SCREENSHOT,)),
    "color_next": ("Color and size", "next color", BOTH),
    "color_prev": ("Color and size", "previous color", BOTH),
    "delete": ("Selection", "delete", BOTH),
    "select_all": ("Selection", "select all", BOTH),
    "raise": ("Selection", "bring forward", BOTH),
    "lower": ("Selection", "send backward", BOTH),
    "rotate_left": ("Selection", "rotate 5° counterclockwise", BOTH),
    "rotate_right": ("Selection", "rotate 5° clockwise", BOTH),
    "raise_top": ("Selection", "bring to front", BOTH),
    "lower_bottom": ("Selection", "send to back", BOTH),
    "undo": ("General", "undo", BOTH),
    "redo": ("General", "redo", BOTH),
    "copy_quit": ("Output", "copy image and quit", (SCREENSHOT,)),
    "copy_path_quit": ("Output", "save, copy path, quit", (SCREENSHOT,)),
    "copy_image": ("Output", "copy image (with selection: elements)", BOTH),
    "paste": ("Selection", "paste elements", BOTH),
    "duplicate": ("Selection", "duplicate", BOTH),
    "save": ("Output", "save editable", BOTH),
    "export_png": ("Output", "export clean PNG", BOTH),
    "crop": ("Output", "set crop (Esc meanwhile: remove)", (SCREENSHOT,)),
    "quit": ("General", "quit", BOTH),
    "help": ("General", "this overview", BOTH),
    "toggle_bar": ("General", "bar on/off", BOTH),
    "spotlight": ("Pointing", "spotlight on/off", BOTH),
    "magnifier": ("Pointing", "magnifier on/off", BOTH),
    "zoom_reset": ("View", "zoom 100 %", (BOARD,)),
    "overview": ("View", "fit all / back", (BOARD,)),
    "background_next": ("View", "background light/dark", (BOARD,)),
    "background_prev": ("View", "previous background", (BOARD,)),
    "history_prev": ("History", "older screenshot", (SCREENSHOT,)),
    "history_next": ("History", "newer screenshot", (SCREENSHOT,)),
}
# Combined in sections()
GROUPED = re.compile(r"^(tool|color|size)_\d+$|^move_(left|down|up|right)(_fine)?$")

# Fixed controls without an entry in the key table: (group, key/mouse, description, modes)
FIXED = [
    ("General", "Esc", "pointing off, deselect, otherwise quit", (SCREENSHOT,)),
    ("General", "Esc", "pointing off, deselect", (BOARD,)),
    ("Mouse", "Drag", "draw with the tool", BOTH),
    ("Mouse", "Click (select)", "select, drag = move", BOTH),
    ("Mouse", "Drag handles", "resize", BOTH),
    ("Mouse", "Drag round handle", "rotate", BOTH),
    ("Mouse", "Arrow end at a shape's edge", "dock it, it follows the shape", BOTH),
    ("Mouse", "Double-click (select)", "edit text / label shape / new text", BOTH),
    ("Mouse", "Alt+wheel", "fine size", BOTH),
    ("Mouse", "Wheel, middle button", "pan the view", (BOARD,)),
    ("Mouse", "Ctrl+wheel", "zoom", (BOARD,)),
]

# Key names as in docs/usage.md (differing from Qt's names)
KEY_NAMES = {"Return": "Enter", "Left": "←", "Right": "→",
             "Up": "↑", "Down": "↓", "Shift+?": "?", "Meta": "Super"}

GROUP_ORDER = ["Tools", "Color and size", "Selection", "Pointing", "Output", "View", "History", "General",
               "Mouse"]


def display(label):
    """Qt key text in the spelling of the overview, e.g. 'Ctrl+Return' -> 'ctrl+enter'."""
    if label in KEY_NAMES:
        return KEY_NAMES[label].lower()
    if label == "+":
        return label
    return "+".join(KEY_NAMES.get(part, part) for part in label.split("+")).lower()


def split_common(labels):
    """['shift+a', 'shift+s'] -> ('shift', ['a', 's']); without a common modifier ('', labels)."""
    prefixes = {label.rpartition("+")[0] for label in labels if label}
    if len(prefixes) == 1 and (prefix := prefixes.pop()):
        return prefix, [label.rpartition("+")[2] for label in labels]
    return "", list(labels)


def combine(labels):
    """['Shift+A', 'Shift+S'] -> 'Shift+A S'; mixed modifiers one by one with commas."""
    labels = [display(label) for label in labels if label]
    if not labels:
        return ""
    prefixes = {label.rpartition("+")[0] for label in labels}
    if len(prefixes) == 1:
        prefix = prefixes.pop()
        keys = " ".join(label.rpartition("+")[2] for label in labels)
        return f"{prefix}+{keys}" if prefix else keys
    return ", ".join(labels)


def sections(keymap, tools, color_count, size_count, board):
    """[(group, [(keys, description), …]), …] for the current mode."""
    mode = BOARD if board else SCREENSHOT
    groups = {name: [] for name in GROUP_ORDER}

    def add(group, keys, text):
        if keys:
            groups.setdefault(group, []).append((keys, text))

    def keys(action):
        """All keys of an action, e.g. 'Del, Backspace'."""
        return ", ".join(display(label) for label in keymap.labels(action))

    for i, tool in enumerate(tools, start=1):
        add("Tools", keys(f"tool_{i}"), tool.value)
    add("Color and size", combine([keymap.label(f"color_{i}") for i in range(1, color_count + 1)]),
        "color from the bar")
    add("Color and size", combine([keymap.label(f"size_{i}") for i in range(1, size_count + 1)]),
        "size in levels")
    directions = ("left", "down", "up", "right")
    add("Selection", combine([keymap.label(f"move_{d}") for d in directions]), "move")
    add("Selection", combine([keymap.label(f"move_{d}_fine") for d in directions]), "move finely")

    for action, (group, text, modes) in DESCRIPTIONS.items():
        if mode in modes:
            add(group, keys(action), text)
    for action in keymap.texts:  # never hide actions without a description
        if action not in DESCRIPTIONS and not GROUPED.match(action):
            add("General", keys(action), action)
    for group, fixed_keys, text, modes in FIXED:
        if mode in modes:
            add(group, fixed_keys.lower(), text)  # lower case like the other keys
    # Tools: Select first, as in the bar
    groups["Tools"].sort(key=lambda entry: entry[1] != "Select")
    return [(name, entries) for name, entries in groups.items() if entries]


# Groups that overview() shows as a picture row or its own column instead of a list on the right
PICTURE_GROUPS = ("Tools", "Color and size", "Mouse")


def overview(keymap, tools, color_count, size_count, board):
    """Data for the panel (draft D):
    tools: [(Tool, keys)] with Select first; colors / sizes: keys per field or level;
    color_hint / size_hint: addition to the heading (common modifier, cycling, wheel);
    mouse: [(mouse, description)]; lists: [(group, [(keys, description)])] for the right."""
    from tools import Tool  # here, so the module stays importable without Qt

    def keys(action):
        return ", ".join(display(label) for label in keymap.labels(action))

    tool_keys = [(Tool.SELECT, keys("tool_select"))]
    tool_keys += [(tool, keys(f"tool_{i}")) for i, tool in enumerate(tools, start=1)]
    tool_keys.append((Tool.MARKER, keys("tool_marker")))
    if not board:
        tool_keys.append((Tool.BLUR, keys("tool_blur")))
    color_prefix, colors = split_common([display(keymap.label(f"color_{i}")) for i in range(1, color_count + 1)])
    size_prefix, sizes = split_common([display(keymap.label(f"size_{i}")) for i in range(1, size_count + 1)])
    browse = " / ".join(k for k in (keys("color_next"), keys("color_prev")) if k)
    color_hint = ", ".join(x for x in (f"{color_prefix} + …" if color_prefix else "",
                                       f"{browse} cycles" if browse else "") if x)
    size_hint = ", ".join(x for x in (f"{size_prefix} + …" if size_prefix else "", "alt+wheel fine") if x)
    groups = sections(keymap, tools, color_count, size_count, board)
    return {
        "tools": tool_keys,
        "colors": colors, "color_hint": color_hint,
        "sizes": sizes, "size_hint": size_hint,
        "mouse": dict(groups).get("Mouse", []),
        "lists": [(name, entries) for name, entries in groups if name not in PICTURE_GROUPS],
    }
