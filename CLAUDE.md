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
- Farben der Oberfläche: `ui.Theme` (Hintergrund, Vordergrund, Deckkraft), Standard aus Alacritty `colors.primary`, änderbar in `[ui]`. Neue UI-Elemente nehmen ihre Farben aus dem Theme, nie fest verdrahtet
- Eigene Config: `~/.config/annotate/config.toml`, gelesen in `config.py`, Vorlage in `config.example.toml`. Farbwerte kommen aus Alacritty (`colors.py`), Auswahl, Reihenfolge und Startwert von Farben und Werkzeugen aus der eigenen Config
- Tasten zentral in `keymap.py`: `DEFAULT_KEYS` (Aktion → Taste), Overrides aus `[keys]` der Config (alte Schreibweise `[tools] keys` gilt weiter), Handler in `Canvas.actions`. Neue Taste = genau diese zwei Stellen. Tasten passen exakt (Shift+T ist nicht T). Esc ist fest im Code
- Export in `export.py`: Szene ohne Leiste rendern (Ausschnitt = Screenshot-Rechteck), Zwischenablage über `xclip` (hält das Bild auch nach dem Beenden), Fallback Qt-Zwischenablage
- Zwei Modi in einer `Canvas`: Screenshot-Overlay (`show_overlay`, Bypass-Fenster, Keyboard-Grab) und Whiteboard (`board=True`, `show_window`, normales Fenster, sehr große Szene, Szenen-Hintergrund = Farbe, Export = Bereich aller Elemente). Ungespeichert-Erkennung über `QUndoStack.isClean()`/`setClean()`. Alles, was auf dem Bildschirm eine feste Größe haben soll (Griffe, Fangradius, Klick-Toleranz), durch `Canvas.zoom()` teilen
- Speichern/Laden in `document.py`: normales PNG mit den Markierungen, Bearbeitungsdaten als JSON im PNG-Text-Chunk `annotate` (Format/Version, roher Hintergrund als Base64-PNG, Elemente von unten nach oben). Elemente liefern `to_dict()`/`from_dict()`, Farben als `#rrggbb`. Fehlerhafte Daten nie Absturz: Bild als Hintergrund bzw. Element überspringen
- Undo/Redo über `QUndoStack`. Jede Änderung an der Szene ist ein `QUndoCommand` in `commands.py` und wird per `undo_stack.push()` abgelegt, nie direkt ausgeführt, sonst fehlt sie im Undo

## Bedienung (aktueller Stand)
- W: Auswahl-Werkzeug. Element am Rand anklicken (bei ungefüllten Formen zählt nur der Rand, 6 px Toleranz), ziehen = verschieben, Griffe ziehen = Größe ändern (Ecken; bei Linie/Pfeil die Endpunkte; bei Text skaliert die Schrift), Entf/Backspace = löschen, Esc = abwählen, Doppelklick auf Text = bearbeiten, Doppelklick auf leere Stelle = neuer Text. h j k l verschieben die Auswahl (Standard 10 px, mit Shift 1 px, `[move]`), Schritte kurz hintereinander = ein Undo-Schritt. Farbe und Größe wirken auf die Auswahl
- Tasten A S D F G T: Werkzeuge in der Reihenfolge der Config, auch per Klick auf die gemeinsame Leiste unten (Werkzeuge | Farben | Größe, `ui.MainBar`) (Standard: Freihand, Linie, Pfeil, Rechteck, Ellipse, Text)
- Text: klicken und tippen, Esc oder Klick daneben beendet die Eingabe. Vorhandenen Text ziehen = verschieben, Doppelklick = bearbeiten
- Shift+A S D F G Z X C V B: Farbe (Reihenfolge der Farbleiste), Tab/Shift+Tab blättern
- Alt+A S D F: Größe in Stufen 1-4 (Strichstärke bzw. Schriftgröße, `[size]` in der Config)
- Alt+Mausrad: Größe fein einstellen (Text ±2 px, Strich ±1 px pro Raste), für Auswahl oder gerade getippten Text. Rasten kurz hintereinander = ein Undo-Schritt (`PropertyCommand` mit `mergeWith`)
- Enter: Bild in die Zwischenablage und beenden, Strg+C: nur kopieren
- Strg+S: bearbeitbare Zeichnung speichern (PNG mit eingebetteten Daten, erst neue Datei in `[output] dir`, danach dieselbe überschreiben), Strg+E: sauberes PNG exportieren
- `python annotate.py bild.png`: gespeicherte Zeichnung wieder öffnen (alles bearbeitbar) oder beliebiges PNG als Hintergrund
- `python annotate.py --board`: Whiteboard in einem normalen Fenster (Hintergrund `[board] background`). Esc und Enter schließen dort nicht, Strg+Q bzw. Fenster schließen fragt bei ungespeicherten Änderungen. Gespeicherte Whiteboards (`…_board.png`) öffnen sich automatisch wieder als Whiteboard. Mausrad = Ansicht verschieben (Shift/Kipprad/Touchpad: seitlich), mittlere Maustaste ziehen = verschieben, Strg+Mausrad = Zoom zur Maus (10–800 %, 7 % pro Raste), Strg+0 = 100 %, Strg+W = Übersicht (alles einpassen, höchstens 100 %), erneut Strg+W = zurück zur Ansicht davor, solange in der Übersicht nicht gezoomt/verschoben wurde. Strg+B / Strg+Shift+B = Hintergrund weiter/zurück aus `[board] backgrounds` (Undo-Schritt über `Canvas.set_board_color`, wird mitgespeichert)
- Strg+Q: beenden
- R: Undo, Shift+R: Redo, Esc: beenden. Alle Tasten außer Esc in `[keys]` änderbar, siehe `config.example.toml`

