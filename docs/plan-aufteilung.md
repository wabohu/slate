# Plan: `annotate.py` aufteilen, CLAUDE.md verschlanken

Status: **in Arbeit**. Entschieden (2026-10-01): flache Dateien `canvas_…`, Schritt 6 (CLAUDE.md) zuerst. Erledigt: 6, 1, 2

**Ziel:** `annotate.py` (1166 Zeilen, davon gut 1000 in der Klasse `Canvas`) in Dateien
aufteilen, die je einen Bereich abdecken, wie es die Konvention in `CLAUDE.md` verlangt
(Capture, Zeichenlogik/Canvas, UI, Export). **An Verhalten und Optik ändert sich nichts.**
Es wird nur Code verschoben, nichts neu geschrieben. Darum muss `tests/regress.py` nach
jedem Schritt ein identisches Bild liefern, ohne `--update`.

## Das Kernproblem

`Canvas` ist ein `QGraphicsView`. Qt liefert alle Maus-, Tastatur- und Mausrad-Events an
genau dieses eine Objekt. Deshalb ist dort im Lauf der Zeit alles gelandet:

| Bereich | Zeilen ca. | Methoden (Auswahl) |
|---|---|---|
| Config lesen, Standardwerte | 230 | Konstanten, `size_values`, `config_*`, `load_theme`, `load_board_backgrounds`, `load_light_overrides`, großer Teil von `__init__` |
| Kern: Werkzeug, Farbe, Größe, Leisten, Tasten | 200 | `set_tool`, `set_color`, `set_size`, `update_bars`, `actions`, `keyPressEvent` |
| Maus, Text, Griffe | 330 | `mouse*Event`, `finish_shape`, `start_text`/`finish_text`, `handle_at`, `drawForeground`, `wheelEvent`, `adjust_size` |
| Whiteboard: Ansicht und Hintergrund | 170 | `pan_by`, `zoom_by_wheel`, `overview`, `set_board_color`, `adapt_color`, `confirm_close` |
| Ausgabe | 110 | `render_image`, `copy_*`, `export_image`, `save_drawing`, `report`, `ask` |
| Start | 60 | `grab_screen`, `main` |

Ein neues Feature bedeutet heute: in einer 1166-Zeilen-Datei die richtige Stelle finden.
Für dich ist das schwer zu überblicken, für mich kostet es bei jeder Sitzung viel Kontext.

## Ansatz: Mixins plus ein Settings-Objekt

**Qt/Python-Konzept Mixin:** Eine kleine Klasse ohne eigenes `__init__`, die nur Methoden
mitbringt. `Canvas` erbt von mehreren davon:

```python
class Canvas(InputMixin, BoardMixin, OutputMixin, QGraphicsView):
    ...
```

Python sucht eine Methode zuerst in `Canvas`, dann der Reihe nach in den Mixins, zuletzt in
`QGraphicsView` (Method Resolution Order). Für Qt sieht es aus wie vorher: ein Objekt, das
`mousePressEvent` usw. hat. `super().mousePressEvent(event)` im Mixin landet weiter bei
`QGraphicsView`. Mit PySide6 habe ich das ausprobiert: Ein Tastendruck kommt in einem
`keyPressEvent` an, das in einem Mixin steht.

Vorteil: Die Methoden wandern **unverändert** in andere Dateien, `self.…` bleibt `self.…`.
Das Risiko ist klein, der Diff besteht fast nur aus Verschiebungen.
Nachteil: Die Mixins teilen sich weiter alle Attribute von `self`. Darum schreibt jedes
Mixin oben in den Docstring, welche Attribute es liest und welche es selbst verwaltet.

**Settings statt Config-Code in `__init__`:** Alles, was nur einmal beim Start aus der Config
gelesen wird und sich danach nicht ändert (Größen-Stufen, Palette, Theme, Schrittweiten,
Eckenradius, Ausgabeordner, dunst/rofi …), kommt in ein eigenes Objekt `Settings`. Das ist
Komposition statt Vererbung: `Canvas` hat ein `self.settings`. Was sich während der Sitzung
ändert (aktuelles Werkzeug, Farbe, Stufe, Whiteboard-Hintergrund), bleibt in `Canvas`.
`Settings` lässt sich ohne Fenster testen.

**Verworfen:** Alles sofort in eigenständige Hilfsobjekte umbauen, also auch für Navigation,
Auswahl usw. Die Grenzen wären sauberer, aber dafür müsste viel Code umgeschrieben werden
statt nur verschoben. Einzelne Mixins lassen sich später noch umbauen, wenn es sich lohnt.

## Neue Dateistruktur

