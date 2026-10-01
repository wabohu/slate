"""Verlauf-Teil der Canvas (Roadmap 10): Screenshot automatisch speichern, mit ← → blättern.

Ablauf im Screenshot-Modus (nie im Whiteboard):
- Start: start_history() merkt sich den Dateinamen für einen neuen Eintrag (Zeitpunkt des
  Screenshots), schreibt aber noch nichts. Screenshots ohne Änderung landen nie im Verlauf.
- Jede Änderung (Undo-Stack ändert sich): nach kurzer Pause speichern, beim ersten Mal
  entsteht die Datei (und alte Einträge werden aufgeräumt). So kostet auch ein Absturz
  höchstens die letzte Sekunde. Während getippt, gezeichnet oder
  gezogen wird, wartet das Speichern, bis die Aktion fertig ist.
- Beenden: Ausstehendes sofort speichern (flush_history).
- ← / →: aktuellen Stand sichern, älteren bzw. neueren Eintrag in dieselbe Canvas laden.
  Undo beginnt dort neu; Änderungen landen wieder in diesem Eintrag.

Qt-Konzept QTimer: Ein Einmal-Timer (setSingleShot) ruft nach Ablauf eine Funktion auf.
Erneutes start() setzt ihn zurück; so speichert er erst, wenn eine Weile Ruhe ist.

Mixin wie BoardMixin (canvas_board.py). Verwaltet (angelegt in Canvas.__init__):
history_path (aktueller Eintrag oder None = kein Verlauf), history_timer.
Liest aus der Canvas: board, settings, scene_, export_rect, export_size, background_image,
editing_text, current_item, dragging, resizing, elements(), finish_text(),
replace_content(), report().
"""
import sys

from PySide6.QtGui import QImage, QPixmap

import history
from document import build_document, load_document, save_document
from export import render_scene

HISTORY_SAVE_DELAY_MS = 1000  # so lange Ruhe nach einer Änderung, dann wird gespeichert


class HistoryMixin:
    def start_history(self, path=None):
        """Verlauf für diese Sitzung einschalten. path=None: neuer Eintrag (frischer
        Screenshot); sonst ein vorhandener Eintrag (aus dem Verlauf geöffnet)."""
        if self.board or not self.settings.history_enabled:
            return
        directory = self.settings.history_dir
        if path is None:
            try:
                path = history.new_entry(directory)  # nur der Name, die Datei kommt beim Speichern
            except OSError as e:
                self.report(f"Verlauf aus: {e}", error=True)
                return
        self.history_path = path

    def schedule_history_save(self, _index=None):
        """Nach einer Änderung: Speichern vormerken (Timer neu starten)."""
        if self.history_path is not None:
            self.history_timer.start(HISTORY_SAVE_DELAY_MS)

    def busy(self):
        """Läuft gerade eine Aktion (Tippen, Aufziehen, Ziehen)? Dann nicht speichern."""
        return bool(self.editing_text or self.current_item or self.dragging or self.resizing)

    def save_history(self):
        """Aktuellen Stand in den Verlaufseintrag schreiben (vom Timer aufgerufen)."""
        if self.history_path is None:
            return
        if self.busy():
            self.history_timer.start(HISTORY_SAVE_DELAY_MS)  # später noch einmal
            return
        if not self.history_path.exists():  # erster Stand dieses Eintrags: Platz schaffen
            history.prune(self.settings.history_dir, self.settings.history_keep - 1)
        # Direkt rendern statt render_image(): das würde Auswahl und Texteingabe beenden
        rendered = render_scene(self.scene_, self.export_rect, self.export_size)
        ok, message = save_document(self.history_path, rendered,
                                    build_document(self.background_image, self.elements()))
        if not ok:
            print(f"[history] {message}", file=sys.stderr)

    def flush_history(self):
        """Beim Beenden oder Blättern: Ausstehendes sofort speichern."""
        if self.history_path is None or not self.history_timer.isActive():
            return
        self.history_timer.stop()
        if self.editing_text:
            self.finish_text()
        self.save_history()

    def history_step(self, step):
        """← (step=-1) älterer, → (step=+1) neuerer Eintrag."""
        if self.board:
            return
        if self.history_path is None:
            self.report("Kein Verlauf (ausgeschaltet oder Datei außerhalb des Verlaufs geöffnet)")
            return
        self.flush_history()
        files = history.entries(self.settings.history_dir)
        names = [p.name for p in files]
        current = names.index(self.history_path.name) if self.history_path.name in names else len(files)
        target = current + step
        if not 0 <= target < len(files):
            self.report("Ältester Eintrag im Verlauf" if step < 0 else "Neuester Eintrag im Verlauf")
            return
        background, elements, _, message = load_document(files[target])
        if not isinstance(background, QImage):  # unlesbar (None) oder Whiteboard (QColor)
            self.report(f"Verlauf: {message}", error=True)
            return
        self.replace_content(QPixmap.fromImage(background), elements)
        self.history_path = files[target]
        self.report(f"Verlauf {target + 1}/{len(files)}: {history.label(files[target])}")
