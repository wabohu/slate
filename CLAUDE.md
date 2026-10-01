# Projekt: Screenshot-Annotationstool

Selbstgebaute Variante von Epic Pen / Tekapoint für Linux. Ein Screenshot des Monitors wird eingefroren im Vollbild angezeigt, darauf wird mit Formen und Text markiert. Ziel ist ein Tool, das ich selbst gut anpassen und erweitern kann. Nebenbei ist das Projekt mein Einstieg ins Vibe Coding.

## Umgebung
- Arch Linux, X11 (kein Wayland), Window-Manager: herbstluftwm
- Terminal: Alacritty (Config in TOML)
- Python 3 + PySide6 (Qt6). Abhängigkeiten über pacman (`python-pyside6`), keine pip-Pakete ohne Rückfrage
- Ich habe eine funktionierende X11-Desktop-Session. Du selbst kannst die GUI nicht starten. Sag mir, wie ich testen soll, und ich melde mich mit dem Ergebnis

## Architektur
- Der Screenshot wird per `QScreen.grabWindow(0)` aufgenommen, bevor das Fenster erscheint
- Anzeige in einem rahmenlosen Fenster in Monitorgröße (`QGraphicsView`) mit `QGraphicsScene`, am Window-Manager vorbei (`Qt.X11BypassWindowManagerHint`). Tastatur per `grabKeyboard()` ohne `activateWindow()`, die Szene wird von Hand aktiviert (`Canvas.show_overlay()`)
- Auswahl über Qts eingebaute Selektion (`ItemIsSelectable`, `scene.selectedItems()`), vorerst höchstens ein Element. `Canvas.update_bars()` zeigt in der Leiste die Werte der Auswahl. Eigenschaftsänderungen als `PropertyCommand`. Rahmen und Griffe zeichnet `Canvas.drawForeground` (nie im Export); jedes Element liefert dafür `handle_points()`, `drag_handle()`, `geometry()`/`set_geometry()`. Neue Element-Arten brauchen diese vier Methoden
- Formen sind `ShapeElement` (`elements.py`, Unterklasse von `QGraphicsPathItem`): feste `id`, `tool`, `points` in lokalen Koordinaten, `color`, `width`, bei Rechtecken `radius` (Eckenradius, für neue aus `[rect] radius` bzw. `radius_board`, fehlt er beim Laden = 8). Lage nur über `pos()`/`rotation()`, Pfad per `rebuild()` aus den Werten. Text ist ein `TextElement` (Unterklasse von `QGraphicsTextItem`, bringt Cursor und Eingabe mit): `id`, `color`, `font_size`, `start_editing()`/`stop_editing()`. Beide Element-Arten haben `color` und `set_color()`
- Werkzeuge in `tools.py`: `Tool`-Enum, Geometrie in `shape_path()`, Symbol für die Werkzeugleiste in `tool_icon()`. Welche Taste welches Werkzeug wählt, bestimmen `[tools] order` (Position i) und die Aktion `tool_i` in der Tastentabelle. Neue Werkzeuge erscheinen nur dann automatisch, wenn die Config keine eigene Reihenfolge hat. Mehr Werkzeuge als Tasten sind per Tastatur nicht erreichbar
- Meldungen und Nachfragen in `notify.py`: `notify()` per `notify-send` (dunst), `ask()` per `rofi -dmenu` (Fuzzy-Suche, Theme `rofi/annotate.rasi` + `~/.config/rofi/colors.rasi`). In der Canvas nur über `Canvas.report()` (Meldung) und `Canvas.ask()` (gibt im Screenshot-Modus den Keyboard-Grab für rofi frei), nie `toast.show_message()` direkt. Wahl per `[ui] messages = "dunst" | "toast"`, `dialogs = "rofi" | "qt"`; fehlt das Programm oder schlägt es fehl, Qt-Fallback (`ui.Toast`, `QMessageBox`). Ohne Bildschirm (`QT_QPA_PLATFORM=offscreen`, Tests) nie extern
- Grundfarbe und gezeigte Farbe: Elemente speichern ihre Grundfarbe (`color`, aus der Palette). Gezeigt wird `elements.shown_color()`: die Szene passt sie per `Canvas.adapt_color` an, im Whiteboard auf hellem Hintergrund abgedunkelt (`colors.adapt_color`, Kontrast `LIGHT_CONTRAST` 3.0, eigene Werte in `[colors.light]`), sonst unverändert. Elemente bestimmen sie neu in `refresh_color()` (beim Einfügen in die Szene über `itemChange`, nach Hintergrundwechsel über `Canvas.refresh_colors()`, das auch die Farbleiste anpasst). Vergleiche (z. B. aktive Farbe in der Leiste) immer mit der Grundfarbe. Auswahlrahmen und Griffe nehmen von Leisten-Vorder-/Hintergrund den mit mehr Kontrast zum Whiteboard (`Canvas.selection_colors()`)
- Farben der Oberfläche: `ui.Theme` (Hintergrund, Vordergrund, Deckkraft), Standard aus Alacritty `colors.primary`, änderbar in `[ui]`. Neue UI-Elemente nehmen ihre Farben aus dem Theme, nie fest verdrahtet
- Eigene Config: `~/.config/annotate/config.toml`, gelesen in `config.py`, Vorlage in `config.example.toml`. Farbwerte kommen aus Alacritty (`colors.py`), Auswahl, Reihenfolge und Startwert von Farben und Werkzeugen aus der eigenen Config
- Einstellungen in `settings.py`: Standardwerte und Grenzen als Konstanten, `Settings` liest beim Start alles aus der Config, was sich während der Sitzung nicht ändert (Größen-Stufen, Palette, Theme, Schrittweiten …); die Canvas greift über `self.settings` darauf zu. Was sich ändert (Werkzeug, Farbe, Stufe, Whiteboard-Hintergrund), gehört der Canvas und startet mit `settings.default_*`. Neuer Config-Wert = `settings.py` + `config.example.toml` (+ Fall in `tests/test_settings.py`)
- Tasten zentral in `keymap.py`: `DEFAULT_KEYS` (Aktion → Taste), Overrides aus `[keys]` der Config (alte Schreibweise `[tools] keys` gilt weiter), Handler in `Canvas.actions`. Neue Taste = genau diese zwei Stellen. Tasten passen exakt (Shift+T ist nicht T). Esc ist fest im Code
- Export in `export.py`: Szene ohne Leiste rendern (Ausschnitt = Screenshot-Rechteck), Zwischenablage über `xclip` (hält das Bild auch nach dem Beenden), Fallback Qt-Zwischenablage
- Zwei Modi in einer `Canvas`: Screenshot-Overlay (`show_overlay`, Bypass-Fenster, Keyboard-Grab) und Whiteboard (`board=True`, `show_window`, normales Fenster, sehr große Szene, Szenen-Hintergrund = Farbe, Export = Bereich aller Elemente). Ungespeichert-Erkennung über `QUndoStack.isClean()`/`setClean()`. Alles, was auf dem Bildschirm eine feste Größe haben soll (Griffe, Fangradius, Klick-Toleranz), durch `Canvas.zoom()` teilen
- Speichern/Laden in `document.py`: normales PNG mit den Markierungen, Bearbeitungsdaten als JSON im PNG-Text-Chunk `annotate` (Format/Version, roher Hintergrund als Base64-PNG, Elemente von unten nach oben). Elemente liefern `to_dict()`/`from_dict()`, Farben als `#rrggbb`. Fehlerhafte Daten nie Absturz: Bild als Hintergrund bzw. Element überspringen
- Undo/Redo über `QUndoStack`. Jede Änderung an der Szene ist ein `QUndoCommand` in `commands.py` und wird per `undo_stack.push()` abgelegt, nie direkt ausgeführt, sonst fehlt sie im Undo