| Datei | Inhalt | Zeilen ca. |
|---|---|---|
| `annotate.py` | nur Start: `grab_screen()` (Capture), `main()` | 70 |
| `settings.py` | Konstanten (`DEFAULT_*`, `*_RANGE`, `HANDLE_SIZE` …), `Settings`, `load_settings(config, board)`, alle `config_*`/`load_*`-Helfer | 230 |
| `canvas.py` | `Canvas`: `__init__`, Zustand, Werkzeug/Farbe/Größe setzen, Leisten, `update_bars`, Auswahl-Helfer (`selected_element`, `element_at`, `elements`, `zoom`), `actions`, `keyPressEvent`, `show_overlay`/`show_window`, `closeEvent` | 350 |
| `canvas_input.py` | `InputMixin`: Maus (`mouse*Event`, `finish_shape`), Text (`start_text`, `edit_text`, `finish_text`, `text_at`), Griffe (`handle_at`, `update_cursor`, `drawForeground`, `selection_colors`), Mausrad (`wheelEvent`, `adjust_size`), `move_selected`, `delete_selected` | 330 |
| `canvas_board.py` | `BoardMixin`: Ansicht (`pan_by*`, `zoom_by_wheel`, `zoom_reset`, `overview`, `view_state`), Hintergrund (`set_board_color`, `cycle_board_color`, `adapt_color`, `refresh_colors`), `update_title`, `confirm_close` | 170 |
| `canvas_output.py` | `OutputMixin`: `render_image`, `used_rect`, `copy_image`, `copy_and_quit`, `copy_path_and_quit`, `export_image`, `save_drawing`, `report`, `ask` | 110 |

Unverändert bleiben: `elements.py`, `tools.py`, `commands.py`, `document.py`, `export.py`,
`ui.py`, `keymap.py`, `colors.py`, `config.py`, `notify.py`.

Der Aufruf bleibt `python annotate.py …`, also auch für sxhkd und `annotate-board`.

Faustregel für später:

| Neue Funktion | gehört nach |
|---|---|
| neuer Config-Wert | `settings.py` (+ `config.example.toml`) |
| neue Taste | `keymap.py` + Handler in `Canvas.actions` (wie bisher) |
| Mausbedienung, Werkzeug-Verhalten | `canvas_input.py` |
| nur im Whiteboard | `canvas_board.py` |
| Speichern, Kopieren, Meldungen | `canvas_output.py` |

## Zwischenschritte

Jeder Schritt: Code verschieben, dann `python tests/regress.py` (Bild identisch) und
`python tests/test_document.py`, dann testest du kurz von Hand, danach ein eigener Commit.
Die Reihenfolge geht vom Einfachen zum Verflochtenen.

1. **`settings.py`**
   - Konstanten, `clamp`, `size_values` und die `config_*`/`load_*`-Methoden aus `Canvas`
     werden Funktionen in `settings.py`.
   - Dazu kommt `Settings` (Dataclass) mit `load_settings(config, board)`.
   - `__init__` schrumpft um etwa 100 Zeilen. Zugriffe werden `self.settings.move_steps` statt
     `self.move_steps`.
   - Neu: ein kleiner Test `tests/test_settings.py`. Er prüft ungültige Werte →
     Standardwert und fehlende Config → kein Absturz.
2. **`canvas_board.py`**: Der Whiteboard-Teil ist am klarsten abgegrenzt, darum kommt er zuerst.
3. **`canvas_output.py`**
4. **`canvas_input.py`**: der größte Schritt. Maus, Text und Griffe greifen ineinander,
   darum wandern sie zusammen.
5. **`canvas.py`**
   - `Canvas` zieht aus `annotate.py` in eine eigene Datei, `annotate.py` behält nur `main()`.
   - Die Tests importieren dann `from canvas import Canvas` statt `annotate.Canvas`.
6. **CLAUDE.md verschlanken** (unabhängig von 1–5, kann auch zuerst kommen):
   - Roadmap und „Offene Designentscheidungen“ ziehen nach `docs/roadmap.md`, die Bedienung
     nach `docs/bedienung.md`.
   - CLAUDE.md behält Umgebung, Architektur (mit der neuen Dateitabelle), Konventionen, Git
     und Stolperstellen, dazu je eine Zeile mit Verweis auf die beiden Dateien.
   - Ergebnis: etwa 45 statt 95 Zeilen, die in jeder Sitzung geladen werden.
   - Roadmap-Punkte schlage ich dann bei Bedarf in `docs/roadmap.md` nach.

Handtest nach jedem Schritt, für alles, was die Tests nicht abdecken:

- Screenshot (Alt+Escape) zeichnen und mit Enter beenden.
- Whiteboard (Alt+Delete):
  - Mausrad, mittlere Maustaste, Strg+Mausrad, Strg+W
  - Strg+B
  - Strg+Q mit ungespeicherten Änderungen (rofi)
- Text tippen, Alt+Mausrad.

## Bewusst nicht in diesem Schritt

- Keine Umbenennungen, keine „Verbesserungen“ nebenbei, keine neuen Funktionen.
- Keine Typannotationen. Die könnten später kommen, Datei für Datei.
- Kein Umbau der Mixins zu eigenständigen Objekten (siehe „Verworfen“).
- `ui.py`, `elements.py` usw. bleiben, wie sie sind.

## Zu beachten

- **`git blame`:** Verschobene Zeilen erscheinen als neu. Mit `git blame -C -C` findet Git
  die Herkunft trotzdem. Darum je Schritt nur verschieben und nichts gleichzeitig ändern.
- **Zirkuläre Imports:** Die Mixins importieren `canvas.py` nie. Was sie brauchen, kommt
  aus `settings.py`, `elements.py`, `commands.py` usw.
- **Reihenfolge der Basisklassen:** Mixins stehen vor `QGraphicsView`. Zwei Mixins dürfen
  nicht dieselbe Methode definieren. Das prüft ein kurzer Test (`set(dir(A)) & set(dir(B))`
  ohne Dunder-Namen ist leer).

## Entschieden

- Flache Dateien mit Präfix `canvas_…`, kein Paket.
- Reihenfolge: zuerst Schritt 6 (CLAUDE.md verschlanken), dann 1–5.
