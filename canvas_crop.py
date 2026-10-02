"""Ausschnitt-Teil der Canvas (Bereichsauswahl, Taste y, nur Screenshot-Modus).

y startet die Auswahl: Rahmen aufziehen, danach geht es mit dem Werkzeug weiter. Gibt es
schon einen Ausschnitt, zeigt y Griffe: Griff ziehen = Größe, innen ziehen = verschieben,
außen ziehen = neu aufziehen. Außerhalb
des Ausschnitts wird abgedunkelt (nur auf dem Bildschirm, drawForeground). Kopieren,
Speichern, Exportieren und der Verlauf nehmen als sichtbares Bild nur den Ausschnitt
(output_area); die bearbeitbare Datei behält den ganzen Screenshot und speichert den
Ausschnitt mit ("crop"), er bleibt also änderbar. Esc während der Auswahl hebt ihn auf.
Festlegen und Aufheben sind Undo-Schritte (PropertyCommand auf set_crop).

Mixin wie BoardMixin (canvas_board.py). Verwaltet (angelegt in Canvas.__init__):
crop_rect (QRectF in Szenenkoordinaten oder None), cropping (Auswahl läuft),
crop_drag (Startpunkt beim Ziehen oder None), crop_drag_end, crop_edit (beim Ziehen:
("resize", Griff), ("move", None) oder None = neu aufziehen).
Liest aus der Canvas: board, export_rect, export_size, scene_, undo_stack, ui_scale,
zoom(), refresh_cursor(), report().
"""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from commands import PropertyCommand
from settings import HANDLE_GRAB, HANDLE_SIZE

CROP_DIM = 110         # Abdunklung außerhalb des Ausschnitts, 0-255
CROP_MIN_SIZE = 5      # kleinere Rahmen (Bildschirm-Pixel) gelten als Klick: nichts ändern
# Griffe am Ausschnitt (relative Lage): Ecken und Kantenmitten, im Uhrzeigersinn ab oben links
CROP_HANDLES = ((0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5))
CROP_CURSORS = (Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor,
                Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor)


