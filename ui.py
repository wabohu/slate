"""UI-Elemente, die über der Zeichenfläche liegen.

Aufbau (Variante A aus docs/plan-bedienung.md): eine MainBar mit gemeinsamem
Hintergrund, darin nebeneinander die Gruppen (Werkzeuge | Farben | Größe),
jede Gruppe eine CellBar.
"""
from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from tools import tool_icon


class Theme:
    """Farben der Oberfläche: Hintergrund der Leiste und Vordergrund (Symbole, Rahmen, Text).

    Standard ist ein neutrales Dunkelgrau mit Weiß; annotate.py setzt normalerweise
    die Farben aus dem Alacritty-Schema ([ui] in der Config).
    """

    def __init__(self, background=QColor(20, 20, 20), foreground=QColor("white"), opacity=0.75,
                 accent=None, heading=None):
        self.background = QColor(background)
        self.background.setAlphaF(opacity)
        self.foreground = QColor(foreground)
        self.accent = QColor(accent) if accent is not None else QColor(foreground)  # z. B. Tasten in der Übersicht
        self.heading = QColor(heading) if heading is not None else QColor(foreground)  # Überschriften

    def fg(self, alpha=255):
        """Vordergrundfarbe mit Deckkraft alpha (0-255), z. B. für dezente Flächen."""
        color = QColor(self.foreground)
        color.setAlpha(alpha)
        return color

    def css(self, color):
        """QColor -> 'rgba(r, g, b, a)' für Qt-Stylesheets."""
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def ui_scale(screen):
    """Maßstab für Leiste, Meldungen und Übersicht: alle Maße gelten für 1080 px
    Bildschirmhöhe, größere Bildschirme (z. B. 4K) bekommen alles entsprechend größer."""
    return max(1.0, screen.geometry().height() / 1080) if screen else 1.0


class MainBar(QWidget):
    """Gemeinsame Leiste: Hintergrund mit feinem Rand, Gruppen mit Trennstrichen.

    Qt-Konzept Layout: QHBoxLayout ordnet die Kind-Widgets automatisch
    nebeneinander an und berechnet daraus die Größe der Leiste. Wir müssen also
    keine Positionen von Hand ausrechnen, wenn eine Gruppe dazukommt.
    """

    SIZE = 0.9    # Gesamtgröße der Leiste (1.0 = Maße wie angegeben, für 1080 px Bildschirmhöhe)
    SPACING = 18  # Abstand zwischen den Gruppen, in der Mitte liegt der Trennstrich
    RADIUS = 12

    def __init__(self, groups, theme, parent=None):
        super().__init__(parent)
        self.groups = groups
        self.theme = theme
        self.scale = 1.0
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        for group in groups:
            self.box.addWidget(group, 0, Qt.AlignVCenter)  # addWidget macht group zum Kind dieser Leiste
        self.set_scale(1.0)

    def set_scale(self, scale):
        """Alle Maße mit scale vervielfachen (siehe ui_scale), dazu SIZE."""
        scale *= self.SIZE
        self.scale = scale
        self.box.setSpacing(round(self.SPACING * scale))
        for group in self.groups:
            group.set_scale(scale)
        self.box.activate()  # Layout sofort neu berechnen, nicht erst beim nächsten Zeichnen
        self.resize(self.sizeHint())

    def paintEvent(self, event):
        s = self.scale
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.theme.fg(45), max(1.0, s)))
        p.setBrush(self.theme.background)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS * s, self.RADIUS * s)
        p.setPen(QPen(self.theme.fg(40), max(1.0, s)))
        inset = self.height() * 0.28
        for left, right in zip(self.groups, self.groups[1:]):
            x = (left.geometry().right() + right.geometry().left()) / 2 + 0.5
            p.drawLine(QPointF(x, inset), QPointF(x, self.height() - inset))

    def mousePressEvent(self, event):
        # Klicks auf Hintergrund/Trennstriche nicht an die Zeichenfläche durchreichen
        event.accept()