## Weitere Dokumente
Nicht in jeder Sitzung nötig, bei Bedarf lesen:
- `docs/bedienung.md`: alle Tasten und Mausaktionen (aktueller Stand). Bei neuen oder geänderten Tasten mitpflegen
- `docs/roadmap.md`: Roadmap (nummerierte Punkte, „Roadmap 15“ meint dort Punkt 15) und Designentscheidungen D1–D5. Vor einem neuen Roadmap-Punkt lesen, danach abhaken
- `docs/plan-*.md`: Pläne zu größeren Umbauten (Datenmodell, Bedienung/Leisten, Aufteilung von `annotate.py`)

## Konventionen
- Kleine, lauffähige Schritte. Nach jedem Schritt muss das Programm starten
- Vor jedem Commit alle drei Tests: `python tests/regress.py` (zeichnet ohne Bildschirm eine feste Szene und vergleicht mit `tests/regress_reference.png`), `python tests/test_document.py` (Speichern, Laden, Weiterbearbeiten) und `python tests/test_settings.py` (Config-Werte und Fallbacks). Ändert sich die Optik absichtlich, Referenz mit `--update` neu schreiben und das im Commit erwähnen
- Code bleibt lesbar und in getrennten Bereichen bzw. Dateien: Capture, Zeichenlogik/Canvas, UI, Export
- Tastenkürzel müssen auf dem US-Tastaturlayout funktionieren (`us`, Variante `altgr-intl`)
- Fehlende Konfigurationsdateien oder Werte dürfen nie zum Absturz führen, immer sinnvolle Fallbacks
- Kein großer Umbau ohne Rückfrage. Bestehendes Verhalten nicht ändern, wenn es nicht Teil der Aufgabe ist
- Erkläre neue Qt-Konzepte kurz, ich will den Code verstehen, den ich erweitere
- Sprache im Chat: Deutsch, per Du. Code, Variablennamen und Kommentare dürfen wie bisher gemischt sein, Kommentare bevorzugt Deutsch

## Git
- Nach jedem funktionierenden Meilenstein ein Commit mit aussagekräftiger Nachricht
- Nicht committen, bevor ich bestätigt habe, dass es bei mir läuft

## Bekannte Stolperstellen
- herbstluftwm: Mit `showFullScreen()` flackerte beim Öffnen und Schließen kurz der Desktop-Hintergrund (auch ohne picom, auch mit WM-Regel). Darum läuft das Fenster am WM vorbei. `activateWindow()` nicht aufrufen, sonst hat nach dem Schließen kein Fenster mehr den Fokus. Beim Start per globalem Hotkey (Roadmap 8) prüfen, ob `grabKeyboard()` klappt, solange der Hotkey noch gedrückt ist
- Bei HiDPI kann der Screenshot skalierungsbedingt unscharf sein (Device-Pixel-Ratio des Pixmaps beachten)
- `annotate.py` muss ausführbar bleiben (`755`): `~/.local/bin/annotate-board` ist ein Symlink darauf, sxhkd startet es direkt. Dateien nie als neue Datei schreiben und per `mv` drüberlegen (Rechte gehen verloren), sondern in place ändern; `git diff --summary` zeigt eine `mode change`
