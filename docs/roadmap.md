# Roadmap und Designentscheidungen

## Roadmap
1. [x] Screenshot als Vollbild-Hintergrund
2. [x] Freihandzeichnen
3. [x] Werkzeugwechsel: Linie, Pfeil, Rechteck, Ellipse
4. [x] Farbauswahl mit Farben aus meiner Alacritty-Config
5. [x] Text-Werkzeug
6. [x] Strichstärke und Redo (Strichstärke als Größen-Stufen, gilt auch für Text)
7. [x] Ausgabe: Zwischenablage (Enter, Strg+C) und PNG speichern (Strg+S)
8. [x] Globaler Hotkey: sxhkd (`~/.config/herbstluftwm/keybindings.sxhkd`), Alt+Escape = Screenshot, Alt+Delete = Whiteboard, beide über `~/.local/bin/annotate-board`
9. [ ] Extras: nummerierte Marker, ~~Unschärfe~~ (erledigt: Werkzeug z, verpixeln, beim Speichern ins Rohbild eingebrannt), Bereichsauswahl, Tray-Icon
10. [x] Verlauf wie bei Tekapoint: Jeder Screenshot landet automatisch als bearbeitbares PNG in `~/.local/share/annotate/history/` (1 s nach jeder Änderung und beim Beenden, absturzsicher; erst ab der ersten Änderung, Screenshots ohne Änderung nicht; keine Whiteboards). ← / → blättern im laufenden Tool, Änderungen landen im jeweiligen Eintrag. Aufbewahrung: die letzten 100 (`[history] keep`). Später denkbar: rofi-Liste mit Vorschaubildern, globaler Hotkey für „letzten Screenshot öffnen“
11. [x] Leere Zeichenfläche für Diagramme (Ersatz für Excalidraw): `--board`, normales gekacheltes Fenster, unendliche Fläche, Mausrad/mittlere Maustaste verschieben, Strg+Mausrad Zoom, Strg+W Übersicht, Speichern/Laden als `_board.png`, Hintergrund aus Alacritty
12. [ ] (Schritt 1 erledigt: auswählen, verschieben, löschen, umfärben, Größe; Schritt 2 erledigt: Griffe zum Größe ändern) Auswahl-Werkzeug für alle Elemente: anklicken, verschieben, löschen (Entf), Farbe nachträglich ändern (Element auswählen, Farbe wählen). Später: Mehrfachauswahl, Größe ändern, Drehen, Strichstärke nachträglich ändern, Kopieren/Einfügen, Vorder-/Hintergrund. Das Verschieben von Text im Text-Werkzeug geht dann darin auf. Drehen nur, wenn die Bedienung übersichtlich bleibt (z. B. Tasten in festen Schritten oder ein Griff an der Auswahl) Hinweis: E ist seit dem Zeigen (Spotlight) belegt, fürs Drehen eine andere Taste wählen
13. [ ] Leisten-Layout: Platz für weitere Leisten (Strichstärke, Füllung, Modi …), siehe D3
14. [ ] Vorlagen, vielleicht: kleine Bibliothek vorgefertigter Elemente wie in draw.io, aber viel einfacher. Symbole (Haken, Kreuz, Warnung …), Tabellen, zusammengesetzte Elemente. Idee: Eine Vorlage ist einfach eine gespeicherte Elementgruppe im selben Format wie D1, eigene Vorlagen entstehen durch „Auswahl als Vorlage speichern“. Symbole als Pfade statt Bilddateien, damit sie umfärbbar bleiben. Tabellen sind der aufwendigste Teil (Zellen bearbeiten, Zeilen/Spalten hinzufügen), darum zuletzt
15. [ ] Diagramm-Grundlagen: Text in Formen (Doppelklick auf Form = beschriften), Verbinder-Pfeile, die an Formen andocken und mitwandern (siehe D5)
16. [ ] Idee für später: weitere Schriften für das Text-Werkzeug, z. B. eine Monospace-Schrift (für Code, Befehle, Pfade). Naheliegend: die Schrift aus der Alacritty-Config (`[font.normal] family`) als Monospace-Standard. Datenmodell: `TextElement` bräuchte ein Feld `font` (in `to_dict`, fehlt es beim Laden = bisherige Schrift, also abwärtskompatibel). Offen: Umschalten per Taste oder Leiste, welche Schriften, fett/normal
17. [x] Meldungen per dunst, Nachfragen („Speichern?“ beim Schließen des Whiteboards) per rofi mit Fuzzy-Eingabe, beides per `[ui]` abschaltbar (Qt-Fallback). Später evtl.: Qt-Dialog per Stylesheet an `ui.Theme` anpassen
18. [x] Hintergrundfarbe im laufenden Whiteboard ändern: Strg+B / Strg+Shift+B blättert durch `[board] backgrounds` (Standard: Alacritty-Hintergrund und Papierweiß, also dunkel/hell), Undo-Schritt, wird mitgespeichert. Nur im Whiteboard. Auf hellem Hintergrund werden alle Farben automatisch abgedunkelt gezeigt (auch schon gezeichnete, Farbleiste und Auswahlrahmen passen sich an)
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