class CellBar(QWidget):
    """Gemeinsame Basis für Leisten aus gleich großen Feldern.

    Klick auf ein Feld sendet selected(index). Das aktive Feld ist hell markiert (Farbfelder:
    Ring, Werkzeug und Größe: invertiert wie eine gedrückte Taste), das Feld unter der Maus
    bekommt eine feine Umrandung. Unterklassen zeichnen nur den
    Inhalt eines Felds (paint_cell). Alle Maße gelten bei scale 1 (1080 px Bildschirmhöhe).

    Weil die Leiste ein eigenes Kind-Widget ist, landen Klicks darauf hier und
    nicht im mousePressEvent der Zeichenfläche. Es entsteht also kein Strich.
    """

    selected = Signal(int)

    CELL = 28      # Kantenlänge eines Felds
    GAP = 6        # Abstand zwischen den Feldern
    PADDING = 10   # Rand um alle Felder
    RADIUS = 6     # Ecken eines Felds

    def __init__(self, count, theme, parent=None):
        super().__init__(parent)
        self.count = count
        self.theme = theme
        self.active = 0
        self.hover = -1
        self.scale = 1.0
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)  # Mausbewegung auch ohne Taste (für das Aufhellen)
        self.set_scale(1.0)

    def set_scale(self, scale):
        self.scale = scale
        self.setFixedSize(self.sizeHint())  # feste Größe, damit das Layout sie nicht streckt
        self.update()

    def px(self, value):
        return value * self.scale

    def sizeHint(self):
        n = self.count
        width = 2 * self.PADDING + n * self.CELL + max(0, n - 1) * self.GAP
        return QSize(round(self.px(width)), round(self.px(2 * self.PADDING + self.CELL)))

    def set_active(self, index):
        """index = -1: kein Feld markieren."""
        self.active = index
        self.update()  # plant ein Neuzeichnen, ruft später paintEvent auf

    def cell_rect(self, index):
        x = self.PADDING + index * (self.CELL + self.GAP)
        return QRectF(self.px(x), self.px(self.PADDING), self.px(self.CELL), self.px(self.CELL))

    def cell_at(self, pos):
        for i in range(self.count):
            if self.cell_rect(i).adjusted(-self.px(self.GAP / 2), -self.px(self.PADDING),
                                          self.px(self.GAP / 2), self.px(self.PADDING)).contains(pos):
                return i
        return -1

    def paint_cell(self, p, index, rect):
        raise NotImplementedError

    def paint_active(self, p, rect):
        """Markierung des aktiven Felds; Standard: heller Ring mit kleinem Abstand."""
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self.theme.foreground, self.px(2)))
        grow = self.px(3)
        p.drawRoundedRect(rect.adjusted(-grow, -grow, grow, grow), self.px(self.RADIUS + 2), self.px(self.RADIUS + 2))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Kein eigener Hintergrund: den zeichnet die MainBar für alle Gruppen
        for i in range(self.count):
            rect = self.cell_rect(i)
            p.save()  # Pinsel/Stift merken, damit paint_cell frei ändern darf
            self.paint_cell(p, i, rect)
            p.restore()
            if i == self.hover and i != self.active:  # feine Umrandung, auch auf bunten Feldern sichtbar
                p.setPen(QPen(self.theme.fg(170), self.px(1.5)))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(rect.adjusted(-self.px(1.5), -self.px(1.5), self.px(1.5), self.px(1.5)),
                                  self.px(self.RADIUS + 1), self.px(self.RADIUS + 1))
            if i == self.active:
                p.save()
                self.paint_active(p, rect)
                p.restore()

    def mouseMoveEvent(self, event):
        index = self.cell_at(event.position())
        if index != self.hover:
            self.hover = index
            self.update()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()

    def mousePressEvent(self, event):
        # Event immer hier "verbrauchen", auch in den Lücken zwischen Feldern
        event.accept()
        if event.button() != Qt.LeftButton:
            return
        index = self.cell_at(event.position())
        if index >= 0:
            self.selected.emit(index)


class PaletteBar(CellBar):
    """Farbleiste: ein Farbfeld pro Farbe."""

    CELL = 26
    GAP = 7

    def __init__(self, colors, theme, parent=None):
        self.colors = [QColor(c) for c in colors]
        super().__init__(len(self.colors), theme, parent)

    def set_colors(self, colors):
        """Gezeigte Farben austauschen (gleiche Anzahl), z. B. helle Varianten."""
        self.colors = [QColor(c) for c in colors]
        self.update()

    def paint_cell(self, p, index, rect):
        p.setBrush(self.colors[index])
        p.setPen(QPen(self.theme.fg(55), max(1.0, self.px(1))))  # dünner Rand, damit dunkle Farben sichtbar bleiben
        p.drawRoundedRect(rect, self.px(self.RADIUS), self.px(self.RADIUS))


