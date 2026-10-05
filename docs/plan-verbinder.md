# Plan: Verbinder-Pfeile (Roadmap 15, Teil 2)

Status: **Entwurf** (2026-10-05), Bedienung entschieden, Umsetzung in vier Schritten

Ziel: Linien und Pfeile, deren Enden an Formen andocken. Verschiebt, dreht oder vergrößert
man die Form, folgt das Ende. Zum Schluss Text an Pfeilen. Baut auf den Beschriftungen auf
(Teil 1, `docs/plan-beschriftung.md`) und auf D5 in der Roadmap.

## Entschieden (2026-10-05)

- **Andockpunkt:** Das Ende zielt auf die Mitte der Form und endet an ihrem Rand, mit kleinem
  Abstand. Verschiebt man Formen, rutscht der Ansatzpunkt am Rand entlang (wie Excalidraw).
  Sind beide Enden angedockt, läuft die Linie von Mitte zu Mitte, an beiden Rändern gekappt.
- **Form bewegen = Pfeil wandert mit:** Verschiebt man eine angedockte Form (Maus, hjkl,
  Undo/Redo), dreht oder vergrößert sie, bleibt der Pfeil angedockt und folgt. Gelöst wird nur
  über den Pfeil selbst (siehe „Lösen“) oder seinen Endpunkt-Griff.
- **Ziele:** Rechteck, Ellipse, Bild und loser Text (der als Rechteck um den Text).
  Nicht: Freihand, Linien/Pfeile selbst, Marker, Unschärfe.
- **Lösen:** Zieht man den ganzen Pfeil weg, löst er sich von beiden Formen. Wird eine Form
  gelöscht, bleibt der Pfeil mit freiem Ende an der letzten Stelle stehen; Undo des Löschens
  dockt ihn wieder an.
- **Text an Pfeilen:** ja, als letzter Schritt, mit derselben Mechanik wie Beschriftungen.

## Vorgeschlagen (ohne Rückfrage, bei Bedarf ändern)

- **Andocken beim Zeichnen:** Beginnt oder endet ein Pfeil/eine Linie auf der Fläche eines
  Ziels, dockt dieses Ende an. Liegen mehrere übereinander, das oberste. Während des Ziehens
  wird das Ziel unter dem Mauszeiger hervorgehoben (feiner Rahmen, nur auf dem Bildschirm).
- **Umhängen:** Endpunkt-Griff (Auswahl-Werkzeug) auf ein anderes Ziel ziehen = dort andocken,
  ins Leere ziehen = lösen. Ein Undo-Schritt.
- **Ganzen Pfeil verschieben:** löst nur die Enden, deren Form nicht mit verschoben wird.
  Wählt man Formen und Pfeil zusammen aus und verschiebt alles, bleibt alles verbunden.
- **Kein Andocken mit Strg** gedrückt? Erst einmal nicht, nur falls es im Alltag stört.
- **Abstand** zwischen Pfeilspitze und Rand: 6 Szenen-Einheiten plus halbe Strichstärke.
- **Beide Modi:** Screenshot und Whiteboard.
- **Kopieren:** Kopiert man Formen und Pfeil zusammen, sind die Kopien untereinander
  verbunden. Kopiert man nur den Pfeil, sind seine Enden frei.
- **Drehen per Q** eines angedockten Pfeils: löst wie Verschieben (die Enden bleiben sonst ja
  an den Formen und würden das Drehen sofort zurücknehmen).

## Technik

**Datenmodell (`elements.py`):**
- Linie und Pfeil bekommen `ends = [start_id, end_id]` (je eine Element-ID oder `None`).
- Gespeichert als optionales `"ends": [id | null, id | null]`. Fehlt es (alte Dateien), sind
  beide Enden frei. IDs, die es in der Datei nicht gibt, gelten als frei.
- `geometry()` / `set_geometry()` der Linie enthalten auch `ends`. So nimmt das vorhandene
  Undo beim Griff-Ziehen (Umhängen) das Andocken mit.

**Lage berechnen (neu, z. B. `connectors.py`, ohne Canvas-Abhängigkeit):**
- `target_outline(item)`: Fläche des Ziels in Szenen-Koordinaten (Rechteck/Ellipse: ihr Pfad,
  Bild/Text: Rechteck um den Inhalt), gedreht wie das Element.
- `clip_to_outline(center, toward, outline)`: Punkt, an dem die Strecke Mitte → anderes Ende
  die Fläche verlässt. Halbierungssuche auf der Strecke mit `QPainterPath.contains()`;
  funktioniert für jede Form, auch gedreht, ohne Formel je Formart.
- `layout_connector(line, lookup)`: neue Endpunkte aus den angedockten Zielen (`lookup` =
  ID → Element) und den freien Enden; setzt `points` über `mapFromScene`, `rebuild()`.

**Wann neu berechnen (Canvas):**
- Nach jeder Änderung des Undo-Stacks (`indexChanged`, deckt Verschieben, Größe, Drehen,
  Löschen, Undo/Redo, Text fertig getippt ab) alle Verbinder.
- Live während Ziehen, Größe-Ändern und Drehen per Maus (sonst springt der Pfeil erst beim
  Loslassen hinterher).
- Die Lage ist aus den Formen abgeleitet und braucht darum kein eigenes Undo: nach jedem
  Undo wird sie einfach neu berechnet.

**Qt-Konzept dahinter:** Statt jede Form ihren Pfeilen Bescheid sagen zu lassen (Signale je
Element), rechnet die Canvas nach jeder Änderung alle Verbinder neu. Bei den paar Dutzend
Elementen einer Zeichnung kostet das nichts und hat keine Sonderfälle.

## Schritte

1. **Datenmodell und Berechnung, ohne Bedienung:** `ends`, Speichern/Laden, `connectors.py`,
   Neuberechnung nach jeder Undo-Änderung. Tests (`test_document.py`): programmgesteuert
   andocken, Form verschieben/drehen/vergrößern → Pfeil folgt und endet am Rand; Form löschen →
   Ende frei an letzter Stelle, Undo → wieder angedockt; Speichern/Laden; alte Dateien.
2. **Andocken mit der Maus:** beim Zeichnen (Start und Ende), Hervorheben des Ziels,
   Endpunkt-Griff umhängen/lösen, Live-Nachführen beim Ziehen. GUI-Szenario `test_connector.py`.
3. **Lösen und Kopieren:** ganzen Pfeil verschieben bzw. per Q drehen löst (außer Formen werden
   mitbewegt), Kopieren/Einfügen/Duplizieren mit neu zugeordneten IDs, Tastenübersicht,
   `docs/usage.md`.
4. **Text an Pfeilen:** Doppelklick auf Linie/Pfeil beschriftet sie, Text mittig auf der Linie,
   waagerecht, ohne Umbruch (Enter = neue Zeile), Linie unter dem Text ausgespart. Offen bis
   dahin: Aussparung im Screenshot-Modus (dort ist der Hintergrund ein Bild, keine Farbe):
   Vorschlag kleiner Kasten in der Leistenfarbe.

Nach jedem Schritt: alle Tests, du prüfst, dann Commit. Push nach Schritt 4 (Meilenstein).
