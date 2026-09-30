"""UI-Elemente, die über der Zeichenfläche liegen."""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class PaletteBar(QWidget):
    """Schmale Farbleiste. Klick auf ein Feld sendet colorSelected(index).

    Weil die Leiste ein eigenes Kind-Widget ist, landen Klicks darauf hier und
    nicht im mousePressEvent der Zeichenfläche. Es entsteht also kein Strich.
    """

    colorSelected = Signal(int)

    SWATCH = 26    # Kantenlänge eines Farbfelds
    GAP = 6        # Abstand zwischen den Feldern
    PADDING = 8    # Rand um alle Felder

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = [QColor(c) for c in colors]
        self.active = 0
        self.setCursor(Qt.PointingHandCursor)
        self.resize(self.sizeHint())

    def sizeHint(self):
        n = len(self.colors)
        width = 2 * self.PADDING + n * self.SWATCH + max(0, n - 1) * self.GAP
        return QSize(width, 2 * self.PADDING + self.SWATCH)

    def set_active(self, index):
        self.active = index
        self.update()  # plant ein Neuzeichnen, ruft später paintEvent auf

    def swatch_rect(self, index):
        x = self.PADDING + index * (self.SWATCH + self.GAP)
        return QRectF(x, self.PADDING, self.SWATCH, self.SWATCH)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Halbtransparenter Hintergrund wie beim Werkzeug-Label
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 20, 190))
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)

        for i, color in enumerate(self.colors):
            rect = self.swatch_rect(i)
            p.setBrush(color)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))  # dünner Rand, damit Schwarz sichtbar bleibt
            p.drawRoundedRect(rect, 4, 4)
            if i == self.active:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(Qt.white, 2))
                p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 6, 6)

    def mousePressEvent(self, event):
        # Event immer hier "verbrauchen", auch in den Lücken zwischen Feldern
        event.accept()
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        for i in range(len(self.colors)):
            if self.swatch_rect(i).adjusted(-self.GAP / 2, -self.PADDING, self.GAP / 2, self.PADDING).contains(pos):
                self.colorSelected.emit(i)
                return