class ToolBar(CellBar):
    """Werkzeugleiste: ein Symbol pro Werkzeug, Tastenkürzel klein unten rechts.

    icons: QPainterPaths in Feld-Koordinaten (0 … 30), labels: Tastennamen oder "".
    Das aktive Werkzeug ist invertiert: helle Fläche, Symbol in der Hintergrundfarbe.
    """

    CELL = 32

    def __init__(self, icons, labels, theme, parent=None):
        self.icons = icons
        self.labels = [label.lower() for label in labels]  # klein wie in der Übersicht
        super().__init__(len(icons), theme, parent)

    def paint_cell(self, p, index, rect):
        active = index == self.active
        dark = QColor(self.theme.background)
        dark.setAlpha(255)
        p.setPen(Qt.NoPen)
        p.setBrush(self.theme.fg(235) if active else self.theme.fg(18))
        p.drawRoundedRect(rect, self.px(self.RADIUS), self.px(self.RADIUS))

        pen = QPen(dark if active else self.theme.foreground, 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.save()
        p.translate(rect.topLeft())  # Symbol ist relativ zur Feldecke gebaut (0 … 30)
        p.scale(rect.width() / 30, rect.height() / 30)
        p.drawPath(self.icons[index])
        p.restore()

        if self.labels[index]:
            font = QFont()
            font.setPixelSize(max(1, round(self.px(9))))
            font.setBold(True)
            p.setFont(font)
            p.setPen(dark if active else self.theme.fg(140))
            p.drawText(rect.adjusted(0, 0, -self.px(3), -self.px(1)), Qt.AlignRight | Qt.AlignBottom,
                       self.labels[index])

    def paint_active(self, p, rect):
        pass  # die invertierte Fläche zeichnet paint_cell


class SizeBar(CellBar):
    """Größen-Stufen: Punkte wachsender Größe (Strichstärke bzw. Schriftgröße)."""

    def __init__(self, levels, theme, parent=None):
        super().__init__(levels, theme, parent)

    def paint_cell(self, p, index, rect):
        active = index == self.active
        dark = QColor(self.theme.background)
        dark.setAlpha(255)
        p.setPen(Qt.NoPen)
        p.setBrush(self.theme.fg(235) if active else self.theme.fg(18))
        p.drawRoundedRect(rect, self.px(self.RADIUS), self.px(self.RADIUS))
        diameter = self.px(4 + index * 4)  # 4, 8, 12, 16: zeigt die Stufe, nicht den Pixelwert
        p.setBrush(dark if active else self.theme.foreground)
        p.drawEllipse(rect.center(), diameter / 2, diameter / 2)

    def paint_active(self, p, rect):
        pass  # invertiert, siehe paint_cell


class Toast(QLabel):
    """Kurze Einblendung oben mittig (z. B. "Gespeichert: …"), verschwindet von selbst."""

    DURATION_MS = 2500

    def __init__(self, theme, parent):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # Klicks gehen durch
        self.set_scale(1.0)
        # Ein Timer statt vieler singleShot-Aufrufe: neue Meldung startet die Zeit neu
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def set_scale(self, scale):
        theme = self.theme
        self.top = round(20 * scale)
        self.setStyleSheet(
            f"background: {theme.css(theme.background)}; color: {theme.css(theme.foreground)};"
            f"border: {max(1, round(scale))}px solid {theme.css(theme.fg(45))};"
            f"padding: {round(8 * scale)}px {round(16 * scale)}px; border-radius: {round(10 * scale)}px;"
            f"font-size: {round(14 * scale)}px;"
        )

    def show_message(self, text):
        self.setText(text)
        self.adjustSize()
        self.move((self.parent().width() - self.width()) // 2, self.top)
        self.show()
        self.raise_()  # über alle anderen Kind-Widgets
        self.timer.start(self.DURATION_MS)


class HelpPanel(QWidget):
    """Tastenübersicht (?), Entwurf D: oben links die Werkzeug-Symbole wie in der
    Leiste, darunter Farbfelder und Größenpunkte, je mit Taste; darunter die Maus; rechts
    die übrigen Gruppen als Liste. Inhalt aus shortcuts.overview().

    Alle Maße sind für 1080 Pixel Bildschirmhöhe angegeben und werden mit der Höhe des
    Bildschirms skaliert (4K = doppelt so groß); passt das Panel nicht ins Fenster, wird
    es kleiner. Messen und Zeichnen machen dieselbe Methode (arrange), so passt beides.
    Schließen regelt die Canvas (jede Taste, Klick daneben); ein Klick aufs Panel schließt es.
    """

    SIZE = 0.9  # Gesamtgröße (1.0 = Maße wie unten, für 1080 px Bildschirmhöhe)
    MARGIN, COLUMN_GAP, SECTION_GAP = 40, 70, 44
    LIST_GAP = 22  # Abstand zwischen den Gruppen rechts
    TOOL_CELL, SWATCH, KEY_GAP = 46, 46, 24  # Werkzeug-Symbole so groß wie die Farbfelder

    def __init__(self, theme, parent):
        super().__init__(parent)
        self.theme = theme
        self.data = None
        self.colors = []
        self.scale = 1.0
        self.hide()

    def set_content(self, data, colors):
        """data aus shortcuts.overview(); colors: Farbfelder, wie die Farbleiste sie zeigt."""
        self.data, self.colors = data, [QColor(c) for c in colors]
        self.scale = self.SIZE * ui_scale(self.window().screen())
        size = self.arrange(None)
        parent = self.parent()
        fit = min(1.0, parent.width() * 0.96 / size.width(), parent.height() * 0.96 / size.height())
        self.scale *= fit
        self.resize(self.arrange(None).toSize())

    # --- Schriften und Farben ---
    def make_font(self, px, bold=False, mono=False, spacing=0.0):
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont) if mono else QFont()
        f.setPixelSize(max(1, round(px * self.scale)))
        f.setBold(bold)
        if spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing * self.scale)
        return f

    def arrange(self, p):
        """Inhalt anordnen; mit Painter p auch zeichnen. Rückgabe: benötigte Größe."""
        s, d, th = self.scale, self.data, self.theme
        fg, accent, dim = th.foreground, th.accent, th.fg(150)
        title_f, hint_f, head_f = self.make_font(22, bold=True), self.make_font(15), self.make_font(13, bold=True, spacing=1.5)
        key_f, text_f, small_f = self.make_font(16, bold=True, mono=True), self.make_font(16), self.make_font(12)
        m = self.MARGIN * s

        def text(x, y, string, font, color, align=None, width=0.0):
            """Text mit Grundlinie y; Rückgabe: Breite."""
            fm = QFontMetricsF(font)
            w = fm.horizontalAdvance(string)
            if p:
                p.setFont(font)
                p.setPen(color)
                if align == "center":
                    x += (width - w) / 2
                p.drawText(QPointF(x, y), string)
            return w

        def heading(x, y, name, hint=""):
            w = text(x, y, name.upper(), head_f, th.heading)
            if hint:
                w += 12 * s + text(x + w + 12 * s, y, hint, head_f, dim)
            return w

        # Titel
        y = m + 26 * s
        w_title = text(m, y, "Tastenkürzel", title_f, fg)
        w_title += 16 * s + text(m + w_title + 16 * s, y, "beliebige Taste schließt", hint_f, dim)
        top = y + 40 * s
        line_h = QFontMetricsF(text_f).height() * 1.45

        # --- linke Spalte: Bildzeilen ---
        x, y = m, top
        heading(x, y, "Werkzeuge")
        cell = self.TOOL_CELL * s
        # Jedes Werkzeug so breit wie Symbol oder Name, damit die Namen nicht aneinanderstoßen
        names = [tool.value.split(" ")[0] for tool, _ in d["tools"]]
        slots = [max(cell, QFontMetricsF(small_f).horizontalAdvance(n)) + 12 * s for n in names]
        for i, (tool, keys) in enumerate(d["tools"]):
            slot_x = x + sum(slots[:i])
            r = QRectF(slot_x + (slots[i] - 12 * s - cell) / 2, y + 14 * s, cell, cell)
            if p:
                p.setPen(Qt.NoPen)
                p.setBrush(th.fg(22))
                p.drawRoundedRect(r, 7 * s, 7 * s)
                p.save()
                icon = cell * 0.8  # Symbole sind für ein 30er-Feld gebaut
                p.translate(r.left() + (cell - icon) / 2, r.top() + (cell - icon) / 2)
                p.scale(icon / 30, icon / 30)
                pen = QPen(fg, 2)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawPath(tool_icon(tool))
                p.restore()
            text(r.left(), r.bottom() + 24 * s, keys, key_f, accent, "center", cell)
            text(slot_x, r.bottom() + 43 * s, names[i], small_f, dim, "center", slots[i] - 12 * s)
        left_w = sum(slots)
        y += 14 * s + cell + 43 * s + self.SECTION_GAP * s

        heading(x, y, "Farben", d["color_hint"])
        sw = self.SWATCH * s
        for i, color in enumerate(self.colors):
            r = QRectF(x + i * (sw + 10 * s), y + 14 * s, sw, sw)
            if p:
                p.setPen(QPen(th.fg(70), max(1.0, s)))
                p.setBrush(color)
                p.drawRoundedRect(r, 7 * s, 7 * s)
            if i < len(d["colors"]):
                text(r.left(), r.bottom() + 24 * s, d["colors"][i], key_f, accent, "center", sw)
        left_w = max(left_w, len(self.colors) * (sw + 10 * s),
                     QFontMetricsF(head_f).horizontalAdvance("FARBEN " + d["color_hint"]) + 12 * s)
        y += 14 * s + sw + 24 * s + self.SECTION_GAP * s

        heading(x, y, "Größe", d["size_hint"])
        step = 64 * s
        for i, keys in enumerate(d["sizes"]):
            cx = x + 20 * s + i * step
            if p:
                p.setPen(Qt.NoPen)
                p.setBrush(fg)
                radius = 3 * s * (i + 1)
                p.drawEllipse(QPointF(cx, y + 34 * s), radius, radius)
            text(cx - step / 2, y + 74 * s, keys, key_f, accent, "center", step)
        y += 74 * s + self.SECTION_GAP * s

        def entry_list(x, y, entries, key_w):
            for keys, desc in entries:
                text(x, y, keys, key_f, accent)
                text(x + key_w, y, desc, text_f, fg)
                y += line_h
            return y

        def key_width(entries):
            return max((QFontMetricsF(key_f).horizontalAdvance(k) for k, _ in entries), default=0) + self.KEY_GAP * s

        def list_width(entries):
            return key_width(entries) + max((QFontMetricsF(text_f).horizontalAdvance(t) for _, t in entries), default=0)

        if d["mouse"]:
            heading(x, y, "Maus")
            y = entry_list(x, y + 32 * s, d["mouse"], key_width(d["mouse"]))
            left_w = max(left_w, list_width(d["mouse"]))
        left_bottom = y

        # --- rechte Spalte: Listen ---
        rx = m + left_w + self.COLUMN_GAP * s
        all_entries = [e for _, entries in d["lists"] for e in entries]
        key_w = key_width(all_entries)
        y = top
        for name, entries in d["lists"]:
            heading(rx, y, name)
            y = entry_list(rx, y + 30 * s, entries, key_w) + self.LIST_GAP * s
        right_w = key_w + max((QFontMetricsF(text_f).horizontalAdvance(t) for _, t in all_entries), default=0)

        width = max(rx + right_w, m + w_title) + m
        height = max(left_bottom, y) + m - line_h / 2
        return QSizeF(width, height)

    def paintEvent(self, event):
        if not self.data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        background = QColor(self.theme.background)
        background.setAlpha(255)  # deckend: gut lesbar über jedem Bild
        p.setPen(QPen(self.theme.fg(60), max(1.0, self.scale)))
        p.setBrush(background)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14 * self.scale, 14 * self.scale)
        self.arrange(p)

    def show_centered(self):
        self.center()
        self.show()
        self.raise_()

    def center(self):
        parent = self.parent()
        self.move((parent.width() - self.width()) // 2, max(10, (parent.height() - self.height()) // 2))

    def mousePressEvent(self, event):
        event.accept()
        self.hide()
