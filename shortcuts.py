"""Inhalt der Tastenübersicht (?): welche Taste was tut, nach Gruppen.

sections() liefert alles als Listen (Gruppe -> Tasten, Beschreibung); overview() ordnet es
für das Panel (ui.HelpPanel): Werkzeuge, Farben und Größen als Bildzeile, der Rest als Listen.
Tasten werden klein geschrieben (a s d, strg+s), Modifier und Namen wie in der Doku.

Die Tasten kommen aus der KeyMap, also mit den eigenen Belegungen aus [keys] und der
Werkzeug-Reihenfolge aus [tools] order. Angezeigt wird nur, was im aktuellen Modus
(Screenshot oder Whiteboard) gilt. Das Panel selbst zeichnet ui.HelpPanel.

Neue Aktion in keymap.DEFAULT_KEYS = hier eine Beschreibung in DESCRIPTIONS
(tests/test_settings.py prüft, dass keine fehlt).
"""
import re

SCREENSHOT, BOARD = "screenshot", "board"
BOTH = (SCREENSHOT, BOARD)

# Aktion -> (Gruppe, Beschreibung, Modi). Werkzeug-, Farb- und Größenplätze und die
# hjkl-Tasten werden zusammengefasst (siehe sections) und stehen darum nicht einzeln hier.
DESCRIPTIONS = {
    "tool_select": ("Werkzeuge", "Auswahl", BOTH),
    "tool_marker": ("Werkzeuge", "Marker (nochmal: 1 2 3 / A B C)", BOTH),
    "tool_blur": ("Werkzeuge", "Unschärfe", (SCREENSHOT,)),
    "color_next": ("Farbe und Größe", "Farbe weiter", BOTH),
    "color_prev": ("Farbe und Größe", "Farbe zurück", BOTH),
    "delete": ("Auswahl", "löschen", BOTH),
    "undo": ("Allgemein", "Rückgängig", BOTH),
    "redo": ("Allgemein", "Wiederholen", BOTH),
    "copy_quit": ("Ausgabe", "Bild kopieren und beenden", (SCREENSHOT,)),
    "copy_path_quit": ("Ausgabe", "speichern, Pfad kopieren, beenden", (SCREENSHOT,)),
    "copy_image": ("Ausgabe", "Bild kopieren", BOTH),
    "save": ("Ausgabe", "bearbeitbar speichern", BOTH),
    "export_png": ("Ausgabe", "sauberes PNG exportieren", BOTH),
    "crop": ("Ausgabe", "Ausschnitt festlegen (dabei Esc: aufheben)", (SCREENSHOT,)),
    "quit": ("Allgemein", "beenden", BOTH),
    "help": ("Allgemein", "diese Übersicht", BOTH),
    "toggle_bar": ("Allgemein", "Leiste ein/aus", BOTH),
    "spotlight": ("Zeigen", "Spotlight an/aus", BOTH),
    "magnifier": ("Zeigen", "Lupe an/aus", BOTH),
    "zoom_reset": ("Ansicht", "Zoom 100 %", (BOARD,)),
    "overview": ("Ansicht", "Übersicht / zurück", (BOARD,)),
    "background_next": ("Ansicht", "Hintergrund hell/dunkel", (BOARD,)),
    "background_prev": ("Ansicht", "Hintergrund zurück", (BOARD,)),
    "history_prev": ("Verlauf", "älterer Screenshot", (SCREENSHOT,)),
    "history_next": ("Verlauf", "neuerer Screenshot", (SCREENSHOT,)),
}
# Zusammengefasst in sections()
GROUPED = re.compile(r"^(tool|color|size)_\d+$|^move_(left|down|up|right)(_fine)?$")

# Feste Bedienung ohne Eintrag in der Tastentabelle: (Gruppe, Taste/Maus, Beschreibung, Modi)
FIXED = [
    ("Allgemein", "Esc", "Zeigen aus, Auswahl aufheben, sonst beenden", (SCREENSHOT,)),
    ("Allgemein", "Esc", "Zeigen aus, Auswahl aufheben", (BOARD,)),
    ("Maus", "Ziehen", "zeichnen mit dem Werkzeug", BOTH),
    ("Maus", "Klick (Auswahl)", "auswählen, ziehen = verschieben", BOTH),
    ("Maus", "Griffe ziehen", "Größe ändern", BOTH),
    ("Maus", "Doppelklick (Auswahl)", "Text bearbeiten / neuer Text", BOTH),
    ("Maus", "Alt+Mausrad", "Größe fein", BOTH),
    ("Maus", "Mausrad, mittlere Taste", "Ansicht verschieben", (BOARD,)),
    ("Maus", "Strg+Mausrad", "zoomen", (BOARD,)),
]

