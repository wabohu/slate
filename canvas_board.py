"""Whiteboard-Teil der Canvas: Ansicht verschieben und zoomen, Hintergrund, Fenstertitel,
Nachfrage beim Schließen. Nur im Whiteboard (board=True) aktiv.

Qt/Python-Konzept Mixin: BoardMixin hat kein eigenes __init__ und ist allein nicht
lauffähig. Canvas erbt davon (class Canvas(BoardMixin, QGraphicsView)), so landen die
Methoden in der Canvas, als stünden sie dort. Siehe docs/plan-aufteilung.md.

Verwaltet (angelegt in Canvas.__init__): board_color, zoom_rest, overview_return.
Liest aus der Canvas: board, scene_, settings, palette_bar, toast, undo_stack,
document_path, elements(), used_rect(), zoom(), ask(), save_drawing().
"""
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox

from colors import adapt_color
from commands import PropertyCommand
from notify import NOT_AVAILABLE
from settings import WHEEL_PAN_STEP, ZOOM_RANGE, ZOOM_STEP, clamp


class BoardMixin:
    # --- Ansicht: verschieben und zoomen ---
    def pan_by(self, dx, dy):
        """Ansicht um dx/dy Bildschirm-Pixel verschieben (Inhalt folgt der Maus).

        Die Scrollbalken sind ausgeblendet, funktionieren aber weiter: Ihr Wert ist die
        Position der Ansicht in der großen Szene.
        """
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(dx))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(dy))

    def pan_by_wheel(self, event, swap):
        """Mausrad: senkrecht; Kipprad/Touchpad: waagerecht; Shift: Achsen tauschen."""
        pixels = event.pixelDelta()  # Touchpads liefern genaue Pixel
        if not pixels.isNull():
            dx, dy = pixels.x(), pixels.y()
        else:
            angle = event.angleDelta()
            dx, dy = angle.x() / 120 * WHEEL_PAN_STEP, angle.y() / 120 * WHEEL_PAN_STEP
        if swap:
            dx, dy = dy, dx
        self.pan_by(dx, dy)

    def zoom_by_wheel(self, delta, mouse):
        """Zoomen, wobei der Punkt unter dem Mauszeiger (mouse, Viewport-Koordinaten) stehen bleibt.

        Qts AnchorUnderMouse geht hier nicht: Es merkt sich die Mausposition in
        QGraphicsView.mouseMoveEvent, das wir überschreiben. Darum von Hand verankern.
        """
        self.zoom_rest += delta
        steps = int(self.zoom_rest / 120)
        if steps == 0:
            return
        self.zoom_rest -= steps * 120
        factor = clamp(self.zoom() * ZOOM_STEP ** steps, ZOOM_RANGE) / self.zoom()
        anchor = self.mapToScene(mouse.toPoint())  # Szenenpunkt unter der Maus
        self.scale(factor, factor)
        drift = self.mapFromScene(anchor) - mouse.toPoint()  # wohin er durchs Skalieren gewandert ist
        self.pan_by(-drift.x(), -drift.y())
        self.refresh_cursor()  # Kreis im Mauszeiger = Strichbreite bei diesem Zoom
        self.toast.show_message(f"Zoom {round(self.zoom() * 100)} %")

    def view_state(self):
        """Aktuelle Ansicht: Transformation (Zoom) und Szenenpunkt in der Fenstermitte."""
        return self.transform(), self.mapToScene(self.viewport().rect().center())

    def set_view_state(self, state):
        transform, center = state
        self.setTransform(transform)
        self.centerOn(center)

    def overview(self):
        """Whiteboard: alle Elemente ins Fenster einpassen (höchstens 100 %).

        Erneutes Strg+W springt zurück zur Ansicht davor, solange die Übersicht
        unverändert ist (nicht gezoomt oder verschoben); sonst wieder Übersicht.
        """
        if not self.board:
            return
        if self.overview_return:
            before, during = self.overview_return
            self.overview_return = None
            transform, center = self.view_state()
            if transform == during[0] and (center - during[1]).manhattanLength() < 1:
                self.set_view_state(before)
                self.refresh_cursor()
                self.toast.show_message(f"Zurück ({round(self.zoom() * 100)} %)")
                return
        before = self.view_state()
        if not self.elements():
            self.resetTransform()
            self.centerOn(0, 0)
        else:
            rect = self.used_rect()
            view = self.viewport().rect()
            factor = clamp(min(view.width() / rect.width(), view.height() / rect.height()),
                           (ZOOM_RANGE[0], 1.0))
            self.resetTransform()
            self.scale(factor, factor)
            self.centerOn(rect.center())
        self.overview_return = (before, self.view_state())
        self.refresh_cursor()
        self.toast.show_message(f"Übersicht ({round(self.zoom() * 100)} %)")

    def zoom_reset(self):
        if self.board:
            self.resetTransform()  # zurück auf 100 %, ohne Drehung/Verzerrung
            self.refresh_cursor()
            self.toast.show_message("Zoom 100 %")

    # --- Hintergrund ---
    def set_board_color(self, color):
        """Setter für PropertyCommand: Hintergrund des Whiteboards (wird mitgespeichert)."""
        self.board_color = QColor(color)
        self.scene_.setBackgroundBrush(self.board_color)
        self.refresh_colors()
        self.refresh_cursor()  # Stiftfarbe im Mauszeiger an den Hintergrund anpassen

    def adapt_color(self, color):
        """Gezeigte Farbe zur Grundfarbe color: auf hellem Whiteboard abgedunkelt
        (colors.adapt_color), sonst unverändert. Gespeichert wird immer die Grundfarbe."""
        if not self.board:
            return QColor(color)
        return QColor(adapt_color(QColor(color).name(), self.board_color.name(), self.settings.light_overrides))

    def refresh_colors(self):
        """Nach Hintergrundwechsel: Elemente und Farbleiste zeigen die passenden Varianten."""
        for item in self.elements():
            item.refresh_color()
        self.palette_bar.set_colors([self.adapt_color(c) for c in self.settings.swatches])
        self.viewport().update()

    def cycle_board_color(self, step):
        """Strg+B / Strg+Shift+B: nächster bzw. voriger Hintergrund aus der Liste.
        Ist der aktuelle nicht in der Liste (z. B. aus einer Datei), geht es beim ersten
        bzw. letzten los. Nur im Whiteboard."""
        if not self.board:
            return
        colors = self.settings.board_backgrounds
        current = next((i for i, c in enumerate(colors) if c == self.board_color), None)
        if current is None:
            new = colors[0] if step > 0 else colors[-1]
        else:
            new = colors[(current + step) % len(colors)]
        if new == self.board_color:
            return  # nur ein Eintrag: nichts zu tun, kein leerer Undo-Schritt
        self.undo_stack.push(PropertyCommand(
            self.set_board_color, QColor(self.board_color), QColor(new), "Hintergrund ändern"))

    # --- Fenster ---
    def update_title(self):
        name = Path(self.document_path).name if self.document_path else "neu"
        self.setWindowTitle(f"annotate – Whiteboard – {name}")

    def confirm_close(self):
        """Ungespeicherte Änderungen? Fragen: Speichern, Verwerfen oder Abbrechen."""
        choice = self.ask("Das Whiteboard hat ungespeicherte Änderungen.",
                          ["Speichern", "Verwerfen", "Abbrechen"])
        if choice is not NOT_AVAILABLE:
            if choice == 0:
                self.save_drawing()
                return self.undo_stack.isClean()
            return choice == 1  # Abbrechen oder Esc: offen lassen
        answer = QMessageBox.question(
            self, "annotate", "Das Whiteboard hat ungespeicherte Änderungen. Speichern?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            self.save_drawing()
            return self.undo_stack.isClean()  # nur schließen, wenn das Speichern geklappt hat
        return answer == QMessageBox.Discard
