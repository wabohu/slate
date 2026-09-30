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
- Jedes Zeichenobjekt ist ein `QGraphicsPathItem`. Das macht Verschieben, Ändern und Löschen später einfach
- Werkzeuge: `Tool`-Enum, Tastenbelegung in `TOOL_KEYS`, Geometrie in `shape_path()`. Ein neues Werkzeug braucht genau diese drei Stellen
- Undo läuft aktuell über eine Liste `items_drawn`. Bei komplexeren Aktionen (Bearbeiten, Verschieben) auf `QUndoStack` umstellen

## Bedienung (aktueller Stand)
- Tasten 1-5: Freihand, Linie, Pfeil, Rechteck, Ellipse
- Strg+Z: Undo, Esc: beenden

## Konventionen
- Kleine, lauffähige Schritte. Nach jedem Schritt muss das Programm starten
- Code bleibt lesbar und in getrennten Bereichen bzw. Dateien: Capture, Zeichenlogik/Canvas, UI, Export
- Tastenkürzel müssen auf einem deutschen Tastaturlayout funktionieren
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
4. [ ] Farbauswahl mit Farben aus meiner Alacritty-Config
5. [ ] Text-Werkzeug
6. [ ] Strichstärke, Redo
7. [ ] Ausgabe: Zwischenablage und PNG speichern
8. [ ] Globaler Hotkey / Autostart
9. [ ] Extras: nummerierte Marker, Unschärfe, Bereichsauswahl, Tray-Icon
