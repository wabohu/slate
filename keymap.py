"""Central key bindings: action -> key, with overrides from the config.

Every action has a name (e.g. "undo", "tool_1", "color_3") and a
default key. In the config, [keys] overrides individual entries:

    [keys]
    undo = "r"
    tool_6 = "t"
    color_next = ""      # empty = action without a key
    delete = ["delete", "backspace"]   # list = several keys for one action

New feature with a key: entry in DEFAULT_KEYS + handler in Canvas.actions.

Qt concept: QKeySequence("shift+r") turns text into keys. One entry of it
is a QKeyCombination (key + modifiers); toCombined() turns that into a number
that works as a dict key.
"""
import sys

from PySide6.QtCore import QKeyCombination, Qt
from PySide6.QtGui import QKeySequence

# Tool slots: tool_i selects the tool at position i of [tools] order
TOOL_SLOT_KEYS = ("a", "s", "d", "f", "g", "t")
TOOL_SLOTS = 9    # tool_7 … tool_9 have no default key, but can be bound in the config
# Color slots: color_i selects field i of the color bar
COLOR_SLOT_KEYS = ("a", "s", "d", "f", "g", "z", "x", "c", "v", "b")
COLOR_SLOTS = 17  # the bar can have at most this many fields (8 + 8 + foreground)
# Size levels: size_i = stroke width or font size level i
SIZE_SLOT_KEYS = ("a", "s", "d", "f")


def _slots(prefix, count, keys, modifier=""):
    return {f"{prefix}_{i}": (modifier + keys[i - 1] if i <= len(keys) else "")
            for i in range(1, count + 1)}


DEFAULT_KEYS = {
    "tool_select": "w",
    "select_all": "ctrl+a",    # select everything (select tool)
    "raise": "ctrl+up",               # selection one step forward
    "lower": "ctrl+down",             # selection one step back
    "rotate_left": "q",               # rotate the selection counterclockwise (ROTATE_STEP)
    "rotate_right": "shift+q",        # rotate the selection clockwise
    "raise_top": "ctrl+shift+up",     # selection all the way to the front
    "lower_bottom": "ctrl+shift+down",  # selection all the way to the back
    "tool_blur": "z",          # blur (pixelate), screenshot mode only
    "tool_marker": "c",        # marker; c again: toggle 1 2 3 / A B C
    "crop": "y",               # draw a crop (Esc meanwhile: remove it), screenshot mode only
    "delete": ("delete", "backspace"),  # delete the selected element
    "undo": "r",
    "redo": "shift+r",
    "color_next": "tab",
    "color_prev": "shift+tab",
    "copy_quit": "return",     # image to the clipboard and quit
    "copy_path_quit": "shift+return",  # save (like Ctrl+S), copy the absolute path, quit
    "copy_image": "ctrl+c",    # with a selection: copy elements, otherwise image to the clipboard
    "paste": "ctrl+v",         # paste copied elements (at the mouse), also from another window
    "duplicate": "ctrl+d",     # duplicate the selection (slightly offset)
    "zoom_reset": "ctrl+0",    # whiteboard: zoom to 100 %
    "overview": "ctrl+w",      # whiteboard: fit the whole document into the window
    "background_next": "ctrl+b",        # whiteboard: next background from [board] backgrounds
    "background_prev": "ctrl+shift+b",  # whiteboard: previous background
    # Move the selection (step sizes in [move]); Shift = fine steps
    "move_left": "h", "move_down": "j", "move_up": "k", "move_right": "l",
    "move_left_fine": "shift+h", "move_down_fine": "shift+j",
    "move_up_fine": "shift+k", "move_right_fine": "shift+l",
    "quit": "ctrl+q",          # quit (on the whiteboard the only key for it, Esc does not close there)
    "save": "ctrl+s",          # editable drawing (PNG with embedded data)
    "export_png": "ctrl+e",    # clean PNG without editing data
    "history_prev": "left",    # history: older screenshot (screenshot mode only)
    "history_next": "right",   # history: newer screenshot
    "help": "shift+?",         # overview of all shortcuts (? = Shift+/ on the US layout)
    "toggle_bar": "b",         # show/hide the bar
    "spotlight": "e",          # pointing: spotlight on/off (everything darkened except around the mouse)
    "magnifier": "shift+e",    # pointing: magnifier on/off
    **_slots("tool", TOOL_SLOTS, TOOL_SLOT_KEYS),
    **_slots("color", COLOR_SLOTS, COLOR_SLOT_KEYS, modifier="shift+"),
    **_slots("size", len(SIZE_SLOT_KEYS), SIZE_SLOT_KEYS, modifier="alt+"),
}

