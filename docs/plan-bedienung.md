# Plan: Bedienung – Tasten (D4) und Leisten (D3)

Status: **entschieden** (2026-10-01), Umsetzung schrittweise mit den jeweiligen Roadmap-Punkten

Ziel: Jede geplante Funktion (Roadmap 6–15) bekommt einen vorgesehenen Platz, bevor sie
gebaut wird. Nichts davon muss sofort umgesetzt werden. Der Plan verhindert, dass wir
später Tasten umbelegen oder Leisten umbauen müssen.

## Grundsätze

1. **Linke Hand Tastatur, rechte Hand Maus.** Häufige Aktionen liegen links
   (Q–T, A–G, Z–B, 1–5, Tab, Shift, Strg, Leertaste). Seltene Aktionen dürfen
   Standardkürzel mit Strg/Alt oder Tasten rechts nutzen.
2. **Eine Taste = eine Bedeutung.** Keine Modi, in denen dieselbe Taste etwas völlig
   anderes tut. Ausnahme: während der Texteingabe gehen alle Tasten in den Text, außer Esc und den
   Größen-Tasten Alt+A S D F (`ACTIONS_WHILE_TYPING` in `annotate.py`).
3. **Eigenschaften wirken auf die Auswahl, sonst auf neue Elemente** (wie Excalidraw).
   Farbe, Strichstärke, Füllung und Schriftgröße setzen: Ist etwas ausgewählt, ändert es
   sich. Sonst gilt der Wert für das nächste Element. Damit ist „nachträglich umfärben“
   keine eigene Funktion, sondern fällt automatisch ab.
4. **Standardkürzel, wo es sie gibt:** Strg+C/V/D/A/S, Entf, Enter, Esc.
5. **Alles in der Config änderbar.** Eine zentrale Tabelle „Aktion → Taste“ statt
   verstreuter Konstanten. Das erleichtert neue Funktionen und das Umbelegen.

## Tastenbelegung

**Bestehend** (bleibt):

| Taste | Aktion |
|---|---|
| A S D F G T | Werkzeuge (Reihenfolge per Config) |
| Shift + A S D F G Z X C V B | Farben |
| Tab / Shift+Tab | Farbe weiter / zurück |
| R / Shift+R | Undo / Redo |
| Esc | Texteingabe beenden, sonst Tool beenden |

**Neu:**

| Taste | Aktion | Roadmap |
|---|---|---|
| W | Auswahl-Werkzeug | 12 |
| Q / E | Auswahl drehen −15° / +15° (Shift: in 1°-Schritten?) | 12 |
| Entf / Backspace | Auswahl löschen | 12 |
| Alt + A S D F | Größe in Stufen: Strichstärke, bei Text die Schriftgröße | 6 |
| Alt + Mausrad | Größe fein einstellen (Auswahl bzw. getippter Text) | 6 |
| X | Füllung an/aus (Rechteck, Ellipse) | 13, 15 |
| C | Werkzeug nummerierter Marker | 9 |
| Z | Werkzeug Unschärfe | 9 |
| V | Vorlagen öffnen (Popup) | 14 |
| B | Leisten ein-/ausblenden | 13 |
| Strg+C | mit Auswahl: Elemente kopieren; ohne: ganzes Bild in die Zwischenablage | 7, 12 |
| Strg+V / Strg+D | Einfügen / Duplizieren | 12 |
| Strg+A | Alles auswählen | 12 |
| Enter | Bild in die Zwischenablage und beenden | 7 |
| Shift+Enter | Speichern (wie Strg+S), absoluten Pfad in die Zwischenablage, beenden | 7 |
| Strg+S | Zeichnung speichern (bearbeitbares PNG) | D1 |
| Strg+E | Sauberes PNG exportieren | 7 |
| ← / → | Verlauf: älterer / neuerer Screenshot (umgesetzt ohne Alt) | 10 |
| Mausrad, mittlere Maustaste ziehen | Whiteboard: Fläche verschieben (beide Achsen) | 11 |
| Strg+Mausrad, Strg+0 | Whiteboard: zoomen, Zoom zurücksetzen | 11 |
| Strg+W | Whiteboard: Übersicht, ganzes Dokument einpassen; erneut = zurück | 11 |
| Strg+B / Strg+Shift+B | Whiteboard: Hintergrund weiter / zurück (`[board] backgrounds`) | 18 |
| ? | Übersicht aller Tastenkürzel | – |
| h j k l, Shift+h j k l | Auswahl verschieben (normal / fein) | 12 |
| Strg+↑ / Strg+↓ | Nach vorne / nach hinten | 12 |

