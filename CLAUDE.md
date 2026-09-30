# Projekt: Screenshot-Annotationstool

Selbstgebaute Variante von Epic Pen / Tekapoint für Linux. Ein Screenshot des Monitors wird eingefroren im Vollbild angezeigt, darauf wird mit Formen und Text markiert. Ziel ist ein Tool, das ich selbst gut anpassen und erweitern kann. Nebenbei ist das Projekt mein Einstieg ins Vibe Coding.

## Umgebung
- Arch Linux, X11 (kein Wayland), Window-Manager: herbstluftwm
- Terminal: Alacritty (Config in TOML)
- Python 3 + PySide6 (Qt6). Abhängigkeiten über pacman (`python-pyside6`), keine pip-Pakete ohne Rückfrage
- Ich habe eine funktionierende X11-Desktop-Session. Du selbst kannst die GUI nicht starten. Sag mir, wie ich testen soll, und ich melde mich mit dem Ergebnis

## Architektur
- Der Screenshot wird per `QScreen.grabWindow(0)` aufgenommen, bevor das Fenster erscheint
- Anzeige in einem rahmenlosen Vollbildfenster (`QGraphicsView`) mit `QGraphicsScene`
- Jedes Zeichenobjekt ist ein `QGraphicsPathItem`, Text ein `QGraphicsTextItem` (bringt Cursor und Eingabe mit). Das macht Verschieben, Ändern und Löschen später einfach
- Werkzeuge: `Tool`-Enum, Geometrie in `shape_path()`, Symbol für die Werkzeugleiste in `tool_icon()`. Welche Taste welches Werkzeug wählt, bestimmen `[tools] order` und `[tools] keys` in der Config (Fallback: Enum-Reihenfolge und `DEFAULT_TOOL_KEYS`). Neue Werkzeuge erscheinen nur dann automatisch, wenn die Config keine eigene Reihenfolge hat. Mehr Werkzeuge als Tasten sind per Tastatur nicht erreichbar
- Eigene Config: `~/.config/annotate/config.toml`, gelesen in `config.py`, Vorlage in `config.example.toml`. Farbwerte kommen aus Alacritty (`colors.py`), Auswahl, Reihenfolge und Startwert von Farben und Werkzeugen aus der eigenen Config
- Undo/Redo über `QUndoStack`. Jede Änderung an der Szene ist ein `QUndoCommand` in `commands.py` und wird per `undo_stack.push()` abgelegt, nie direkt ausgeführt, sonst fehlt sie im Undo

## Bedienung (aktueller Stand)
- Tasten A S D F G T: Werkzeuge in der Reihenfolge der Config, auch per Klick auf die Werkzeugleiste über der Farbleiste (Standard: Freihand, Linie, Pfeil, Rechteck, Ellipse, Text)
- Text: klicken und tippen, Esc oder Klick daneben beendet die Eingabe. Vorhandenen Text ziehen = verschieben, Doppelklick = bearbeiten
- Shift+A S D F G Z X C V B: Farbe (Reihenfolge der Farbleiste), Tab/Shift+Tab blättern
- R: Undo, Shift+R: Redo (`[keys] undo/redo`), Esc: beenden

## Konventionen
- Kleine, lauffähige Schritte. Nach jedem Schritt muss das Programm starten
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
- herbstluftwm ist ein Tiling-WM. Aktuell funktioniert `showFullScreen()` bei mir. Falls ein Fenster verschwindet, ist Plan B das Flag `Qt.X11BypassWindowManagerHint` plus `grabKeyboard()`
- Bei HiDPI kann der Screenshot skalierungsbedingt unscharf sein (Device-Pixel-Ratio des Pixmaps beachten)

## Roadmap
1. [x] Screenshot als Vollbild-Hintergrund
2. [x] Freihandzeichnen
3. [x] Werkzeugwechsel: Linie, Pfeil, Rechteck, Ellipse
4. [x] Farbauswahl mit Farben aus meiner Alacritty-Config
5. [x] Text-Werkzeug
6. [ ] Strichstärke (Redo ist erledigt)
7. [ ] Ausgabe: Zwischenablage und PNG speichern
8. [ ] Globaler Hotkey / Autostart
9. [ ] Extras: nummerierte Marker, Unschärfe, Bereichsauswahl, Tray-Icon
10. [ ] Verlauf wie bei Tekapoint: jeden Screenshot automatisch speichern und per Tastenkombination wieder aufrufen. Offene Fragen, vor dem Start klären:
    - Inhalt: bearbeitbar (Screenshot + Annotationen als Objekte, z. B. JSON, plus PNG-Vorschau), nur fertiges Bild (flaches PNG) oder nur Roh-Screenshot?
    - Aufruf: im laufenden Tool vor/zurück blättern, Übersicht mit Vorschaubildern, globaler Hotkey von außen (hängt an Punkt 8)? Kombination möglich
    - Aufbewahrung: letzte N, nach Alter (Tage) oder unbegrenzt? Wert in der Config
    - Zeitpunkt: Start + Beenden, nach jeder Änderung (absturzsicher) oder nur beim Beenden? Leere Sessions ohne Annotationen speichern?
    - Speicherort: z. B. `~/.local/share/annotate/` (XDG), in der Config änderbar?
    - Beziehung zu Punkt 7: Ist das automatische Speichern zugleich „PNG speichern“ oder bleibt das ein eigener Export?
