# Plan: Text in Formen (Roadmap 15, Teil 1)

Status: **Entwurf** (2026-10-05), Bedienung entschieden, Umsetzung in drei Schritten

Ziel: Ein Rechteck oder eine Ellipse bekommt eine Beschriftung, die zur Form gehört:
Sie steht mittig, bricht an der Breite der Form um, hat die Farbe der Form und wandert beim
Verschieben, Drehen und Größe-Ändern mit. Teil 2 von Roadmap 15 (Verbinder-Pfeile) bekommt
einen eigenen Plan, baut aber auf diesem auf (D5).

## Entschieden (2026-10-05)

- **Anlegen/Bearbeiten:** Im Auswahl-Werkzeug Doppelklick irgendwo in die Form (Rand oder
  Inneres) öffnet die Beschriftung, ist noch keine da, entsteht sie. Bisher legte ein
  Doppelklick ins leere Innere eines Rechtecks einen losen Text an; das geht dann nur noch
  per T. Keine eigene Taste.
- **Umbruch:** Text bricht an der Breite der Form um und steht waagerecht und senkrecht
  mittig. Die Form wächst nicht mit; zu viel Text ragt oben/unten heraus, dann zieht man die
  Form größer und der Text bricht neu um.
- **Farbe:** immer die der Form. Umfärben der Form färbt beides, auf hellem Whiteboard
  werden beide gleich abgedunkelt.
- **Formen:** nur Rechteck und Ellipse. Text an Pfeilen/Linien kommt mit den Verbindern.

## Vorgeschlagen (ohne Rückfrage, bei Bedarf ändern)

- **Schriftgröße:** beim Anlegen die aktuelle Text-Stufe (wie neuer Text). Während des Tippens
  ändern Alt+A S D F und Alt+Mausrad sie wie bei normalem Text. Ist die Form nur ausgewählt
  (nicht in Bearbeitung), ändern die Größen-Tasten weiter nur die Strichstärke.
- **Auswahl:** Die Beschriftung ist kein eigenes Element. Ein Klick auf sie wählt die Form, Ziehen
  verschiebt die Form, Entf löscht die Form samt Beschriftung. Nur der Doppelklick geht in den Text.
- **Löschen nur der Beschriftung:** Text leeren und Esc (wie bei normalem Text: leerer Text
  verschwindet).
- **Ränder:** Abstand zum Rand der Form, damit der Text nicht am Strich klebt. Bei der Ellipse
  ist die Fläche kleiner: Umbruchbreite ≈ 70 % der Breite (passt in das innere Rechteck).
- **Fett** wie normaler Text.

## Technik

**Qt-Konzept Kind-Item:** `label.setParentItem(shape)` hängt den Text an die Form. Seine
Koordinaten sind dann relativ zur Form, und Lage, Drehung, Sichtbarkeit und Löschen erbt er
automatisch. Das ist genau „wandert mit“, ohne dass wir beim Verschieben etwas tun müssen.

**Datenmodell (`elements.py`):**
- `ShapeElement.label`: ein `TextElement` als Kind oder `None`.
- `layout_label()`: Umbruchbreite (`setTextWidth`) aus der Breite der Form, Text mittig
  ausrichten (Absatz zentriert über `QTextOption`), Position so, dass die Mitte des Textes in
  der Mitte der Form liegt. Aufgerufen aus `rebuild()` (Größe ändern), bei Schriftgröße und
  bei jeder Textänderung (Signal `contentsChanged` des Dokuments, damit er beim Tippen
  mittig bleibt).
- Farbe: `ShapeElement.set_color` / `refresh_color` geben die Farbe an die Beschriftung weiter.
- `to_dict`: neuer optionaler Eintrag `"label": {"text": …, "font_size": …}`. Fehlt er
  (alte Dateien), gibt es keine Beschriftung; das Format bleibt abwärtskompatibel.

**Canvas:**
- `elements()` liefert nur Elemente ohne Eltern (`parentItem() is None`). Sonst würde die
  Beschriftung doppelt gespeichert, mit Strg+A einzeln ausgewählt, umsortiert usw.
- `element_at()`: trifft die Suche eine Beschriftung, gilt ihre Form als getroffen.
- Neu `shape_at(pos)`: oberstes Rechteck/oberste Ellipse, deren *Fläche* pos enthält (für den
  Doppelklick; normale Klicks treffen weiter nur den Rand, D2).
- Bearbeiten über die vorhandene Texteingabe (`edit_text`/`finish_text`), mit Unterscheidung,
  ob es eine Beschriftung ist.
- Die Beschriftung selbst ist nicht auswählbar (`ItemIsSelectable` aus).

**Undo (`commands.py`):**
- Neu `SetLabelCommand(shape, label)` hängt eine Beschriftung an bzw. ab (Undo = wieder weg).
- Text ändern: das vorhandene `EditTextCommand`.
- Leeren = Beschriftung entfernen: Makro aus Textänderung + Abhängen, wie bei losem Text.

**Kopieren/Einfügen/Duplizieren, Verlauf, Export:** laufen über `to_dict`, die Beschriftung
geht also automatisch mit. Rendern und Export sehen das Kind-Item ohnehin.

## Schritte

1. **Datenmodell ohne Bedienung:** `label`, `layout_label`, Farbe, `to_dict`/`from_dict`,
   `elements()`/`element_at()` ohne Kinder. Test in `tests/test_document.py`: Form mit
   Beschriftung anlegen, speichern, laden, pixelgleich; `elements()` zählt sie nicht; nach
   Größe ändern und Drehen sitzt sie mittig; Umfärben färbt beides; alte Datei ohne `label`
   lädt. Optik bestehender Szenen unverändert (`regress.py`).
2. **Bedienung:** Doppelklick in Rechteck/Ellipse, `SetLabelCommand`, leeren = entfernen,
   Tippen mittig. Tests: `test_document.py` (Undo, Leeren) und ein GUI-Szenario
   (Doppelklick, tippen, Esc, verschieben, Verlauf enthält die Beschriftung).
3. **Rundherum:** Kopieren zwischen Screenshot und Whiteboard, Tastenübersicht (Maus:
   „double-click (select)“ um „label shape“ ergänzen), `docs/usage.md`, Roadmap, CLAUDE.md.

Nach jedem Schritt: alle Tests, du prüfst, dann Commit. Push erst nach Schritt 3.

## Offen für Teil 2 (Verbinder)

- Text an Pfeilen: dieselbe `label`-Mechanik, Position Mitte der Linie statt Mitte der Form.
- Verbinder speichern die IDs ihrer Start-/Zielform (D5); Beschriftungen ändern daran nichts.