# Tastennamen wie in docs/bedienung.md (Qt schreibt sie englisch)
KEY_NAMES = {"Ctrl": "Strg", "Return": "Enter", "Del": "Entf", "Left": "←", "Right": "→",
             "Up": "↑", "Down": "↓", "Shift+?": "?", "Meta": "Super"}

GROUP_ORDER = ["Werkzeuge", "Farbe und Größe", "Auswahl", "Zeigen", "Ausgabe", "Ansicht", "Verlauf", "Allgemein",
               "Maus"]


def display(label):
    """Qt-Tastentext in die Schreibweise der Übersicht, z. B. 'Ctrl+Return' -> 'strg+enter'."""
    if label in KEY_NAMES:
        return KEY_NAMES[label].lower()
    if label == "+":
        return label
    return "+".join(KEY_NAMES.get(part, part) for part in label.split("+")).lower()


def split_common(labels):
    """['shift+a', 'shift+s'] -> ('shift', ['a', 's']); ohne gemeinsamen Modifier ('', labels)."""
    prefixes = {label.rpartition("+")[0] for label in labels if label}
    if len(prefixes) == 1 and (prefix := prefixes.pop()):
        return prefix, [label.rpartition("+")[2] for label in labels]
    return "", list(labels)


def combine(labels):
    """['Shift+A', 'Shift+S'] -> 'Shift+A S'; gemischte Modifier einzeln mit Komma."""
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
    """[(Gruppe, [(Tasten, Beschreibung), …]), …] für den aktuellen Modus."""
    mode = BOARD if board else SCREENSHOT
    groups = {name: [] for name in GROUP_ORDER}

    def add(group, keys, text):
        if keys:
            groups.setdefault(group, []).append((keys, text))

    def keys(action):
        """Alle Tasten einer Aktion, z. B. 'Entf, Backspace'."""
        return ", ".join(display(label) for label in keymap.labels(action))

    for i, tool in enumerate(tools, start=1):
        add("Werkzeuge", keys(f"tool_{i}"), tool.value)
    add("Farbe und Größe", combine([keymap.label(f"color_{i}") for i in range(1, color_count + 1)]),
        "Farbe aus der Leiste")
    add("Farbe und Größe", combine([keymap.label(f"size_{i}") for i in range(1, size_count + 1)]),
        "Größe in Stufen")
    directions = ("left", "down", "up", "right")
    add("Auswahl", combine([keymap.label(f"move_{d}") for d in directions]), "verschieben")
    add("Auswahl", combine([keymap.label(f"move_{d}_fine") for d in directions]), "fein verschieben")

    for action, (group, text, modes) in DESCRIPTIONS.items():
        if mode in modes:
            add(group, keys(action), text)
    for action in keymap.texts:  # Aktionen ohne Beschreibung nie verschweigen
        if action not in DESCRIPTIONS and not GROUPED.match(action):
            add("Allgemein", keys(action), action)
    for group, fixed_keys, text, modes in FIXED:
        if mode in modes:
            add(group, fixed_keys.lower(), text)  # klein wie die übrigen Tasten
    # Werkzeuge: Auswahl zuerst, wie in der Leiste
    groups["Werkzeuge"].sort(key=lambda entry: entry[1] != "Auswahl")
    return [(name, entries) for name, entries in groups.items() if entries]


# Gruppen, die overview() als Bildzeile bzw. eigene Spalte zeigt statt als Liste rechts
PICTURE_GROUPS = ("Werkzeuge", "Farbe und Größe", "Maus")


def overview(keymap, tools, color_count, size_count, board):
    """Daten für das Panel (Entwurf D):
    tools: [(Tool, Tasten)] mit Auswahl vorne; colors / sizes: Tasten je Feld bzw. Stufe;
    color_hint / size_hint: Überschrift-Zusatz (gemeinsamer Modifier, Blättern, Mausrad);
    mouse: [(Maus, Beschreibung)]; lists: [(Gruppe, [(Tasten, Beschreibung)])] für rechts."""
    from tools import Tool  # hier, damit das Modul ohne Qt importierbar bleibt

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
                                       f"{browse} blättert" if browse else "") if x)
    size_hint = ", ".join(x for x in (f"{size_prefix} + …" if size_prefix else "", "alt+mausrad fein") if x)
    groups = sections(keymap, tools, color_count, size_count, board)
    return {
        "tools": tool_keys,
        "colors": colors, "color_hint": color_hint,
        "sizes": sizes, "size_hint": size_hint,
        "mouse": dict(groups).get("Maus", []),
        "lists": [(name, entries) for name, entries in groups if name not in PICTURE_GROUPS],
    }
