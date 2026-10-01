"""UI-Elemente, die über der Zeichenfläche liegen.

Aufbau (Variante A aus docs/plan-bedienung.md): eine MainBar mit gemeinsamem
Hintergrund, darin nebeneinander die Gruppen (Werkzeuge | Farben | Größe),
jede Gruppe eine CellBar.
"""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget



class Theme:
    """Farben der Oberfläche: Hintergrund der Leiste und Vordergrund (Symbole, Rahmen, Text).

    Standard ist ein neutrales Dunkelgrau mit Weiß; annotate.py setzt normalerweise
    die Farben aus dem Alacritty-Schema ([ui] in der Config).
    """

    def __init__(self, background=QColor(20, 20, 20), foreground=QColor("white"), opacity=0.75):
        self.background = QColor(background)
        self.background.setAlphaF(opacity)
        self.foreground = QColor(foreground)

    def fg(self, alpha=255):
        """Vordergrundfarbe mit Deckkraft alpha (0-255), z. B. für dezente Flächen."""
        color = QColor(self.foreground)
        color.setAlpha(alpha)
        return color

    def css(self, color):
        """QColor -> 'rgba(r, g, b, a)' für Qt-Stylesheets."""
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


class MainBar(QWidget):
    """Gemeinsame Leiste: halbtransparenter Hintergrund, Gruppen mit Trennstrichen.

    Qt-Konzept Layout: QHBoxLayout ordnet die Kind-Widgets automatisch
    nebeneinander an und berechnet daraus die Größe der Leiste. Wir müssen also
    keine Positionen von Hand ausrechnen, wenn eine Gruppe dazukommt.
    """

    SPACING = 14  # Abstand zwischen den Gruppen, in der Mitte liegt der Trennstrich

    def __init__(self, groups, theme, parent=None):
        super().__init__(parent)
        self.groups = groups
        self.theme = theme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.SPACING)
        for group in groups:
            layout.addWidget(group, 0, Qt.AlignVCenter)  # addWidget macht group zum Kind dieser Leiste
        self.resize(self.sizeHint())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.theme.background)
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        p.setPen(QPen(self.theme.fg(50), 1))
        for left, right in zip(self.groups, self.groups[1:]):
            x = (left.geometry().right() + right.geometry().left()) / 2 + 0.5
            p.drawLine(QPointF(x, 10), QPointF(x, self.height() - 10))

    def mousePressEvent(self, event):
        # Klicks auf Hintergrund/Trennstriche nicht an die Zeichenfläche durchreichen
        event.accept()


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

    def __init__(self, count, theme, parent=None):
        super().__init__(parent)
        self.count = count
        self.theme = theme
        self.active = 0
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.sizeHint())  # feste Größe, damit das Layout sie nicht streckt

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
        # Kein eigener Hintergrund: den zeichnet die MainBar für alle Gruppen
        for i in range(self.count):
            rect = self.cell_rect(i)
            p.save()  # Pinsel/Stift merken, damit paint_cell frei ändern darf
            self.paint_cell(p, i, rect)
            p.restore()
            if i == self.active:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(self.theme.foreground, 2))
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

    def __init__(self, colors, theme, parent=None):
        self.colors = [QColor(c) for c in colors]
        super().__init__(len(self.colors), theme, parent)

    def set_colors(self, colors):
        """Gezeigte Farben austauschen (gleiche Anzahl), z. B. helle Varianten."""
        self.colors = [QColor(c) for c in colors]
        self.update()

    def paint_cell(self, p, index, rect):
        p.setBrush(self.colors[index])
        p.setPen(QPen(self.theme.fg(60), 1))  # dünner Rand, damit dunkle Farben sichtbar bleiben
        p.drawRoundedRect(rect, 4, 4)


class ToolBar(CellBar):
    """Werkzeugleiste: ein Symbol pro Werkzeug, Tastenkürzel klein unten rechts.

    icons: QPainterPaths in Feld-Koordinaten (0 … CELL), labels: Tastennamen oder "".
    """

    CELL = 30

    def __init__(self, icons, labels, theme, parent=None):
        self.icons = icons
        self.labels = labels
        super().__init__(len(icons), theme, parent)

    def paint_cell(self, p, index, rect):
        p.setPen(Qt.NoPen)
        p.setBrush(self.theme.fg(25))
        p.drawRoundedRect(rect, 4, 4)

        pen = QPen(self.theme.foreground, 2)
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
            p.setPen(self.theme.fg(150))
            p.drawText(QRectF(0, 0, self.CELL - 2, self.CELL - 1),
                       Qt.AlignRight | Qt.AlignBottom, self.labels[index])


class SizeBar(CellBar):
    """Größen-Stufen: Punkte wachsender Größe (Strichstärke bzw. Schriftgröße)."""

    def __init__(self, levels, theme, parent=None):
        super().__init__(levels, theme, parent)

    def paint_cell(self, p, index, rect):
        p.setPen(Qt.NoPen)
        p.setBrush(self.theme.fg(25))
        p.drawRoundedRect(rect, 4, 4)
        diameter = 4 + index * 4  # 4, 8, 12, 16 px: zeigt die Stufe, nicht den Pixelwert
        p.setBrush(self.theme.foreground)
        p.drawEllipse(rect.center(), diameter / 2, diameter / 2)


class Toast(QLabel):
    """Kurze Einblendung oben mittig (z. B. "Gespeichert: …"), verschwindet von selbst."""

    DURATION_MS = 2500

    def __init__(self, theme, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # Klicks gehen durch
        self.setStyleSheet(
            f"background: {theme.css(theme.background)}; color: {theme.css(theme.foreground)};"
            "padding: 8px 16px; border-radius: 8px; font-size: 14px;"
        )
        # Ein Timer statt vieler singleShot-Aufrufe: neue Meldung startet die Zeit neu
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text):
        self.setText(text)
        self.adjustSize()
        self.move((self.parent().width() - self.width()) // 2, 20)
        self.show()
        self.raise_()  # über alle anderen Kind-Widgets
        self.timer.start(self.DURATION_MS)
