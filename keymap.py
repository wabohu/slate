"""Zentrale Tastenbelegung: Aktion -> Taste, mit Overrides aus der Config.

Jede Aktion hat einen Namen (z. B. "undo", "tool_1", "color_3") und eine
Standardtaste. In der Config überschreibt [keys] einzelne Einträge:

    [keys]
    undo = "r"
    tool_6 = "t"
    color_next = ""      # leer = Aktion ohne Taste

Neue Funktion mit Taste: Eintrag in DEFAULT_KEYS + Handler in Canvas.actions.

Qt-Konzept: QKeySequence("shift+r") wandelt Text in Tasten um. Ein Eintrag davon
ist eine QKeyCombination (Taste + Modifier); toCombined() macht daraus eine Zahl,
die sich als Dict-Schlüssel eignet.
"""
import sys

from PySide6.QtCore import QKeyCombination, Qt
from PySide6.QtGui import QKeySequence

# Werkzeug-Plätze: tool_i wählt das Werkzeug an Position i von [tools] order
TOOL_SLOT_KEYS = ("a", "s", "d", "f", "g", "t")
TOOL_SLOTS = 9    # tool_7 … tool_9 haben keine Standardtaste, sind aber per Config belegbar
# Farb-Plätze: color_i wählt Feld i der Farbleiste
COLOR_SLOT_KEYS = ("a", "s", "d", "f", "g", "z", "x", "c", "v", "b")
COLOR_SLOTS = 17  # so viele Felder kann die Leiste höchstens haben (8 + 8 + Vordergrund)
# Größen-Stufen: size_i = Strichstärke bzw. Schriftgröße Stufe i
SIZE_SLOT_KEYS = ("a", "s", "d", "f")


def _slots(prefix, count, keys, modifier=""):
    return {f"{prefix}_{i}": (modifier + keys[i - 1] if i <= len(keys) else "")
            for i in range(1, count + 1)}


DEFAULT_KEYS = {
    "undo": "r",
    "redo": "shift+r",
    "color_next": "tab",
    "color_prev": "shift+tab",
    "copy_quit": "return",     # Bild in die Zwischenablage und beenden
    "copy_image": "ctrl+c",    # Bild in die Zwischenablage, offen bleiben
    "save_png": "ctrl+s",
    **_slots("tool", TOOL_SLOTS, TOOL_SLOT_KEYS),
    **_slots("color", COLOR_SLOTS, COLOR_SLOT_KEYS, modifier="shift+"),
    **_slots("size", len(SIZE_SLOT_KEYS), SIZE_SLOT_KEYS, modifier="alt+"),
}

# Nur diese Modifier zählen; z. B. KeypadModifier (Ziffernblock) wird ignoriert
_MODIFIERS = Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier


def parse_shortcut(text):
    """'r', 'shift+r', 'ctrl+z', 'tab' -> QKeyCombination; ungültig -> None."""
    seq = QKeySequence(text.strip())
    if seq.count() != 1 or seq[0].key() == Qt.Key_unknown:
        return None
    return _normalize(seq[0])


def _normalize(combo):
    """Vergleichbare Form: nur relevante Modifier, Shift+Tab statt 'Backtab'."""
    key = combo.key()
    mods = combo.keyboardModifiers() & _MODIFIERS
    if key == Qt.Key_Backtab:  # Qt meldet Shift+Tab als eigene Taste "Backtab"
        key = Qt.Key_Tab
        mods |= Qt.ShiftModifier
    elif key == Qt.Key_Enter:  # Enter am Ziffernblock wie die normale Enter-Taste
        key = Qt.Key_Return
    return QKeyCombination(mods, key)


class KeyMap:
    def __init__(self, config):
        keys_table = config.get("keys") if isinstance(config.get("keys"), dict) else {}
        user = {}  # vom Benutzer gesetzte Einträge: action -> Text

        # Alte Schreibweise [tools] keys = ["a", "s", …] -> tool_1, tool_2, …
        tools_table = config.get("tools") if isinstance(config.get("tools"), dict) else {}
        legacy = tools_table.get("keys")
        if isinstance(legacy, list):
            for i, text in enumerate(legacy, start=1):
                if isinstance(text, str):
                    user[f"tool_{i}"] = text

        for action, text in keys_table.items():
            if action not in DEFAULT_KEYS:
                print(f"[keys] Unbekannte Aktion: {action!r}", file=sys.stderr)
            elif not isinstance(text, str):
                print(f"[keys] {action}: Wert muss Text sein, nicht {text!r}", file=sys.stderr)
            else:
                user[action] = text

        self.texts = {}     # action -> Tastentext (für Anzeigen)
        self._lookup = {}   # Taste (als Zahl) -> action
        # Erst die Einträge des Benutzers, dann die Standardwerte: bei doppelter
        # Belegung gewinnt, was ausdrücklich in der Config steht
        ordered = [(a, user[a], True) for a in user] + [
            (a, t, False) for a, t in DEFAULT_KEYS.items() if a not in user
        ]
        for action, text, from_config in ordered:
            if not text.strip():
                continue  # bewusst ohne Taste
            combo = parse_shortcut(text)
            if combo is None:
                if not from_config:
                    continue
                default = DEFAULT_KEYS[action]
                print(f"[keys] {action}: ungültige Taste {text!r}, nehme {default or 'keine'!r}",
                      file=sys.stderr)
                if not default:
                    continue
                text, combo = default, parse_shortcut(default)
            code = combo.toCombined()
            if code in self._lookup:
                print(f"[keys] {text!r} ist doppelt belegt: {self._lookup[code]} behält sie, "
                      f"{action} hat keine Taste", file=sys.stderr)
                continue
            self._lookup[code] = action
            self.texts[action] = text

    def action_for(self, event):
        """Aktion für ein QKeyEvent oder None."""
        return self._lookup.get(_normalize(event.keyCombination()).toCombined())

    def label(self, action):
        """Kurzer Anzeigetext, z. B. 'A' oder 'Shift+T'; '' wenn ohne Taste."""
        text = self.texts.get(action)
        return QKeySequence(text).toString() if text else ""