Noch frei danach: Y U I O P N M, 1–0, Shift+Q/W/E/T, Alt-Kombinationen außer
Alt + A S D F und Alt+Pfeile.

**Verbinder (15)** brauchen keine eigene Taste: Beginnt oder endet ein Pfeil auf einer
Form, dockt er dort an. **Text in Formen (15)**: Doppelklick auf eine Form im
Auswahl-Werkzeug.

## Leisten

Heute: zwei Leisten unten mittig übereinander (Werkzeuge, Farben). Dazu kommen
Strichstärke (4 Stufen), Füllung (1 Schalter) und später weitere Werkzeuge.

**Variante A – eine gemeinsame Leiste** (gewählt, Standardposition unten mittig):
```
┌──────────────────────────────────────────────────────────────────────────┐
│ ▢W ∿A ╱S ↗D ▭F ◯G T │ ■ ■ ■ ■ ■ ■ ■ ■ ■ │ · • ● ⬤ │ ◧X │   (Stärke: Alt+A S D F)
└──────────────────────────────────────────────────────────────────────────┘
   Werkzeuge            Farben                Stärke 1–4  Füllung
```
- Eine Zeile, Gruppen durch Trennstriche. Etwa 20 Felder × 32 px ≈ 650 px breit,
  auf deinen Monitoren (3440 / 3840 px) unproblematisch.
- Alles an einer Stelle, verdeckt nur einen schmalen Streifen.

**Variante B – Excalidraw-Stil:**
```
                 ┌──────────────────────────┐
                 │ ▢ ∿ ╱ ↗ ▭ ◯ T            │   Werkzeuge oben mittig
                 └──────────────────────────┘
┌─────────┐
│ Farben  │
│ ■ ■ ■   │   Eigenschaften links, zeigt die
│ Stärke  │   Werte der Auswahl bzw. des Werkzeugs
│ · • ●   │
│ Füllung │
└─────────┘
```
- Übersichtlicher bei vielen Eigenschaften, gewohnt aus Excalidraw.
- Verdeckt auf Screenshots zwei Stellen statt einer.

**Variante C – bleibt wie heute**, zusätzliche Leisten stapeln sich unten. Wird mit
jeder neuen Eigenschaft höher.

**Unabhängig von der Variante:**
- Position per Config (`[ui] position = "bottom" | "top" | "left" | "right"`).
- B blendet alle Leisten aus und ein.
- Die Vorlagen (14) öffnen als Popup mit Vorschaubildern (Taste V), nicht als
  dauerhafte Leiste.
- Die Leisten zeigen immer die aktuell gültigen Werte, bei einer Auswahl also deren
  Farbe und Stärke (Grundsatz 3).

## Entscheidungen (2026-10-01)

1. Grundsatz 3 („wirkt auf Auswahl“): **ja**
2. Tastenbelegung: **wie vorgeschlagen**, außer Strichstärke/Schriftgröße auf
   **Alt + A S D F** statt 1–4
3. Leisten: **Variante A**, eine gemeinsame Leiste, Standard unten mittig,
   Position per Config
4. Zentrale Tastentabelle mit Config: **ja**, umgesetzt in `keymap.py`