## Konventionen
- Kleine, lauffähige Schritte. Nach jedem Schritt muss das Programm starten
- Vor jedem Commit `python tests/regress.py` und `python tests/test_document.py` (Speichern, Laden, Weiterbearbeiten) (zeichnet ohne Bildschirm eine feste Szene und vergleicht mit `tests/regress_reference.png`). Ändert sich die Optik absichtlich, Referenz mit `--update` neu schreiben und das im Commit erwähnen
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

## Roadmap
1. [x] Screenshot als Vollbild-Hintergrund
2. [x] Freihandzeichnen
3. [x] Werkzeugwechsel: Linie, Pfeil, Rechteck, Ellipse
4. [x] Farbauswahl mit Farben aus meiner Alacritty-Config
5. [x] Text-Werkzeug
6. [x] Strichstärke und Redo (Strichstärke als Größen-Stufen, gilt auch für Text)
7. [x] Ausgabe: Zwischenablage (Enter, Strg+C) und PNG speichern (Strg+S)
8. [x] Globaler Hotkey: sxhkd (`~/.config/herbstluftwm/keybindings.sxhkd`), Alt+Escape = Screenshot, Alt+Delete = Whiteboard, beide über `~/.local/bin/annotate-board`
9. [ ] Extras: nummerierte Marker, Unschärfe, Bereichsauswahl, Tray-Icon
10. [ ] Verlauf wie bei Tekapoint: jeden Screenshot automatisch speichern und per Tastenkombination wieder aufrufen. Offene Fragen, vor dem Start klären:
    - Inhalt: bearbeitbar (Screenshot + Annotationen als Objekte, z. B. JSON, plus PNG-Vorschau), nur fertiges Bild (flaches PNG) oder nur Roh-Screenshot?
    - Aufruf: im laufenden Tool vor/zurück blättern, Übersicht mit Vorschaubildern, globaler Hotkey von außen (hängt an Punkt 8)? Kombination möglich
    - Aufbewahrung: letzte N, nach Alter (Tage) oder unbegrenzt? Wert in der Config
    - Zeitpunkt: Start + Beenden, nach jeder Änderung (absturzsicher) oder nur beim Beenden? Leere Sessions ohne Annotationen speichern?
    - Speicherort: z. B. `~/.local/share/annotate/` (XDG), in der Config änderbar?
    - Teilweise geklärt: Speicherformat ist das bearbeitbare PNG aus `document.py` (Strg+S). Offen: automatisch bei jedem Screenshot speichern, Aufruf, Aufbewahrung
