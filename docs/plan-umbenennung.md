# Plan: Umbenennung annotate → slate

Ziel: Das Tool heißt `slate`, überall: Befehl, Fenstertitel, Meldungen, Ordner,
Dateiformat und Doku. Alte Zeichnungen und Verlauf sind nicht wichtig (Testphase,
2026-10-02), darum kein Code für Rückwärtskompatibilität. Nur die eigene Config zieht um.

Name geprüft (2026-10-02): kein Befehl `slate` auf dem System, kein offizielles
Arch-Paket. Im AUR gibt es `slate` (Qt-Pixel-Art-Editor), stört nur, wenn man ihn
installiert.

## Vorher

- Offene Änderungen (`canvas_input.py`, `canvas_pointer.py`, `docs/bedienung.md`,
  `tests/test_document.py`) erst fertig machen und committen, damit die Umbenennung
  ein eigener, sauberer Commit wird.
- **Aufgefallen:** `~/.local/bin/annotate-board` zeigt auf
  `~/vibecoding/annotate.py`, das gibt es nicht mehr. Die Hotkeys
  Alt+Escape und Alt+Delete starten im Moment also nichts. Wird in Schritt 1 behoben.

## Dateiformat und Zwischenablage

Auch die internen Namen werden umbenannt, ohne den alten weiter zu lesen:

- `document.py`: `FORMAT = "slate"`, `PNG_KEY = "slate"` (PNG-Text-Chunk). Alte
  `annotate`-PNGs öffnen sich danach nur noch als flaches Bild (Markierungen
  eingebrannt), ohne Absturz. Fehlermeldung „kein annotate-Dokument“ anpassen
- `canvas_output.py`: `ELEMENTS_MIME = "application/x-slate-elements"`,
  `CLIP_FORMAT = "slate-elements"`
- `tests/test_document.py`: `QImage.text("slate")`

## Schritt 1: Startdatei und Befehl

- `git mv annotate.py slate.py` (behält die Rechte `755`, `git diff --summary` prüfen)
- Docstring in `slate.py` anpassen (Aufrufe `python slate.py …`, Symlink)
- Symlink neu: `ln -sfn ~/1_Projekte/privat/annotate-board/slate.py ~/.local/bin/slate`,
  alten `annotate-board`-Symlink löschen
- `~/.config/herbstluftwm/keybindings.sxhkd`: `annotate-board` → `slate` (3 Stellen,
  Kommentar `# annotate` → `# slate`), danach `pkill -USR1 sxhkd` (Config neu laden)
- Tests: `tests/gui/harness.py` (`ANNOTATE` → `SLATE`, Prüfung `b"slate.py"` in der
  Kommandozeile, `annotate_pids()` → `slate_pids()`), alle `tests/gui/test_*.py`
  (Aufrufe von `annotate_pids`)

## Schritt 2: Sichtbare Namen

- `canvas_board.py`: Fenstertitel `slate – Whiteboard – …`, Titel der Nachfrage beim
  Schließen
- `notify.py`: `--app-name=slate` und Überschrift der Meldung (dunst-Regeln, die auf
  `annotate` passen, müsstest du selbst anpassen)
- `rofi/annotate.rasi` → `rofi/slate.rasi` (`git mv`), Pfad in `notify.py`, Kommentar
  in `settings.py`
- Docstrings/Kommentare in `ui.py`, `tools.py`, `config.py`, `export.py`, `history.py`

## Schritt 3: Ordner und Dateinamen

| Alt | Neu | Was drin ist |
|---|---|---|
| `~/.config/annotate/` | `~/.config/slate/` | `config.toml` (+ `.bak`) |
| `~/.local/share/annotate/history/` | `~/.local/share/slate/history/` | Verlauf (36 Dateien) |
| `~/Pictures/annotate/` | `~/Pictures/slate/` | gespeicherte Bilder |
| `$XDG_RUNTIME_DIR/annotate/` | `$XDG_RUNTIME_DIR/slate/` | `clipboard.json` (nur vorübergehend) |

Neue Dateien heißen `slate_2026-…png` statt `annotate_2026-…png` (`export.py`,
`history.py`: `_NAME_RE` nur noch mit `slate_`).

Umzug von Hand, nur die Config (deine eigenen Werte). Verlauf, Bilder und
Zwischenablage-Datei werden nicht übernommen; die alten Ordner kannst du löschen,
wenn alles läuft:

```sh
mv ~/.config/annotate ~/.config/slate
# später, nach den Handtests:
rm -r ~/.local/share/annotate ~/Pictures/annotate
```

Kein Rückfall-Code auf die alten Pfade. Fehlt ein Ordner, gelten wie immer die
Standardwerte bzw. er wird beim ersten Speichern angelegt.

Mitändern: `config.example.toml` (Kommentare, `dir`-Standardwerte),
`scripts/sync_config.py`, `scripts/git-hooks/pre-commit`, `tests/regress.py`,
`tests/gui/harness.py` (Config- und Verlaufsordner), `tests/test_document.py`
(`glob("slate_*.png")`).

## Schritt 4: Doku

- `CLAUDE.md`: Projektname, `slate.py`, Symlink `~/.local/bin/slate`, Pfade, rofi-Theme,
  PNG-Text-Chunk `slate`, MIME-Typ `application/x-slate-elements`
- `docs/bedienung.md`, `docs/roadmap.md` (Pfad des Verlaufs)
- Alte Pläne (`plan-aufteilung.md`, `plan-datenmodell.md`, `plan-bedienung.md`) bleiben,
  wie sie sind: Sie beschreiben den Stand von damals

## Schritt 5: Repo-Ordner (optional, zuletzt)

`~/1_Projekte/privat/annotate-board` → `~/1_Projekte/privat/slate`. Danach:

- Symlink `~/.local/bin/slate` neu setzen (zeigt sonst ins Leere, wie jetzt gerade)
- Git-Hook bleibt aktiv (`core.hooksPath` ist relativ)
- Claude-Code-Gedächtnis hängt am Pfad: `~/.claude-privat/projects/…-annotate-board`
  nach `…-privat-slate` umbenennen
- Ein Remote gibt es nicht, also nichts weiter

## Prüfen

Nach Schritt 1–4: alle Tests (`python tests/gui/run.py`, `tests/regress.py`,
`tests/test_document.py`, `tests/test_settings.py`). Die Referenz für `regress.py`
ändert sich nicht (der Name taucht im Bild nicht auf).

Handtests bei dir:
- Alt+Escape und Alt+Delete starten das Tool
- Deine Config-Werte gelten noch (z. B. Farben, Tasten)
- dunst-Meldung heißt `slate`, Whiteboard-Fenstertitel ebenso
- Screenshot ändern, schließen, neu öffnen: ← zeigt ihn im neuen Verlauf

Ein Commit für Schritt 1–4 („Umbenennung annotate → slate“), Schritt 5 braucht keinen.
