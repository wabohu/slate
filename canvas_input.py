"""Eingabe-Teil der Canvas: Maus (zeichnen, auswählen, verschieben, Griffe ziehen),
Texteingabe, Auswahlrahmen mit Griffen, Mausrad (Größe fein, im Whiteboard verschieben/
zoomen über BoardMixin), Auswahl mit hjkl verschieben und löschen.

Mixin wie BoardMixin (canvas_board.py): kein eigenes __init__, Canvas erbt davon.
super().mousePressEvent(event) usw. landet bei QGraphicsView (Qts Standardverhalten,
z. B. Cursor setzen im Text-Editor).

Verwaltet (angelegt in Canvas.__init__): current_item, start_pos, editing_text,
editing_old, dragging, drag_offset, drag_start, passthrough, wheel_rest, resizing, panning.
Liest aus der Canvas: tool, board, board_color, pen_color, pen_width, text_size, scene_,
settings, toast, undo_stack, selected_element(), element_at(), zoom(), update_bars(),
pan_by(), pan_by_wheel(), zoom_by_wheel().
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from colors import contrast
from commands import (AddItemCommand, EditTextCommand, MoveItemCommand, PropertyCommand, RemoveItemCommand,
                      property_command)
from elements import ShapeElement, TextElement
from settings import (HANDLE_GRAB, HANDLE_SIZE, STROKE_WIDTH_RANGE, TEXT_SIZE_RANGE, WHEEL_STROKE_STEP,
                      WHEEL_TEXT_STEP, clamp)
from tools import Tool


class InputMixin:
    # --- Maus: zeichnen, auswählen, verschieben, Griffe ziehen ---
    def mousePressEvent(self, event):
        if not self.board and not self.isActiveWindow():
            self.take_focus()  # ein Hotkey hat den Fokus woanders hingelegt: per Klick zurück
        if self.help_panel.isVisible():  # Klick neben die Tastenübersicht schließt nur sie
            self.help_panel.hide()
            return
        if self.pointer_mode and event.button() == Qt.LeftButton:
            return  # Spotlight/Lupe: Klicks zeichnen nichts (mittlere Taste verschiebt weiter)
        if self.cropping and event.button() == Qt.LeftButton:
            self.crop_press(self.mapToScene(event.position().toPoint()))  # Ausschnitt aufziehen
            return
        if event.button() == Qt.MiddleButton and self.board:
            self.panning = event.position()  # Ansicht verschieben beginnt
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if event.button() != Qt.LeftButton:
            return
        pos = self.mapToScene(event.position().toPoint())

        if self.editing_text:
            if self.editing_text.contains(self.editing_text.mapFromScene(pos)):
                # Klick in den gerade bearbeiteten Text: Qt setzt Cursor bzw. markiert
                self.passthrough = True
                super().mousePressEvent(event)
                return
            # Klick daneben beendet die Eingabe nur
            self.finish_text()
            if self.tool in (Tool.TEXT, Tool.SELECT):
                return

        if self.tool == Tool.SELECT:
            handle = self.handle_at(pos)
            if handle is not None:  # Griff anfassen = Größe ändern
                item = self.selected_element()
                self.resizing = (item, handle, item.geometry())
                return
            item = self.element_at(pos)
            shift = bool(event.modifiers() & Qt.ShiftModifier)
            if item and shift:  # Shift+Klick: Element zur Auswahl dazu bzw. heraus
                item.setSelected(not item.isSelected())
            elif item:  # anklicken = auswählen und anfassen; Teil einer Auswahl: ziehen bewegt alle
                if not item.isSelected():
                    self.scene_.clearSelection()
                    item.setSelected(True)
                self.start_drag(self.selected_elements(), pos)
                self.click_only = item  # Loslassen ohne Ziehen: nur dieses Element auswählen
            else:  # leere Stelle: Auswahlrahmen aufziehen (Shift: zur Auswahl dazu)
                before = self.selected_elements() if shift else []
                if not shift:
                    self.scene_.clearSelection()
                self.rubber = (pos, pos, before)
            self.update_bars()
            return

        if self.tool == Tool.TEXT:
            item = self.text_at(pos)
            if item:  # vorhandenen Text anfassen zum Verschieben
                self.start_drag([item], pos)
            else:
                self.start_text(pos)
            return

        if self.current_item is not None:  # vorige Form ohne Loslassen (z. B. Doppelklick)
            self.finish_shape(pos)
        self.start_pos = pos
        self.current_item = ShapeElement(self.tool, pos, self.pen_color, self.pen_width,
                                         radius=self.settings.rect_radius)
        if self.tool == Tool.MARKER:
            self.current_item.marker_kind = self.marker_kind
            self.current_item.marker_order = self.next_marker_order()
        self.scene_.addItem(self.current_item)

    def mouseDoubleClickEvent(self, event):
        # Qt schickt beim zweiten Klick statt mousePressEvent ein DoubleClick-Event
        pos = self.mapToScene(event.position().toPoint())
        if self.editing_text:
            if self.editing_text.contains(self.editing_text.mapFromScene(pos)):
                self.passthrough = True
                super().mouseDoubleClickEvent(event)  # im Editor: Wort markieren
            else:
                self.mousePressEvent(event)  # daneben: Eingabe beenden wie bei einem Klick
            return
        item = self.text_at(pos) if self.tool in (Tool.TEXT, Tool.SELECT) else None
        left = event.button() == Qt.LeftButton
        if item and left:
            self.dragging = None
            self.edit_text(item, old=(item.toPlainText(), item.color, item.font_size))
        elif left and self.tool == Tool.SELECT and self.element_at(pos) is None:
            # Auswahl-Werkzeug, Doppelklick auf leere Stelle: neuer Text (wie Excalidraw).
            # Nur hier, in Zeichenwerkzeugen hätte der erste Klick schon etwas gezeichnet
            self.dragging = None
            self.start_text(pos)
        else:
            self.mousePressEvent(event)  # sonst wie ein normaler Klick behandeln

    def mouseMoveEvent(self, event):
        if self.panning is not None:
            delta = event.position() - self.panning
            self.panning = event.position()
            self.pan_by(delta.x(), delta.y())
            return
        if self.pointer_mode:
            self.viewport().update()  # Spotlight/Lupe folgen der Maus
            return
        if self.crop_drag is not None:
            self.crop_move(self.mapToScene(event.position().toPoint()))
            return
        if self.cropping:  # Zeiger über Griffen bzw. im Ausschnitt anpassen
            self.crop_hover(self.mapToScene(event.position().toPoint()))
            return
        if self.passthrough:
            super().mouseMoveEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        if self.resizing:
            item, handle, start = self.resizing
            if isinstance(item, TextElement):
                item.drag_handle(handle, pos, start, TEXT_SIZE_RANGE)
            else:
                item.drag_handle(handle, pos, start)
            self.viewport().update()
            return
        if self.dragging:
            delta = pos - self.drag_origin
            for item, start in zip(self.dragging, self.drag_starts):
                item.setPos(start + delta)
            self.viewport().update()  # Griffe wandern mit
            return
        if self.rubber is not None:
            start, _, before = self.rubber
            self.rubber = (start, pos, before)
            self.select_in_rubber()
            return
        if self.current_item is None:
            self.update_cursor(pos)  # nur Bewegung ohne Taste
            return
        # Werkzeug des Elements, nicht self.tool: ein Tastendruck mitten im Ziehen ändert nichts mehr
        if self.current_item.tool == Tool.FREEHAND:
            self.current_item.add_point(pos)
        else:
            self.current_item.set_end(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self.panning is not None:
            self.panning = None
            self.refresh_cursor()
            return
        if event.button() != Qt.LeftButton:
            return
        if self.crop_drag is not None:
            self.crop_release(self.mapToScene(event.position().toPoint()))
            return
        if self.passthrough:
            self.passthrough = False
            super().mouseReleaseEvent(event)
            return
        if self.resizing:
            item, _, start = self.resizing
            self.resizing = None
            if item.geometry() != start:  # nur echte Änderung ist ein Undo-Schritt
                self.undo_stack.push(PropertyCommand(item.set_geometry, start, item.geometry(), "Größe ändern"))
            return
        if self.dragging:
            items, starts, only = self.dragging, self.drag_starts, self.click_only
            self.dragging = self.drag_starts = self.drag_origin = self.click_only = None
            if any(item.pos() != start for item, start in zip(items, starts)):  # nur echtes Verschieben
                self.undo_stack.push(MoveItemCommand(items, starts, [i.pos() for i in items]))
            elif only is not None and len(items) > 1:  # bloßer Klick in eine Mehrfachauswahl
                self.scene_.clearSelection()
                only.setSelected(True)
                self.update_bars()
            return
        if self.rubber is not None:
            self.rubber = None
            self.update_bars()
            return
        if self.current_item is None:
            return
        self.finish_shape(self.mapToScene(event.position().toPoint()))

    def start_drag(self, items, pos):
        """Elemente zum Verschieben anfassen (ein Undo-Schritt beim Loslassen)."""
        self.dragging = list(items)
        self.drag_origin = QPointF(pos)
        self.drag_starts = [QPointF(i.pos()) for i in items]

    def select_in_rubber(self):
        """Auswahl = was ganz im Rahmen liegt (plus Auswahl davor bei Shift)."""
        start, end, before = self.rubber
        rect = QRectF(start, end).normalized()
        for item in self.elements():
            item.setSelected(item in before or rect.contains(item.sceneBoundingRect()))
        self.update_bars()

    def finish_shape(self, pos):
        """Aufgezogene Form abschließen: als Undo-Schritt ablegen oder, wenn zu klein, verwerfen."""
        # Versehentlicher Klick ohne Ziehen: leere Form wieder wegwerfen
        too_small = (pos - self.start_pos).manhattanLength() < 3
        if self.current_item.tool == Tool.MARKER and too_small:
            self.current_item.set_end(self.start_pos)  # Klick: nur der Kreis, ohne Zeigelinie
        if self.current_item.tool not in (Tool.FREEHAND, Tool.MARKER) and too_small:
            self.scene_.removeItem(self.current_item)
        else:
            self.undo_stack.push(AddItemCommand(self.scene_, self.current_item))
        self.current_item = None
        self.start_pos = None

    # --- Text ---
    def start_text(self, pos):
        """Neues Textobjekt an pos anlegen und direkt zum Tippen fokussieren."""
        item = TextElement(pos, self.pen_color, self.text_size)
        # Klickpunkt ungefähr auf Höhe der Zeilenmitte
        item.setPos(pos - QPointF(0, item.boundingRect().height() / 2))
        self.scene_.addItem(item)
        self.edit_text(item, old=None)

    def edit_text(self, item, old):
        """Item zum Tippen öffnen. old = (Text, Farbe, Größe) vorher, None bei neuem Text."""
        self.scene_.clearSelection()  # beim Tippen keinen Auswahlrahmen zeigen
        item.start_editing()
        self.editing_text = item
        self.editing_old = old

    def finish_text(self):
        """Eingabe beenden und als Undo-Schritt ablegen; leerer Text verschwindet."""
        item, old = self.editing_text, self.editing_old
        self.editing_text = self.editing_old = None
        item.stop_editing()
        new = (item.toPlainText(), item.color, item.font_size)
        empty = not new[0].strip()

        if old is None:  # neuer Text
            if empty:
                self.scene_.removeItem(item)
            else:
                self.undo_stack.push(AddItemCommand(self.scene_, item, "Text hinzufügen"))
        elif empty:
            # Makro: mehrere Befehle, die mit einem Undo gemeinsam zurückgenommen werden
            self.undo_stack.beginMacro("Text löschen")
            self.undo_stack.push(EditTextCommand(item, old, new))
            self.undo_stack.push(RemoveItemCommand(self.scene_, item))
            self.undo_stack.endMacro()
        elif new != old:
            self.undo_stack.push(EditTextCommand(item, old, new))

    def text_at(self, pos):
        """Oberstes Textobjekt an der Szenenposition pos oder None."""
        for item in self.scene_.items(pos):  # sortiert von oben nach unten
            if isinstance(item, TextElement):
                return item
        return None

    # --- Griffe und Auswahlrahmen ---
    def handle_at(self, pos):
        """Nummer des Griffs der Auswahl an Szenenposition pos oder None."""
        item = self.selected_element()
        if item is None or self.tool != Tool.SELECT or self.editing_text:
            return None
        grab = HANDLE_GRAB / self.zoom()  # Fangradius in Szenen-Einheiten
        for i, local in enumerate(item.handle_points()):
            point = item.mapToScene(local)
            if abs(point.x() - pos.x()) <= grab and abs(point.y() - pos.y()) <= grab:
                return i
        return None

    def update_cursor(self, pos):
        """Mauszeiger im Auswahl-Werkzeug: Pfeil, über Griffen ein Größen-Pfeil."""
        if self.tool != Tool.SELECT:
            return
        handle = self.handle_at(pos)
        item = self.selected_element()
        if handle is None:
            cursor = Qt.ArrowCursor
        elif isinstance(item, ShapeElement) and item.tool in (Tool.LINE, Tool.ARROW):
            cursor = Qt.SizeAllCursor
        else:  # Ecken 0/2 diagonal ↖↘, 1/3 diagonal ↗↙
            cursor = Qt.SizeFDiagCursor if handle in (0, 2) else Qt.SizeBDiagCursor
        self.viewport().setCursor(cursor)

    def drawForeground(self, painter, rect):
        """Rahmen und Griffe der Auswahl über allem zeichnen.

        Qt-Konzept: drawForeground gehört zur Ansicht, nicht zur Szene. Was hier
        gezeichnet wird, landet darum nie im exportierten Bild (scene.render).
        """
        self.paint_selection(painter)
        self.paint_crop(painter)     # Ausschnitt: außerhalb abdunkeln (canvas_crop.py)
        self.paint_pointer(painter)  # Spotlight/Lupe über allem (canvas_pointer.py)

    def paint_selection(self, painter):
        """Rahmen und Griffe der Auswahl (nur im Auswahl-Werkzeug). Ein Element: Rahmen mit
        Griffen; mehrere: je ein gestrichelter Rahmen ohne Griffe; dazu der Auswahlrahmen."""
        if self.tool != Tool.SELECT or self.editing_text:
            return
        line, fill = self.selection_colors()
        if self.rubber is not None:  # Auswahlrahmen beim Aufziehen
            start, end, _ = self.rubber
            band = QPen(line, 1, Qt.DashLine)
            band.setCosmetic(True)
            painter.setPen(band)
            tint = QColor(line)
            tint.setAlpha(30)
            painter.setBrush(tint)
            painter.drawRect(QRectF(start, end).normalized())
        items = self.selected_elements()
        if len(items) > 1:
            frame = QPen(line, 1, Qt.DashLine)
            frame.setCosmetic(True)
            painter.setPen(frame)
            painter.setBrush(Qt.NoBrush)
            pad = 4 / self.zoom()
            for item in items:
                painter.drawRect(item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad))
            return
        item = self.selected_element()
        if item is None:
            return
        points = [item.mapToScene(p) for p in item.handle_points()]
        painter.setRenderHint(QPainter.Antialiasing)
        if len(points) == 4:  # Rahmen durch die Ecken (bei Linien nur die Endpunkte)
            frame = QPen(line, 1, Qt.DashLine)
            frame.setCosmetic(True)  # immer 1 Pixel, unabhängig von Zoom/Transformation
            painter.setPen(frame)
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF(points))
        outline = QPen(line, 1.5)
        outline.setCosmetic(True)
        painter.setPen(outline)
        painter.setBrush(QBrush(fill))
        size = HANDLE_SIZE / self.zoom()  # auf dem Bildschirm immer gleich groß
        for p in points:
            painter.drawRect(QRectF(p.x() - size / 2, p.y() - size / 2, size, size))

    def selection_colors(self):
        """(Linie, Füllung) für Auswahlrahmen und Griffe: die Leistenfarbe mit mehr
        Kontrast zum Whiteboard-Hintergrund als Linie, damit sie auf hell und dunkel sichtbar ist."""
        line, fill = QColor(self.settings.theme.foreground), QColor(self.settings.theme.background)
        if self.board and contrast(fill.name(), self.board_color.name()) > \
                contrast(line.name(), self.board_color.name()):
            line, fill = fill, line
        fill.setAlpha(255)
        line.setAlpha(255)
        return line, fill

    # --- Mausrad und Tasten für die Auswahl ---
    def wheelEvent(self, event):
        """Alt+Mausrad: Größe fein einstellen. Whiteboard: Mausrad verschiebt, Strg+Mausrad zoomt."""
        mods = event.modifiers()
        if self.board and not mods & Qt.AltModifier:
            event.accept()
            if mods & Qt.ControlModifier:
                self.zoom_by_wheel(event.angleDelta().y() or event.angleDelta().x(), event.position())
            else:
                self.pan_by_wheel(event, swap=bool(mods & Qt.ShiftModifier))
            return
        if not mods & Qt.AltModifier:
            super().wheelEvent(event)
            return
        event.accept()
        # Mit Alt meldet Qt das Mausrad unter Linux als waagerecht, darum beide Achsen
        delta = event.angleDelta()
        self.wheel_rest += delta.y() or delta.x()
        steps = int(self.wheel_rest / 120)  # 120 = eine Raste
        if steps == 0:
            return
        self.wheel_rest -= steps * 120
        self.adjust_size(steps)

    def adjust_size(self, steps):
        """Größe um steps Rasten ändern, unabhängig von den Stufen."""
        if self.editing_text:  # Undo-Schritt entsteht beim Beenden der Eingabe
            item = self.editing_text
            item.set_font_size(clamp(item.font_size + steps * WHEEL_TEXT_STEP, TEXT_SIZE_RANGE))
            return
        items = self.selected_elements()
        if not items:
            self.toast.show_message("Alt+Mausrad: erst etwas auswählen (W)")
            return
        changes = []  # jedes Element um dieselben Rasten, ein Undo-Schritt
        for item in items:
            if isinstance(item, TextElement):
                old = item.font_size
                changes.append((item.set_font_size, old, clamp(old + steps * WHEEL_TEXT_STEP, TEXT_SIZE_RANGE)))
            else:
                old = item.width
                changes.append((item.set_width, old, clamp(old + steps * WHEEL_STROKE_STEP, STROKE_WIDTH_RANGE)))
        if any(old != new for _, old, new in changes):
            self.undo_stack.push(property_command(changes, "Größe ändern", mergeable=True))
            self.update_bars()  # beim Zusammenfassen meldet der Stack keine Änderung

    def move_selected(self, dx, dy, fine):
        """Auswahl um einen Schritt (Bildschirm-Pixel, zoomunabhängig) verschieben."""
        items = self.selected_elements()
        if not items:
            return
        step = self.settings.move_steps[fine] / self.zoom()
        olds = [QPointF(i.pos()) for i in items]
        news = [p + QPointF(dx * step, dy * step) for p in olds]
        self.undo_stack.push(MoveItemCommand(items, olds, news, "Verschieben", mergeable=True))
        self.update_bars()  # Griffe mitbewegen; beim Zusammenfassen meldet der Stack nichts

    def delete_selected(self):
        items = self.selected_elements()
        if not items:
            return
        self.undo_stack.beginMacro("Löschen")  # mehrere Befehle = ein Undo-Schritt
        for item in items:
            item.setSelected(False)  # sonst wäre es nach einem Undo noch markiert
            self.undo_stack.push(RemoveItemCommand(self.scene_, item, "Löschen"))
        self.undo_stack.endMacro()
