# Plan: Monospace-Schrift für Text (Roadmap 16)

Status: **umgesetzt** (2026-10-09). Abweichung: Prüfung „Schrift installiert?“ muss Qts Namen mit Herstellerkürzel kennen (z. B. „RobotoMono Nerd Font Mono [GOOG]“), siehe `Canvas.use_mono_family`.

Ziel: Text kann zusätzlich zur bisherigen Schrift in einer Monospace-Schrift stehen, für Code,
Befehle und Pfade auf Screenshots. Standard für Monospace ist die Schrift aus der
Alacritty-Config (`[font.normal] family`, bei mir „RobotoMono Nerd Font Mono“), so wie die
Farben schon aus Alacritty kommen. Die Schrift gilt immer für einen ganzen Text, nicht für
einzelne Wörter darin.

## Entschieden (2026-10-09)

- **Taste: Alt+V überall**, beim Tippen und sonst. Beim Tippen gehen Buchstaben in den Text,
  nur Alt+… wirkt dort als Befehl (`ACTIONS_WHILE_TYPING`, so laufen schon Alt+A S D F für die
  Größe); Alt = Eigenschaft von Text/Strich. Im Tastaturbild bleibt v leer (es zeigt nur
  Tasten ohne bzw. mit Shift), in der Liste steht „alt+v: monospace on/off“
- **Fett:** Monospace ist wie normaler Text fett, mit Alacrittys Fett-Schrift (`[font.bold]`,
  fehlt sie: `[font.normal]`)

## Vorgeschlagen (ohne Rückfrage, bei Bedarf ändern)

- **Wirkung der Taste**, wie bei Farbe und Größe (D4: Eigenschaften gelten für die Auswahl
  oder das Nächste):
  - beim Tippen: der Text, der gerade bearbeitet wird (auch Beschriftungen in Formen und an
    Pfeilen)
  - mit Auswahl: alle ausgewählten Texte und die Beschriftungen der ausgewählten Formen, ein
    Undo-Schritt (`property_command` mit mehreren Settern)
  - sonst: Zustand der Canvas (`text_font`, wie `size_level`), gilt für den nächsten Text
- **Anzeige:** keine Meldung (erst eingebaut, dann auf Wunsch entfernt: störte), man sieht es
  am Text. Später evtl. in der Leiste (Roadmap 13).
- **Fehlende Schrift:** Ist die Alacritty-Schrift nicht installiert oder fehlt der Eintrag,
  nimmt Qt die System-Monospace-Schrift (`QFontDatabase.systemFont(FixedFont)`), Hinweis im
  Terminal. Nie Absturz.
- **Whiteboard und Screenshot** gleich.

## Datenmodell

- `TextElement.font_kind`: `"normal"` oder `"mono"`, Setter `set_font_kind(kind)` (baut die
  `QFont` neu, wie `set_font_size`; bei Beschriftungen danach `relayout()`, damit der Umbruch
  stimmt)
- Gespeichert wird die Art, nicht der Name der Schrift: Dateien bleiben auf einem anderen
  Rechner lesbar, und eine andere Alacritty-Schrift gilt auch für alte Zeichnungen
- `to_dict`: `"font": "mono"` nur bei Monospace, fehlt der Eintrag = normal (alte Dateien
  unverändert gültig). Beschriftung im `label`-Dict der Form genauso
  (`{"text", "font_size", "font"}`)
- `from_dict`: unbekannter Wert = normal (nie Absturz, wie bei anderen fehlerhaften Daten)

## Config

- `[text] mono_font = ""`: leer = aus Alacritty `[font.bold] family` (fehlt sie:
  `[font.normal]`), sonst Name einer installierten Schrift
- Lesen der Alacritty-Schrift in `colors.py` neben der Palette (gleiche Datei, gleiche
  `import`-Auflösung, `_load_file` sammelt dann auch `font`). Name der Funktion z. B.
  `load_terminal_font()`; `colors.py` heißt dann nicht mehr ganz passend, Umbenennen in
  `alacritty.py` wäre ein eigener kleiner Schritt (nicht hier)
- `settings.py`: `Settings.mono_family` (fertig aufgelöst), `config.example.toml`, Fall in
  `tests/test_settings.py`

## Schritte

1. **Datenmodell und Schrift laden:** `font_kind` in `TextElement` (inkl. Beschriftung,
   `to_dict`/`from_dict`), Alacritty-Schrift lesen, `[text] mono_font`, Fallback.
   Tests: `test_document.py` (speichern/laden mit und ohne `font`, alte Datei, kaputter Wert),
   `test_settings.py` (Config leer, eigener Name, Alacritty ohne `[font]`). Noch keine Taste:
   Programm läuft unverändert
2. **Bedienung:** Aktion `text_font` (keymap, `Canvas.actions`, `shortcuts.DESCRIPTIONS`,
   in `ACTIONS_WHILE_TYPING`), Zustand `text_font` der Canvas, Wirkung beim Tippen/Auswahl/nächster Text,
   Undo, Meldung. `docs/usage.md`, `config.example.toml` (`[keys]`), Tastenübersicht.
   GUI-Szenario `test_text_font.py` (oder in `test_label.py`): Text tippen, umschalten, Breite
   des Textes ändert sich, Undo, Verlauf enthält `"font": "mono"`
3. **Abschluss:** Regressionsbild bleibt gleich (normale Schrift unverändert), Roadmap 16
   abhaken, CLAUDE.md (Text-Element: `font_kind`)

Handtests bei dir: Aussehen der Nerd-Font-Schrift auf deinen Monitoren, HiDPI.

## Später denkbar

- Weitere Schriften (Handschrift für Whiteboard), dann eher eine Liste in `[text] fonts`
  statt nur normal/mono
- Kursiv, nicht fett; Code-Hintergrund (Kasten hinter Monospace-Text)
