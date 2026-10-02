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
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QPainter

from commands import AddItemCommand
from document import build_document, elements_from_dicts, save_document
from elements import ImageElement, ShapeElement, blur_block, new_id, pixelate
from export import (copy_data_to_clipboard, copy_text_to_clipboard, copy_to_clipboard, data_from_clipboard,
                    new_file_path, png_bytes, render_scene, save_png, short_path)
from notify import NOT_AVAILABLE, ask, notify
from settings import BOARD_EXPORT_MARGIN
from tools import Tool

# Kopierte Elemente in der Zwischenablage: eigener Datentyp, JSON wie im Dateiformat
ELEMENTS_MIME = "application/x-slate-elements"
CLIP_FORMAT = "slate-elements"
DUPLICATE_OFFSET = 20  # Strg+D: Versatz in Bildschirm-Pixeln


def rich_copy_path():
    """Private Datei mit der bearbeitbaren Fassung des zuletzt kopierten Bildes."""
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / "slate" / "clipboard.json"


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
        return render_scene(self.scene_, *self.output_area())  # ganzer Screenshot oder Ausschnitt

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

    # --- Elemente kopieren, einfügen, duplizieren ---
    def copy_selection_or_image(self):
        """Strg+C: mit Auswahl die Elemente (zum Einfügen, auch in einem anderen Fenster),
        sonst das ganze Bild wie bisher."""
        items = self.selected_elements()
        if not items or self.editing_text:
            return self.copy_image()
        data = json.dumps({"format": CLIP_FORMAT, "elements": [i.to_dict() for i in items]})
        copy_data_to_clipboard(data.encode(), ELEMENTS_MIME)
        self.report(f"{len(items)} Element(e) kopiert (Strg+V fügt ein)")

    def paste_elements(self):
        """Strg+V: kopierte Elemente an der Mausposition einfügen (sonst in der Mitte)."""
        dicts = self.clipboard_elements()
        mouse = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(mouse):
            mouse = self.viewport().rect().center()
        self.insert_copies(dicts, target=self.mapToScene(mouse))

    def clipboard_elements(self):
        """Was Strg+V einfügt, als Element-Dicts: kopierte Elemente; sonst ein Bild aus der
        Zwischenablage, und zwar die bearbeitbare Fassung, wenn es unser kopiertes Bild ist."""
        raw = data_from_clipboard(ELEMENTS_MIME)
        if raw:
            try:
                return json.loads(raw)["elements"]
            except (ValueError, KeyError, TypeError):
                pass  # unbrauchbar: vielleicht liegt ein Bild darin
        png = data_from_clipboard("image/png")
        if png:
            try:
                rich = json.loads(rich_copy_path().read_text())
                if rich.get("png_sha256") == hashlib.sha256(png).hexdigest():
                    return rich["elements"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
            image = QImage.fromData(png)
        else:  # andere Bildformate (JPG …), soweit Qt sie kennt
            image = QGuiApplication.clipboard().image()
        if image.isNull():
            return []
        return [ImageElement(QPointF(0, 0), image).to_dict()]

    def duplicate_selected(self):
        """Strg+D: Auswahl leicht versetzt verdoppeln (Zwischenablage bleibt unberührt)."""
        items = self.selected_elements()
        if items:
            step = DUPLICATE_OFFSET / self.zoom()
            self.insert_copies([i.to_dict() for i in items], offset=QPointF(step, step))

    def insert_copies(self, dicts, target=None, offset=None):
        """Elemente aus dicts neu anlegen (neue IDs, Marker zählen weiter), entweder mit ihrer
        Mitte bei target oder um offset versetzt; ein Undo-Schritt, danach ausgewählt."""
        dicts = [dict(d, id=new_id()) for d in dicts
                 if not (self.board and d.get("tool") == "blur")]  # im Whiteboard nichts zu verpixeln
        items = elements_from_dicts(dicts)
        if not items:
            self.report("Nichts zum Einfügen (Elemente oder ein Bild kopieren)")
            return
        order = self.next_marker_order()
        for item in sorted(items, key=lambda i: getattr(i, "marker_order", 0)):
            if isinstance(item, ShapeElement) and item.tool == Tool.MARKER:
                item.marker_order = order
                order += 1
        if target is not None:
            box = QRectF()
            for item in items:
                box = box.united(item.sceneBoundingRect())
            offset = target - box.center()
        for item in items:
            item.setPos(item.pos() + offset)
        if self.editing_text:
            self.finish_text()
        self.set_tool(Tool.SELECT)
        self.scene_.clearSelection()
        self.undo_stack.beginMacro("Einfügen")
        for item in items:
            self.undo_stack.push(AddItemCommand(self.scene_, item, "Einfügen"))
        self.undo_stack.endMacro()
        for item in items:
            item.setSelected(True)
        self.update_bars()

    def copy_image(self):
        """Fertiges Bild in die Zwischenablage (Enter, Strg+C ohne Auswahl). Im Screenshot-Modus
        zusätzlich die bearbeitbare Fassung ablegen (rich_copy), fürs Einfügen im Whiteboard."""
        image = self.render_image()
        ok, message = copy_to_clipboard(image)
        if ok and not self.board:
            self.store_rich_copy(png_bytes(image))
        self.report(message, error=not ok)
        return ok

    def store_rich_copy(self, png):
        """Bearbeitbare Fassung des kopierten Bildes: Screenshot-Teil als Bild-Element (Unschärfe
        eingebrannt) plus die Markierungen darin als Elemente. Liegt in einer privaten Datei,
        erkannt am Fingerabdruck des PNG (xclip bietet nur einen Datentyp an)."""
        area, size = self.output_area()
        factor = size.width() / max(1.0, area.width())
        background = self.background_to_save().copy(QRectF(area.x() * factor, area.y() * factor,
                                                           size.width(), size.height()).toRect())
        dicts = [ImageElement(area.topLeft(), background, area.size()).to_dict()]
        dicts += [e.to_dict() for e in self.elements()
                  if e.sceneBoundingRect().intersects(area)
                  and not (isinstance(e, ShapeElement) and e.tool == Tool.BLUR)]  # steckt schon im Bild
        try:
            path = rich_copy_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"format": CLIP_FORMAT, "png_sha256": hashlib.sha256(png).hexdigest(),
                                        "elements": dicts}))
            path.chmod(0o600)
        except OSError as e:
            print(f"[output] bearbeitbare Kopie nicht abgelegt: {e}", file=sys.stderr)

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
        background = self.board_color if self.board else self.background_to_save()
        crop = None if self.board else self.crop_rect
        ok, message = save_document(path, rendered, build_document(background, self.elements(), crop))
        if ok:
            self.document_path = path
            self.undo_stack.setClean()  # Stand merken: ab hier "nichts ungespeichert"
            if self.board:
                self.update_title()
        self.report(message, error=not ok)
        return path if ok else None

    def background_to_save(self):
        """Rohbild für die bearbeitbare Datei, Unschärfe-Bereiche darin eingebrannt: Keine
        gespeicherte Datei enthält je, was verpixelt wurde. Im laufenden Tool bleibt das
        Rohbild unverändert (Unschärfe verschieben/löschen geht dort weiter)."""
        blurs = [e for e in self.elements() if isinstance(e, ShapeElement) and e.tool == Tool.BLUR]
        if not blurs:
            return self.background_image
        image = self.background_image.copy()
        factor = self.scene_.blur_scale
        painter = QPainter(image)
        for element in blurs:
            r = element.mapRectToScene(element.path().boundingRect())
            result = pixelate(self.background_image, QRectF(r.x() * factor, r.y() * factor,
                                                            r.width() * factor, r.height() * factor),
                              blur_block(element.width) * factor)
            if result:
                painter.drawImage(result[1].topLeft(), result[0])
        painter.end()
        return image

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
        self.asking = True  # rofi hat jetzt den Fokus, nicht zurückholen
        try:
            return ask(question, choices, self.settings.rofi_theme)
        finally:
            self.asking = False
            if not self.board:
                self.take_focus()