class CropMixin:
    # --- Zustand ---
    def set_crop(self, rect):
        """Setter für PropertyCommand: Ausschnitt (QRectF) oder None = ganzer Screenshot."""
        self.crop_rect = QRectF(rect) if rect is not None else None
        self.viewport().update()

    def output_area(self):
        """(Ausschnitt in der Szene, Größe in Bildpixeln) für Rendern und Speichern."""
        if self.crop_rect is None:
            return self.export_rect, self.export_size
        area = self.crop_rect.intersected(self.export_rect)
        factor = self.export_size.width() / max(1.0, self.export_rect.width())
        return area, QSize(max(1, round(area.width() * factor)), max(1, round(area.height() * factor)))

    # --- Taste y und Maus ---
    def crop_key(self):
        """y: Auswahl starten (mit vorhandenem Ausschnitt: Griffe zum Anpassen);
        läuft sie schon, abbrechen (Ausschnitt bleibt)."""
        if self.board:
            return
        self.cropping = not self.cropping
        self.crop_drag = None
        if self.cropping:
            self.stop_pointer()
            self.report("Ausschnitt anpassen: Griffe ziehen, innen verschieben, außen neu (Esc: aufheben)"
                        if self.crop_rect is not None else "Ausschnitt aufziehen (Esc: Ausschnitt aufheben)")
        self.refresh_cursor()
        self.viewport().update()

    def cancel_crop(self):
        """Esc während der Auswahl: Ausschnitt aufheben (Undo-Schritt), Auswahl beenden."""
        self.cropping = False
        self.crop_drag = None
        if self.crop_rect is not None:
            self.undo_stack.push(PropertyCommand(self.set_crop, QRectF(self.crop_rect), None, "Ausschnitt aufheben"))
        self.refresh_cursor()
        self.viewport().update()

    def crop_handle_points(self, rect):
        return [QPointF(rect.left() + fx * rect.width(), rect.top() + fy * rect.height()) for fx, fy in CROP_HANDLES]

    def crop_hit(self, pos):
        """Was liegt unter pos? ("resize", Griff), ("move", None) oder None (außerhalb: neu aufziehen)."""
        if self.crop_rect is None:
            return None
        grab = HANDLE_GRAB / self.zoom()  # Fangradius auf dem Bildschirm immer gleich
        for index, point in enumerate(self.crop_handle_points(self.crop_rect)):
            if abs(point.x() - pos.x()) <= grab and abs(point.y() - pos.y()) <= grab:
                return ("resize", index)
        return ("move", None) if self.crop_rect.contains(pos) else None

    def crop_hover(self, pos):
        """Mauszeiger während der Auswahl: Größenpfeile über Griffen, Kreuzpfeil innen."""
        hit = self.crop_hit(pos)
        if hit is None:
            cursor = Qt.CrossCursor
        elif hit[0] == "move":
            cursor = Qt.SizeAllCursor
        else:
            cursor = CROP_CURSORS[hit[1]]
        self.viewport().setCursor(cursor)

    def crop_press(self, pos):
        self.crop_drag = self.crop_drag_end = pos
        self.crop_edit = self.crop_hit(pos)  # None = neu aufziehen

    def crop_move(self, pos):
        self.crop_drag_end = pos
        self.viewport().update()

    def crop_preview(self):
        """Ausschnitt, wie er gerade aussieht (beim Ziehen schon mit der Änderung)."""
        if self.crop_drag is None:
            return self.crop_rect
        start, end = self.crop_drag, self.crop_drag_end
        if self.crop_edit is None:
            return QRectF(start, end).normalized().intersected(self.export_rect)
        mode, index = self.crop_edit
        rect = QRectF(self.crop_rect)
        dx, dy = end.x() - start.x(), end.y() - start.y()
        bounds = self.export_rect
        if mode == "move":  # verschieben, aber im Screenshot bleiben
            dx = min(max(dx, bounds.left() - rect.left()), bounds.right() - rect.right())
            dy = min(max(dy, bounds.top() - rect.top()), bounds.bottom() - rect.bottom())
            return rect.translated(dx, dy)
        fx, fy = CROP_HANDLES[index]
        if fx == 0:
            rect.setLeft(rect.left() + dx)
        elif fx == 1:
            rect.setRight(rect.right() + dx)
        if fy == 0:
            rect.setTop(rect.top() + dy)
        elif fy == 1:
            rect.setBottom(rect.bottom() + dy)
        return rect.normalized().intersected(bounds)

    def crop_release(self, pos):
        self.crop_drag_end = pos
        rect = self.crop_preview()
        self.crop_drag = self.crop_edit = None
        self.cropping = False
        self.refresh_cursor()
        if rect is not None and min(rect.width(), rect.height()) * self.zoom() >= CROP_MIN_SIZE \
                and rect != self.crop_rect:
            old = QRectF(self.crop_rect) if self.crop_rect is not None else None
            self.undo_stack.push(PropertyCommand(self.set_crop, old, rect, "Ausschnitt"))
        self.viewport().update()

    # --- Anzeige ---
    def paint_crop(self, painter):
        """Außerhalb des Ausschnitts abdunkeln, Rahmen und Größe zeigen (nie im Export)."""
        if self.board:
            return
        rect = self.crop_preview()  # beim Ziehen schon mit der Änderung
        if rect is None:
            return
        rect = rect.intersected(self.export_rect)
        s = self.ui_scale
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        outside = QPainterPath()
        outside.addRect(self.mapToScene(self.viewport().rect()).boundingRect().united(self.export_rect))
        inside = QPainterPath()
        inside.addRect(rect)
        painter.fillPath(outside.subtracted(inside), QColor(0, 0, 0, CROP_DIM))
        painter.setBrush(Qt.NoBrush)
        # Dunkle Linie unter der hellen gestrichelten: auf hellem und dunklem Grund sichtbar
        for color, style in ((QColor(0, 0, 0, 170), Qt.SolidLine), (QColor(255, 255, 255, 230), Qt.DashLine)):
            pen = QPen(color, 1.5 * s, style)
            pen.setCosmetic(True)  # auf dem Bildschirm immer gleich dick, egal wie gezoomt
            painter.setPen(pen)
            painter.drawRect(rect)
        if self.cropping and self.crop_rect is not None and (self.crop_drag is None or self.crop_edit is not None):
            line, fill = self.selection_colors()  # wie die Griffe der Auswahl
            handle_pen = QPen(line, 1.5)
            handle_pen.setCosmetic(True)
            painter.setPen(handle_pen)
            painter.setBrush(fill)
            size = HANDLE_SIZE / self.zoom()
            for p in self.crop_handle_points(rect):
                painter.drawRect(QRectF(p.x() - size / 2, p.y() - size / 2, size, size))
        # Größe in Bildpixeln unten rechts am Rahmen, in Bildschirmkoordinaten
        factor = self.export_size.width() / max(1.0, self.export_rect.width())
        label = f"{round(rect.width() * factor)} × {round(rect.height() * factor)}"
        corner = self.mapFromScene(rect.bottomRight())
        painter.resetTransform()
        font = QFont()
        font.setPixelSize(round(12 * s))
        painter.setFont(font)
        box = QRectF(corner.x() - 120 * s, corner.y() + 4 * s, 120 * s, 20 * s)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        width = painter.fontMetrics().horizontalAdvance(label) + 12 * s
        painter.drawRoundedRect(QRectF(box.right() - width, box.top(), width, box.height()), 4 * s, 4 * s)
        painter.setPen(QColor("white"))
        painter.drawText(box.adjusted(0, 0, -6 * s, 0), Qt.AlignRight | Qt.AlignVCenter, label)
        painter.restore()


