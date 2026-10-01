"""Ausgabe-Teil der Canvas: Bild rendern, kopieren, speichern, exportieren, dazu
Meldungen (report) und Nachfragen (ask) über dunst/rofi oder Qt.

Mixin wie BoardMixin (canvas_board.py): kein eigenes __init__, Canvas erbt davon.
Die eigentliche Arbeit (Rendern, Zwischenablage, PNG schreiben, dunst, rofi) machen
export.py, document.py und notify.py; hier steht nur, was die Canvas dafür beisteuert.

Verwaltet (angelegt in Canvas.__init__): document_path.
Liest aus der Canvas: board, board_color, background_image, export_rect, export_size,
scene_, settings, toast, undo_stack, editing_text, finish_text(), update_bars(),
elements(), update_title().
"""
from pathlib import Path

from PySide6.QtCore import QRectF

from document import build_document, save_document
from export import (copy_text_to_clipboard, copy_to_clipboard, new_file_path, render_scene, save_png,
                    short_path)
from notify import NOT_AVAILABLE, ask, notify
from settings import BOARD_EXPORT_MARGIN


class OutputMixin:
    # --- Bild: rendern, kopieren, speichern ---
    def render_image(self):
        """Screenshot plus Zeichnungen als QImage, ohne Leiste und ohne Textcursor."""
        if self.editing_text:
            self.finish_text()
        self.scene_.clearSelection()  # sonst wäre der gestrichelte Auswahlrahmen im Bild
        self.update_bars()
        if self.board:  # nur der benutzte Bereich, Maßstab 1:1
            rect = self.used_rect()
            return render_scene(self.scene_, rect, rect.size().toSize())
        return render_scene(self.scene_, self.export_rect, self.export_size)

    def used_rect(self):
        """Whiteboard: Bereich aller Elemente plus Rand; leer = sichtbarer Ausschnitt."""
        items = self.elements()
        if not items:
            return QRectF(self.mapToScene(self.viewport().rect()).boundingRect().toAlignedRect())
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-BOARD_EXPORT_MARGIN, -BOARD_EXPORT_MARGIN,
                             BOARD_EXPORT_MARGIN, BOARD_EXPORT_MARGIN)
        return QRectF(rect.toAlignedRect())  # auf ganze Pixel, damit das Bild nicht verschwimmt

    def copy_image(self):
        ok, message = copy_to_clipboard(self.render_image())
        self.report(message, error=not ok)
        return ok

    def copy_and_quit(self):
        """Enter: kopieren und beenden; im Whiteboard nur kopieren (Fenster bleibt)."""
        if self.copy_image() and not self.board:
            self.close()

    def copy_path_and_quit(self):
        """Shift+Enter: speichern wie Strg+S, absoluten Pfad der Datei in die Zwischenablage,
        beenden; im Whiteboard bleibt das Fenster offen (wie bei Enter)."""
        path = self.save_drawing()
        if path is None:
            return  # Fehler hat save_drawing schon gemeldet
        path = Path(path).resolve()
        copy_text_to_clipboard(str(path))
        self.report(f"Pfad kopiert: {short_path(path)}")
        if not self.board:
            self.close()

    def export_image(self):
        """Sauberes PNG ohne Bearbeitungsdaten, immer als neue Datei."""
        path, message = save_png(self.render_image(), self.settings.output_dir)
        self.report(message, error=path is None)

    def save_drawing(self):
        """Bearbeitbare Zeichnung: beim ersten Mal neue Datei, danach dieselbe überschreiben.
        Rückgabe: Pfad der Datei, bei Fehler None."""
        rendered = self.render_image()
        try:
            path = self.document_path or new_file_path(self.settings.output_dir, "_board" if self.board else "")
        except OSError as e:
            self.report(f"Speichern fehlgeschlagen: {e}", error=True)
            return None
        background = self.board_color if self.board else self.background_image
        ok, message = save_document(path, rendered, build_document(background, self.elements()))
        if ok:
            self.document_path = path
            self.undo_stack.setClean()  # Stand merken: ab hier "nichts ungespeichert"
            if self.board:
                self.update_title()
        self.report(message, error=not ok)
        return path if ok else None

    # --- Meldungen und Nachfragen ---
    def report(self, text, error=False):
        """Ergebnis-Meldung (Gespeichert, Kopiert, Fehler …): per dunst, sonst Einblendung."""
        if not (self.settings.use_dunst and notify(text, error=error)):
            self.toast.show_message(text)

    def ask(self, question, choices):
        """Auswahl per rofi, sonst None. NOT_AVAILABLE = rofi nicht benutzbar (Qt nehmen).

        Im Screenshot-Modus holt sich das Overlay danach den Fokus zurück (rofi hatte ihn).
        """
        if not self.settings.use_rofi:
            return NOT_AVAILABLE
        try:
            return ask(question, choices, self.settings.rofi_theme)
        finally:
            if not self.board:
                self.take_focus()
