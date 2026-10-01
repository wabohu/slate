# Plan: Datenmodell umbauen (D1, Schritt 1)

Status: **abgeschlossen** (Schritt 1: 1a, 1b, 1c; Schritt 2: Speichern/Laden)

**Ziel:** Jedes gezeichnete Element kennt seine eigenen Werte: ID, Art, Geometrie,
Farbe, Strichstärke, Position und Drehung. **An der Bedienung ändert sich nichts.**
Nach dem Umbau verhält sich das Tool genau wie vorher. Der Umbau schafft das Fundament
für Auswahl, Umfärben, Drehen, Speichern, Verbinder und Vorlagen (Roadmap 10–15, D1 und D5
in `CLAUDE.md`).

## Das Kernproblem

Beim Zeichnen eines Rechtecks entsteht ein `QGraphicsPathItem` mit einem fertigen Pfad in
Bildschirmkoordinaten. Danach weiß das Item nicht mehr, dass es ein Rechteck von A nach B
war. Ohne diese Information kann man das Element weder vergrößern noch speichern, und auch
das Drehen um die eigene Mitte funktioniert nicht sauber.

## Neue Dateistruktur

| Datei | Inhalt | Status |
|---|---|---|
| `tools.py` | `Tool`-Enum, `parse_tool`, `tool_order`, `shape_path`, `tool_icon`, `RECT_RADIUS` | neu, nur verschoben aus `annotate.py` |
| `elements.py` | `ShapeElement`, `TextElement`, `new_id()` | neu |
| `commands.py` | Undo-Befehle | unverändert |
| `annotate.py` | Canvas (Maus, Tastatur, Leisten), Tastenkürzel, Capture, `main()` | schlanker |
| `ui.py`, `colors.py`, `config.py` | | unverändert |

`tools.py` muss eine eigene Datei werden. `elements.py` braucht `Tool` und `shape_path`, und
würde es diese aus `annotate.py` importieren, entstünde ein Kreis: `annotate.py` importiert
ja `elements.py`.

## Die neuen Klassen (`elements.py`)

**`ShapeElement(QGraphicsPathItem)`**, für Freihand, Linie, Pfeil, Rechteck und Ellipse:
- `id`: zufällige, eindeutige Kennung (`uuid4().hex`), für Verbinder und Speichern
- `tool`: welche Form
- `points`: Liste von Punkten **relativ zum Element**. Bei Linie, Pfeil, Rechteck und
  Ellipse sind das 2 Punkte (Start, Ende), bei Freihand alle Punkte.
- `color`, `width`
- Position und Drehung verwaltet Qt selbst: `pos()` und `rotation()` hat jedes Grafikobjekt.
- `rebuild()` baut aus `tool` und `points` den Pfad neu. Farbe oder Strichstärke setzen
  läuft über `set_color()` bzw. `set_width()`, beide bauen den Stift neu.
- `add_point()` erweitert bei Freihand den Pfad Punkt für Punkt, statt ihn bei jeder
  Mausbewegung ganz neu zu bauen.

**`TextElement(QGraphicsTextItem)`:**
- `id`, `font_size`. Die Farbe steckt schon in `defaultTextColor()`.
- Später hängt eine Formbeschriftung (D5) als Kind-Item an einem `ShapeElement`, die Klasse
  ist dafür schon vorbereitet.

**Lokale Koordinaten:** Beim Zeichnen wird der Startpunkt zur Position des Elements
(`setPos(start)`), alle weiteren Punkte werden relativ dazu gespeichert. Qt-Konzept
dahinter: Jedes Item hat ein eigenes Koordinatensystem, und `pos()`, `rotation()` und
`scale()` bilden es in die Szene ab. Verschieben ändert dann nur `pos`, Drehen nur
`rotation`, und die Geometrie bleibt unberührt.

## Zwischenschritte

Jeder Schritt ist für sich lauffähig. Nach jedem Schritt wird getestet, committet wird erst
nach Bestätigung.

- [x] **1a** Reine Verschiebung: Werkzeug-Kram nach `tools.py`, keine Logikänderung.
  Test: Startet? Alle Werkzeuge, Leisten, Undo wie bisher
- [x] **1b** `ShapeElement` einführen, Canvas zeichnet damit, lokale Koordinaten.
  Test: Alle 5 Formen zeichnen, Undo/Redo, sieht alles aus wie vorher?
- [x] **1c** `TextElement` einführen, Text-Werkzeug nutzt es.
  Test: Text neu, verschieben, Doppelklick bearbeiten, Undo

Vor jedem Schritt laufen die Offscreen-Tests, mit Zeichnen, Undo/Redo, Text und gerendertem
Bild. In 1b wird zusätzlich geprüft, dass jede Form in der Szene exakt an derselben Stelle
landet wie vorher.

## Bewusst nicht in diesem Schritt
- Speichern und Laden als JSON. Das ist der nächste Schritt, dort testen wir das Format.
- Auswahl-Werkzeug, Umfärben, Drehen: Das Modell kann es danach, eine Bedienung dafür gibt
  es aber noch nicht.
- D2 (Treffer nur am Rand), D3 (Leisten), D4 (Tasten).
- `CLAUDE.md` wird im jeweiligen Schritt angepasst (neue Dateien, „Jedes Zeichenobjekt ist
  ein `ShapeElement` …“).

## Schritt 2: Speichern und Laden (erledigt)

Entscheidungen (2026-10-01):
- Farben als Farbwert `#rrggbb` (alte Zeichnungen sehen nach einem Theme-Wechsel gleich aus)
- Eine Datei: normales PNG mit den Markierungen, Bearbeitungsdaten als JSON im PNG-Text-Chunk
  `annotate`, roher Hintergrund als Base64-PNG darin. Grund: Bildbetrachter und Dateimanager
  zeigen die Zeichnung direkt, annotate kann sie wieder bearbeiten
- Strg+S speichert die Zeichnung (erst neue Datei, dann überschreiben), Strg+E exportiert ein
  sauberes PNG ohne Daten

Umsetzung: `to_dict()`/`from_dict()` in den Elementen, `document.py` für das Format,
`python annotate.py datei.png` zum Öffnen, Test in `tests/test_document.py`.