11. [x] Leere Zeichenfläche für Diagramme (Ersatz für Excalidraw): `--board`, normales gekacheltes Fenster, unendliche Fläche, Mausrad/mittlere Maustaste verschieben, Strg+Mausrad Zoom, Strg+W Übersicht, Speichern/Laden als `_board.png`, Hintergrund aus Alacritty
12. [ ] (Schritt 1 erledigt: auswählen, verschieben, löschen, umfärben, Größe; Schritt 2 erledigt: Griffe zum Größe ändern) Auswahl-Werkzeug für alle Elemente: anklicken, verschieben, löschen (Entf), Farbe nachträglich ändern (Element auswählen, Farbe wählen). Später: Mehrfachauswahl, Größe ändern, Drehen, Strichstärke nachträglich ändern, Kopieren/Einfügen, Vorder-/Hintergrund. Das Verschieben von Text im Text-Werkzeug geht dann darin auf. Drehen nur, wenn die Bedienung übersichtlich bleibt (z. B. Tasten in festen Schritten oder ein Griff an der Auswahl)
13. [ ] Leisten-Layout: Platz für weitere Leisten (Strichstärke, Füllung, Modi …), siehe D3
14. [ ] Vorlagen, vielleicht: kleine Bibliothek vorgefertigter Elemente wie in draw.io, aber viel einfacher. Symbole (Haken, Kreuz, Warnung …), Tabellen, zusammengesetzte Elemente. Idee: Eine Vorlage ist einfach eine gespeicherte Elementgruppe im selben Format wie D1, eigene Vorlagen entstehen durch „Auswahl als Vorlage speichern“. Symbole als Pfade statt Bilddateien, damit sie umfärbbar bleiben. Tabellen sind der aufwendigste Teil (Zellen bearbeiten, Zeilen/Spalten hinzufügen), darum zuletzt
15. [ ] Diagramm-Grundlagen: Text in Formen (Doppelklick auf Form = beschriften), Verbinder-Pfeile, die an Formen andocken und mitwandern (siehe D5)
16. [ ] Idee für später: weitere Schriften für das Text-Werkzeug, z. B. eine Monospace-Schrift (für Code, Befehle, Pfade). Naheliegend: die Schrift aus der Alacritty-Config (`[font.normal] family`) als Monospace-Standard. Datenmodell: `TextElement` bräuchte ein Feld `font` (in `to_dict`, fehlt es beim Laden = bisherige Schrift, also abwärtskompatibel). Offen: Umschalten per Taste oder Leiste, welche Schriften, fett/normal
17. [x] Meldungen per dunst, Nachfragen („Speichern?“ beim Schließen des Whiteboards) per rofi mit Fuzzy-Eingabe, beides per `[ui]` abschaltbar (Qt-Fallback). Später evtl.: Qt-Dialog per Stylesheet an `ui.Theme` anpassen
18. [x] Hintergrundfarbe im laufenden Whiteboard ändern: Strg+B / Strg+Shift+B blättert durch `[board] backgrounds` (Standard: Alacritty-Hintergrund, Papierweiß, helles Grau), Undo-Schritt, wird mitgespeichert. Nur im Whiteboard. Offen: bei hellem Hintergrund passen helle Palettenfarben schlecht, evtl. Leistenfarben/Kontrast mitdenken
19. [x] Text per Doppelklick anlegen (im Auswahl-Werkzeug), ohne vorher T zu drücken. Empfehlung: im Auswahl-Werkzeug Doppelklick auf leere Stelle = neuer Text dort (wie Excalidraw); auf Text = bearbeiten (gibt es schon); auf Form = beschriften (Punkt 15)
    - In Zeichenwerkzeugen eher nicht: Qt meldet den Doppelklick erst nach dem ersten Klick, Freihand hat dann schon einen Punkt gezeichnet (müsste samt Undo-Schritt wieder weg), und zwei schnelle Freihand-Punkte würden ungewollt zu Text. Linie/Rechteck/Ellipse wären unkritisch (Klick ohne Ziehen wird verworfen)
    - Entschieden: nur im Auswahl-Werkzeug

## Offene Designentscheidungen
Betreffen mehrere Roadmap-Punkte, darum vor dem jeweils ersten klären.
- **D1 Datenmodell (Schritt 1 erledigt):** Formen (`ShapeElement`) und Text (`TextElement`) kennen ID, Art, Geometrie in lokalen Koordinaten, Farbe und Strichstärke bzw. Schriftgröße; Lage über `pos()`/`rotation()`. Schritt 2 erledigt: Speicherformat (PNG mit eingebettetem JSON, `document.py`). Offen: Gruppen über `QGraphicsItemGroup` für Vorlagen, Bezüge per ID für Verbinder. Plan in `docs/plan-datenmodell.md`
- **D2 Treffer beim Anklicken (entschieden, umgesetzt):** Nur der Rand: `ShapeElement.shape()` ist nur der Strich. Die Toleranz (`HIT_TOLERANCE`, 6 Bildschirm-Pixel) gibt `Canvas.element_at()` dazu, indem es in einem kleinen Quadrat um den Klick sucht; so bleibt sie beim Zoomen gleich. Gefüllte Formen (später) sollen auch innen treffen
- **D3 Leisten (entschieden):** Variante A, eine gemeinsame Leiste unten mittig (Werkzeuge | Farben | Stärke | Füllung), Position per Config, B blendet aus, Vorlagen als Popup. Details in `docs/plan-bedienung.md`
- **D4 Tasten (entschieden):** Belegung und Grundsätze in `docs/plan-bedienung.md`. Wichtig: Eigenschaften (Farbe, Stärke, Füllung, Schriftgröße) wirken auf die Auswahl, sonst auf neue Elemente. Strichstärke Alt+A S D F. Nächster Schritt: zentrale Tabelle „Aktion → Taste“ mit Config
- **D5 Diagramm-Umfang (entschieden):** Ja zu Text in Formen (Beschriftung im Rechteck, wandert mit) und ja zu Pfeilen, die an Formen „kleben“ und beim Verschieben mitgehen (Verbinder wie in Excalidraw/draw.io). Folge für D1: Elemente brauchen feste IDs, Beschriftungen gehören zu ihrer Form (Kind-Item), Verbinder speichern die IDs ihrer Start-/Zielform und berechnen sich neu, wenn sich diese bewegen