# Renamed actions: a hint instead of "unknown", the old entry is ignored
LEGACY_ACTIONS = {
    "save_png": "is now called export_png (default Ctrl+E); Ctrl+S saves the editable drawing",
}

# Only these modifiers count; e.g. KeypadModifier (number pad) is ignored
_MODIFIERS = Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier


def parse_shortcut(text):
    """'r', 'shift+r', 'ctrl+z', 'tab' -> QKeyCombination; invalid -> None."""
    seq = QKeySequence(text.strip())
    if seq.count() != 1 or seq[0].key() == Qt.Key_unknown:
        return None
    return _normalize(seq[0])


def _normalize(combo):
    """Comparable form: only relevant modifiers, Shift+Tab instead of 'Backtab'."""
    key = combo.key()
    mods = combo.keyboardModifiers() & _MODIFIERS
    if key == Qt.Key_Backtab:  # Qt reports Shift+Tab as a separate key "Backtab"
        key = Qt.Key_Tab
        mods |= Qt.ShiftModifier
    elif key == Qt.Key_Enter:  # Enter on the number pad like the normal Enter key
        key = Qt.Key_Return
    return QKeyCombination(mods, key)


def _as_list(value):
    """'r' -> ['r'], ('del', 'backspace') -> ['del', 'backspace']"""
    return [value] if isinstance(value, str) else list(value)


class KeyMap:
    def __init__(self, config):
        keys_table = config.get("keys") if isinstance(config.get("keys"), dict) else {}
        user = {}  # entries set by the user: action -> text or list of texts

        # Old notation [tools] keys = ["a", "s", …] -> tool_1, tool_2, …
        tools_table = config.get("tools") if isinstance(config.get("tools"), dict) else {}
        legacy = tools_table.get("keys")
        if isinstance(legacy, list):
            for i, text in enumerate(legacy, start=1):
                if isinstance(text, str):
                    user[f"tool_{i}"] = text

        for action, value in keys_table.items():
            if action in LEGACY_ACTIONS:
                print(f"[keys] {action} {LEGACY_ACTIONS[action]}", file=sys.stderr)
            elif action not in DEFAULT_KEYS:
                print(f"[keys] Unknown action: {action!r}", file=sys.stderr)
            elif not (isinstance(value, str)
                      or isinstance(value, list) and all(isinstance(v, str) for v in value)):
                print(f"[keys] {action}: value must be text or a list of texts, not {value!r}",
                      file=sys.stderr)
            else:
                user[action] = value

        self.texts = {}     # action -> first key text (for display)
        self.all_texts = {}  # action -> all key texts (for the shortcut overview)
        self._lookup = {}   # key (as a number) -> action
        # The user's entries first, then the defaults: if a key is bound twice,
        # whatever is explicitly in the config wins
        ordered = [(a, user[a], True) for a in user] + [
            (a, t, False) for a, t in DEFAULT_KEYS.items() if a not in user
        ]
        for action, value, from_config in ordered:
            for text in _as_list(value):
                if not text.strip():
                    continue  # deliberately without a key
                combo = parse_shortcut(text)
                if combo is None:
                    print(f"[keys] {action}: invalid key {text!r}, ignored", file=sys.stderr)
                    continue
                self._bind(action, text, combo)
            # If the user only entered invalid keys, the default stays
            if from_config and action not in self.texts:
                for text in _as_list(DEFAULT_KEYS[action]):
                    if text and (combo := parse_shortcut(text)) is not None:
                        print(f"[keys] {action}: using default {text!r}", file=sys.stderr)
                        self._bind(action, text, combo)

    def _bind(self, action, text, combo):
        code = combo.toCombined()
        if code in self._lookup:
            print(f"[keys] {text!r} is bound twice: {self._lookup[code]} keeps it, "
                  f"{action} does not get it", file=sys.stderr)
            return
        self._lookup[code] = action
        self.texts.setdefault(action, text)
        self.all_texts.setdefault(action, []).append(text)

    def action_for(self, event):
        """Action for a QKeyEvent or None."""
        return self._lookup.get(_normalize(event.keyCombination()).toCombined())

    def label(self, action):
        """Short display text, e.g. 'A' or 'Shift+T'; '' if without a key."""
        text = self.texts.get(action)
        return QKeySequence(text).toString() if text else ""

    def labels(self, action):
        """Display texts of all keys of an action, e.g. ['Del', 'Backspace']."""
        return [QKeySequence(text).toString() for text in self.all_texts.get(action, [])]
