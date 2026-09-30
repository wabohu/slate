"""UI-Elemente, die über der Zeichenfläche liegen."""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class CellBar(QWidget):
    """Gemeinsame Basis für Leisten aus gleich großen Feldern.

    Klick auf ein Feld sendet selected(index), das aktive Feld bekommt einen
    weißen Rahmen. Unterklassen zeichnen nur den Inhalt eines Felds (paint_cell).

    Weil die Leiste ein eigenes Kind-Widget ist, landen Klicks darauf hier und
    nicht im mousePressEvent der Zeichenfläche. Es entsteht also kein Strich.
    """

    selected = Signal(int)

    CELL = 26      # Kantenlänge eines Felds
    GAP = 6        # Abstand zwischen den Feldern
    PADDING = 8    # Rand um alle Felder

    def __init__(self, count, parent=None):
        super().__init__(parent)
        self.count = count
        self.active = 0
        self.setCursor(Qt.PointingHandCursor)
        self.resize(self.sizeHint())

    def sizeHint(self):
        n = self.count
        width = 2 * self.PADDING + n * self.CELL + max(0, n - 1) * self.GAP
        return QSize(width, 2 * self.PADDING + self.CELL)

    def set_active(self, index):
        """index = -1: kein Feld markieren."""
        self.active = index
        self.update()  # plant ein Neuzeichnen, ruft später paintEvent auf

    def cell_rect(self, index):
        x = self.PADDING + index * (self.CELL + self.GAP)
        return QRectF(x, self.PADDING, self.CELL, self.CELL)

    def paint_cell(self, p, index, rect):
        raise NotImplementedError

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Halbtransparenter Hintergrund wie beim Werkzeug-Label
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 20, 190))
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)

        for i in range(self.count):
            rect = self.cell_rect(i)
            p.save()  # Pinsel/Stift merken, damit paint_cell frei ändern darf
            self.paint_cell(p, i, rect)
            p.restore()
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
        for i in range(self.count):
            if self.cell_rect(i).adjusted(-self.GAP / 2, -self.PADDING, self.GAP / 2, self.PADDING).contains(pos):
                self.selected.emit(i)
                return


class PaletteBar(CellBar):
    """Farbleiste: ein Farbfeld pro Farbe."""

    def __init__(self, colors, parent=None):
        self.colors = [QColor(c) for c in colors]
        super().__init__(len(self.colors), parent)

    def paint_cell(self, p, index, rect):
        p.setBrush(self.colors[index])
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))  # dünner Rand, damit Schwarz sichtbar bleibt
        p.drawRoundedRect(rect, 4, 4)


class ToolBar(CellBar):
    """Werkzeugleiste: ein Symbol pro Werkzeug, Tastenkürzel klein unten rechts.

    icons: QPainterPaths in Feld-Koordinaten (0 … CELL), labels: Tastennamen oder "".
    """

    CELL = 30

    def __init__(self, icons, labels, parent=None):
        self.icons = icons
        self.labels = labels
        super().__init__(len(icons), parent)

    def paint_cell(self, p, index, rect):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 25))
        p.drawRoundedRect(rect, 4, 4)

        pen = QPen(Qt.white, 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.translate(rect.topLeft())  # Symbol ist relativ zur Feldecke gebaut
        p.drawPath(self.icons[index])

        if self.labels[index]:
            font = QFont()
            font.setPixelSize(9)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(QRectF(0, 0, self.CELL - 2, self.CELL - 1),
                       Qt.AlignRight | Qt.AlignBottom, self.labels[index])
