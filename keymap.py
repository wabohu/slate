"""Zentrale Tastenbelegung: Aktion -> Taste, mit Overrides aus der Config.

Jede Aktion hat einen Namen (z. B. "undo", "tool_1", "color_3") und eine
Standardtaste. In der Config überschreibt [keys] einzelne Einträge:

    [keys]
    undo = "r"
    tool_6 = "t"
    color_next = ""      # leer = Aktion ohne Taste
    delete = ["delete", "backspace"]   # Liste = mehrere Tasten für eine Aktion

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
    "tool_select": "w",
    "select_all": "ctrl+a",    # alles auswählen (Auswahl-Werkzeug)
    "raise": "ctrl+up",               # Auswahl einen Schritt nach vorne
    "lower": "ctrl+down",             # Auswahl einen Schritt nach hinten
    "raise_top": "ctrl+shift+up",     # Auswahl ganz nach vorne
    "lower_bottom": "ctrl+shift+down",  # Auswahl ganz nach hinten
    "tool_blur": "z",          # Unschärfe (verpixeln), nur Screenshot-Modus
    "tool_marker": "c",        # Marker; erneut c: 1 2 3 / A B C umschalten
    "crop": "y",               # Ausschnitt aufziehen (Esc dabei: aufheben), nur Screenshot-Modus
    "delete": ("delete", "backspace"),  # ausgewähltes Element löschen
    "undo": "r",
    "redo": "shift+r",
    "color_next": "tab",
    "color_prev": "shift+tab",
    "copy_quit": "return",     # Bild in die Zwischenablage und beenden
    "copy_path_quit": "shift+return",  # speichern (wie Strg+S), absoluten Pfad kopieren, beenden
    "copy_image": "ctrl+c",    # Bild in die Zwischenablage, offen bleiben
    "zoom_reset": "ctrl+0",    # Whiteboard: Zoom auf 100 %
    "overview": "ctrl+w",      # Whiteboard: ganzes Dokument ins Fenster einpassen
    "background_next": "ctrl+b",        # Whiteboard: nächster Hintergrund aus [board] backgrounds
    "background_prev": "ctrl+shift+b",  # Whiteboard: voriger Hintergrund
    # Auswahl verschieben (Schrittweiten in [move]); Shift = feine Schritte
    "move_left": "h", "move_down": "j", "move_up": "k", "move_right": "l",
    "move_left_fine": "shift+h", "move_down_fine": "shift+j",
    "move_up_fine": "shift+k", "move_right_fine": "shift+l",
    "quit": "ctrl+q",          # beenden (im Whiteboard die einzige Taste dafür, Esc schließt dort nicht)
    "save": "ctrl+s",          # bearbeitbare Zeichnung (PNG mit eingebetteten Daten)
    "export_png": "ctrl+e",    # sauberes PNG ohne Bearbeitungsdaten
    "history_prev": "left",    # Verlauf: älterer Screenshot (nur Screenshot-Modus)
    "history_next": "right",   # Verlauf: neuerer Screenshot
    "help": "shift+?",         # Übersicht aller Tastenkürzel (? = Shift+/ auf US-Layout)
    "toggle_bar": "b",         # Leiste ein-/ausblenden
    "spotlight": "e",          # Zeigen: Spotlight an/aus (alles abgedunkelt außer um die Maus)
    "magnifier": "shift+e",    # Zeigen: Lupe an/aus
    **_slots("tool", TOOL_SLOTS, TOOL_SLOT_KEYS),
    **_slots("color", COLOR_SLOTS, COLOR_SLOT_KEYS, modifier="shift+"),
    **_slots("size", len(SIZE_SLOT_KEYS), SIZE_SLOT_KEYS, modifier="alt+"),
}

# Umbenannte Aktionen: Hinweis statt "unbekannt", der alte Eintrag wird ignoriert
LEGACY_ACTIONS = {
    "save_png": "heißt jetzt export_png (Standard Strg+E); Strg+S speichert die bearbeitbare Zeichnung",
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


def _as_list(value):
    """'r' -> ['r'], ('del', 'backspace') -> ['del', 'backspace']"""
    return [value] if isinstance(value, str) else list(value)


class KeyMap:
    def __init__(self, config):
        keys_table = config.get("keys") if isinstance(config.get("keys"), dict) else {}
        user = {}  # vom Benutzer gesetzte Einträge: action -> Text oder Liste von Texten

        # Alte Schreibweise [tools] keys = ["a", "s", …] -> tool_1, tool_2, …
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
                print(f"[keys] Unbekannte Aktion: {action!r}", file=sys.stderr)
            elif not (isinstance(value, str)
                      or isinstance(value, list) and all(isinstance(v, str) for v in value)):
                print(f"[keys] {action}: Wert muss Text oder Liste von Texten sein, nicht {value!r}",
                      file=sys.stderr)
            else:
                user[action] = value

        self.texts = {}     # action -> erster Tastentext (für Anzeigen)
        self.all_texts = {}  # action -> alle Tastentexte (für die Tastenübersicht)
        self._lookup = {}   # Taste (als Zahl) -> action
        # Erst die Einträge des Benutzers, dann die Standardwerte: bei doppelter
        # Belegung gewinnt, was ausdrücklich in der Config steht
        ordered = [(a, user[a], True) for a in user] + [
            (a, t, False) for a, t in DEFAULT_KEYS.items() if a not in user
        ]
        for action, value, from_config in ordered:
            for text in _as_list(value):
                if not text.strip():
                    continue  # bewusst ohne Taste
                combo = parse_shortcut(text)
                if combo is None:
                    print(f"[keys] {action}: ungültige Taste {text!r}, wird ignoriert", file=sys.stderr)
                    continue
                self._bind(action, text, combo)
            # Hat der Benutzer nur Ungültiges eingetragen, bleibt der Standard
            if from_config and action not in self.texts:
                for text in _as_list(DEFAULT_KEYS[action]):
                    if text and (combo := parse_shortcut(text)) is not None:
                        print(f"[keys] {action}: nehme Standard {text!r}", file=sys.stderr)
                        self._bind(action, text, combo)

    def _bind(self, action, text, combo):
        code = combo.toCombined()
        if code in self._lookup:
            print(f"[keys] {text!r} ist doppelt belegt: {self._lookup[code]} behält sie, "
                  f"{action} hat sie nicht", file=sys.stderr)
            return
        self._lookup[code] = action
        self.texts.setdefault(action, text)
        self.all_texts.setdefault(action, []).append(text)

    def action_for(self, event):
        """Aktion für ein QKeyEvent oder None."""
        return self._lookup.get(_normalize(event.keyCombination()).toCombined())

    def label(self, action):
        """Kurzer Anzeigetext, z. B. 'A' oder 'Shift+T'; '' wenn ohne Taste."""
        text = self.texts.get(action)
        return QKeySequence(text).toString() if text else ""

    def labels(self, action):
        """Anzeigetexte aller Tasten einer Aktion, z. B. ['Del', 'Backspace']."""
        return [QKeySequence(text).toString() for text in self.all_texts.get(action, [])]
