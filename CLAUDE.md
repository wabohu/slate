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
11. [ ] Leere Zeichenfläche für Diagramme (Ersatz für Excalidraw): Start ohne Screenshot, einfarbiger Hintergrund. Offen: Start per Kommandozeilen-Option und/oder Taste? Feste Bildschirmgröße oder unendliche Fläche mit Verschieben/Zoom? Vollbild oder normales (gekacheltes) Fenster? Speichern und wieder öffnen (siehe D1)
12. [ ] Auswahl-Werkzeug für alle Elemente: anklicken, verschieben, löschen (Entf), Farbe nachträglich ändern (Element auswählen, Farbe wählen). Später: Mehrfachauswahl, Größe ändern, Drehen, Strichstärke nachträglich ändern, Kopieren/Einfügen, Vorder-/Hintergrund. Das Verschieben von Text im Text-Werkzeug geht dann darin auf. Drehen nur, wenn die Bedienung übersichtlich bleibt (z. B. Tasten in festen Schritten oder ein Griff an der Auswahl)
13. [ ] Leisten-Layout: Platz für weitere Leisten (Strichstärke, Füllung, Modi …), siehe D3
14. [ ] Vorlagen, vielleicht: kleine Bibliothek vorgefertigter Elemente wie in draw.io, aber viel einfacher. Symbole (Haken, Kreuz, Warnung …), Tabellen, zusammengesetzte Elemente. Idee: Eine Vorlage ist einfach eine gespeicherte Elementgruppe im selben Format wie D1, eigene Vorlagen entstehen durch „Auswahl als Vorlage speichern“. Symbole als Pfade statt Bilddateien, damit sie umfärbbar bleiben. Tabellen sind der aufwendigste Teil (Zellen bearbeiten, Zeilen/Spalten hinzufügen), darum zuletzt
15. [ ] Diagramm-Grundlagen: Text in Formen (Doppelklick auf Form = beschriften), Verbinder-Pfeile, die an Formen andocken und mitwandern (siehe D5)

## Offene Designentscheidungen
Betreffen mehrere Roadmap-Punkte, darum vor dem jeweils ersten klären.
- **D1 Datenmodell:** Formen speichern bisher nur ihren fertigen `QPainterPath`, in Szenen-Koordinaten. Für Umfärben, Größe ändern, Drehen, Speichern/Laden und Vorlagen (Punkte 10, 11, 12, 14) muss jedes Element seine Parameter kennen (Art, Geometrie, Farbe, Strichstärke). Vorschlag: eigene Item-Klasse(n) mit diesen Werten plus JSON-Speicherformat. Dabei die Geometrie relativ zum Element speichern und die Lage über Position + Drehung (`setPos`, `setRotation`); dann kosten Verschieben und Drehen fast nichts. Gruppen (für Vorlagen) über `QGraphicsItemGroup`. Möglichst vor Punkt 12 umsetzen, damit nicht zweimal umgebaut wird
- **D2 Treffer beim Anklicken:** Ein nicht gefülltes Rechteck gilt in Qt auch innen als getroffen. Für Diagramme besser nur der Rand (wie Excalidraw), außer die Form ist gefüllt
- **D3 Leisten:** Aktuell zwei Leisten unten mittig übereinander. Mit Punkt 14 kommt eine Vorlagen-Auswahl dazu (Leiste, Seitenpanel oder Popup per Taste). Optionen: alles in einer Leiste, Werkzeuge oben und Eigenschaften (Farbe, Stärke, Füllung) seitlich wie Excalidraw, Position per Config. Dazu: Leisten per Taste ein-/ausblenden, damit sie auf Screenshots nichts verdecken
- **D4 Tasten:** Ohne Modifier frei sind Q W E, Y U I O P, H J K L, Z X C V B N M sowie Entf (Z X C V B sind nur mit Shift für Farben belegt). Das Auswahl-Werkzeug braucht eine Taste (Excalidraw: V). Viele neue Funktionen konkurrieren um wenige Tasten, darum früh eine Gesamtbelegung planen
- **D5 Diagramm-Umfang (entschieden):** Ja zu Text in Formen (Beschriftung im Rechteck, wandert mit) und ja zu Pfeilen, die an Formen „kleben“ und beim Verschieben mitgehen (Verbinder wie in Excalidraw/draw.io). Folge für D1: Elemente brauchen feste IDs, Beschriftungen gehören zu ihrer Form (Kind-Item), Verbinder speichern die IDs ihrer Start-/Zielform und berechnen sich neu, wenn sich diese bewegen
