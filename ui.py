"""UI elements that lie above the drawing surface.

Structure (variant A from docs/plan-bedienung.md): a MainBar with a common
background, in it side by side the groups (tools | colors | size),
each group a CellBar.
"""
from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from shortcuts import KEYBOARD_COLUMNS
from tools import tool_icon


class Theme:
    """Interface colors: background of the bar and foreground (icons, frames, text).

    Default is a neutral dark gray with white; normally the settings set
    the colors from the Alacritty scheme ([ui] in the config).
    """

    def __init__(self, background=QColor(20, 20, 20), foreground=QColor("white"), opacity=0.75,
                 accent=None, heading=None):
        self.background = QColor(background)
        self.background.setAlphaF(opacity)
        self.foreground = QColor(foreground)
        self.accent = QColor(accent) if accent is not None else QColor(foreground)  # e.g. keys in the overview
        self.heading = QColor(heading) if heading is not None else QColor(foreground)  # headings

    def fg(self, alpha=255):
        """Foreground color with opacity alpha (0-255), e.g. for subtle areas."""
        color = QColor(self.foreground)
        color.setAlpha(alpha)
        return color

    def css(self, color):
        """QColor -> 'rgba(r, g, b, a)' for Qt style sheets."""
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def ui_scale(screen):
    """Scale for bar, messages and overview: all sizes are meant for 1080 px
    screen height, larger screens (e.g. 4K) get everything correspondingly larger."""
    return max(1.0, screen.geometry().height() / 1080) if screen else 1.0


class MainBar(QWidget):
    """Common bar: background with a fine border, groups with separator lines.

    Qt concept layout: QHBoxLayout arranges the child widgets side by side
    automatically and computes the size of the bar from them. So we do not
    have to compute positions by hand when a group is added.
    """

    SIZE = 0.9    # overall size of the bar (1.0 = sizes as given, for 1080 px screen height)
    SPACING = 18  # gap between the groups, the separator line lies in the middle
    RADIUS = 12

    def __init__(self, groups, theme, parent=None):
        super().__init__(parent)
        self.groups = groups
        self.theme = theme
        self.scale = 1.0
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        for group in groups:
            self.box.addWidget(group, 0, Qt.AlignVCenter)  # addWidget makes group a child of this bar
        self.set_scale(1.0)

    def set_scale(self, scale):
        """Multiply all sizes by scale (see ui_scale), plus SIZE."""
        scale *= self.SIZE
        self.scale = scale
        self.box.setSpacing(round(self.SPACING * scale))
        for group in self.groups:
            group.set_scale(scale)
        self.box.activate()  # recompute the layout right away, not only on the next paint
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
        # do not pass clicks on background/separators through to the drawing surface
        event.accept()


class CellBar(QWidget):
    """Common base for bars made of equally sized fields.

    A click on a field emits selected(index). The active field is highlighted (color fields:
    ring, tool and size: inverted like a pressed key), the field under the mouse
    gets a fine outline. Subclasses only draw the
    content of a field (paint_cell). All sizes apply at scale 1 (1080 px screen height).

    Because the bar is a child widget of its own, clicks on it land here and
    not in the mousePressEvent of the drawing surface. So no stroke is created.
    """

    selected = Signal(int)

    CELL = 28      # edge length of a field
    GAP = 6        # gap between the fields
    PADDING = 10   # margin around all fields
    RADIUS = 6     # corners of a field

    def __init__(self, count, theme, parent=None):
        super().__init__(parent)
        self.count = count
        self.theme = theme
        self.active = 0
        self.hover = -1
        self.scale = 1.0
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)  # mouse movement without a button too (for the highlight)
        self.set_scale(1.0)

    def set_scale(self, scale):
        self.scale = scale
        self.setFixedSize(self.sizeHint())  # fixed size so the layout does not stretch it
        self.update()

    def px(self, value):
        return value * self.scale

    def sizeHint(self):
        n = self.count
        width = 2 * self.PADDING + n * self.CELL + max(0, n - 1) * self.GAP
        return QSize(round(self.px(width)), round(self.px(2 * self.PADDING + self.CELL)))

    def set_active(self, index):
        """index = -1: highlight no field."""
        self.active = index
        self.update()  # schedules a repaint, calls paintEvent later

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
        """Highlight of the active field; default: light ring with a small gap."""
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self.theme.foreground, self.px(2)))
        grow = self.px(3)
        p.drawRoundedRect(rect.adjusted(-grow, -grow, grow, grow), self.px(self.RADIUS + 2), self.px(self.RADIUS + 2))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # No background of its own: the MainBar draws it for all groups
        for i in range(self.count):
            rect = self.cell_rect(i)
            p.save()  # remember brush/pen so paint_cell may change them freely
            self.paint_cell(p, i, rect)
            p.restore()
            if i == self.hover and i != self.active:  # fine outline, visible on colored fields too
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
        # always "consume" the event here, also in the gaps between fields
        event.accept()
        if event.button() != Qt.LeftButton:
            return
        index = self.cell_at(event.position())
        if index >= 0:
            self.selected.emit(index)


class PaletteBar(CellBar):
    """Color bar: one color field per color."""

    CELL = 26
    GAP = 7

    def __init__(self, colors, theme, parent=None):
        self.colors = [QColor(c) for c in colors]
        super().__init__(len(self.colors), theme, parent)

    def set_colors(self, colors):
        """Replace the shown colors (same count), e.g. light variants."""
        self.colors = [QColor(c) for c in colors]
        self.update()

    def paint_cell(self, p, index, rect):
        p.setBrush(self.colors[index])
        p.setPen(QPen(self.theme.fg(55), max(1.0, self.px(1))))  # thin border so dark colors stay visible
        p.drawRoundedRect(rect, self.px(self.RADIUS), self.px(self.RADIUS))


class ToolBar(CellBar):
    """Tool bar: one icon per tool, shortcut small at the bottom right.

    icons: QPainterPaths in field coordinates (0 … 30), labels: key names or "".
    The active tool is inverted: light area, icon in the background color.
    """

    CELL = 32

    def __init__(self, icons, labels, theme, parent=None):
        self.icons = icons
        self.labels = [label.lower() for label in labels]  # lower case as in the overview
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
        p.translate(rect.topLeft())  # the icon is built relative to the field corner (0 … 30)
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
        pass  # paint_cell draws the inverted area


class SizeBar(CellBar):
    """Size levels: dots of growing size (stroke width or font size)."""

    def __init__(self, levels, theme, parent=None):
        super().__init__(levels, theme, parent)

    def paint_cell(self, p, index, rect):
        active = index == self.active
        dark = QColor(self.theme.background)
        dark.setAlpha(255)
        p.setPen(Qt.NoPen)
        p.setBrush(self.theme.fg(235) if active else self.theme.fg(18))
        p.drawRoundedRect(rect, self.px(self.RADIUS), self.px(self.RADIUS))
        diameter = self.px(4 + index * 4)  # 4, 8, 12, 16: shows the level, not the pixel value
        p.setBrush(dark if active else self.theme.foreground)
        p.drawEllipse(rect.center(), diameter / 2, diameter / 2)

    def paint_active(self, p, rect):
        pass  # inverted, see paint_cell


class Toast(QLabel):
    """Short message at the top center (e.g. "Saved: …"), disappears by itself."""

    DURATION_MS = 2500

    def __init__(self, theme, parent):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # clicks go through
        self.set_scale(1.0)
        # One timer instead of many singleShot calls: a new message restarts the time
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
        self.raise_()  # above all other child widgets
        self.timer.start(self.DURATION_MS)


# Keyboard picture of the overview: column stagger of shortcuts.KEYBOARD_COLUMNS in key heights
# (how far each column sits lower than the highest one, the E column), like my keyboard in Vial
KEYBOARD_STAGGER = (0.78, 0.78, 0.26, 0.0, 0.26, 0.38)
# Letter rows, for the color fields (one row per keyboard row of their keys)
KEY_ROWS = ("1234567890", "qwertyuiop", "asdfghjkl;", "zxcvbnm,./")


def key_row(keys):
    """Keyboard row of the first key in keys (e.g. "w", "shift+a, x"); None outside the four
    letter/number rows (F1, Space ...)."""
    base = keys.split(",")[0].strip().lower().rsplit("+", 1)[-1]
    return next((row for row, letters in enumerate(KEY_ROWS) if len(base) == 1 and base in letters), None)


def keyboard_rows(key_list, wrap=10):
    """Indexes of key_list grouped by keyboard row of their key (rows in keyboard order, each
    in list order); entries without such a key at the end, wrap per row."""
    rows = {}
    rest = []
    for i, keys in enumerate(key_list):
        row = key_row(keys) if keys else None
        if row is None:
            rest.append(i)
        else:
            rows.setdefault(row, []).append(i)
    return [rows[r] for r in sorted(rows)] + [rest[i:i + wrap] for i in range(0, len(rest), wrap)]


class HelpPanel(QWidget):
    """Key overview (?), draft D: top left the left half of the keyboard (column stagger as
    on my keyboard) with tools and single keys, below it color fields (one row per keyboard
    row of their keys) and next to them size dots, each with its key; the pictures spread
    over the full height. The lists (mouse first, then the groups) flow in reading order over three
    columns: one below the pictures, two to their right from the top, split so the columns
    end about evenly. Content from shortcuts.overview().

    All sizes are given for 1080 pixel screen height and scale with the height of the
    screen (4K = twice as large); if the panel does not fit into the window, it gets
    smaller. Measuring and drawing use the same method (arrange), so both match.
    The Canvas handles closing (any key, click outside); a click on the panel closes it.
    """

    SIZE = 0.9  # overall size (1.0 = sizes as below, for 1080 px screen height)
    MARGIN, COLUMN_GAP, SECTION_GAP = 40, 70, 44
    LIST_GAP = 22  # gap between the groups on the right
    SWATCH, KEY_GAP = 46, 24
    KEY_CAP = (96, 78)  # width, height of a key in the keyboard picture

    def __init__(self, theme, parent):
        super().__init__(parent)
        self.theme = theme
        self.data = None
        self.colors = []
        self.scale = 1.0
        self.spread = 0.0  # extra gap between the picture rows on the left (set_content)
        self.slack = 0.0   # room left below the pictures, measured by arrange
        self.hide()

    def set_content(self, data, colors):
        """data from shortcuts.overview(); colors: color fields as the color bar shows them."""
        self.data, self.colors = data, [QColor(c) for c in colors]
        self.scale = self.SIZE * ui_scale(self.window().screen())
        self.spread = 0.0
        size = self.arrange(None)
        parent = self.parent()
        fit = min(1.0, parent.width() * 0.96 / size.width(), parent.height() * 0.96 / size.height())
        self.scale *= fit
        # Spread the pictures on the left over the height of the lists (the gap between
        # keyboard and colors)
        self.spread = 0.0
        self.arrange(None)
        self.spread = self.slack
        self.resize(self.arrange(None).toSize())

    # --- fonts and colors ---
    def make_font(self, px, bold=False, mono=False, spacing=0.0):
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont) if mono else QFont()
        f.setPixelSize(max(1, round(px * self.scale)))
        f.setBold(bold)
        if spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing * self.scale)
        return f

    def arrange(self, p):
        """Arrange the content; with painter p also draw it. Returns: required size."""
        s, d, th = self.scale, self.data, self.theme
        fg, accent, dim = th.foreground, th.accent, th.fg(150)
        title_f, hint_f, head_f = self.make_font(22, bold=True), self.make_font(15), self.make_font(13, bold=True, spacing=1.5)
        key_f, text_f, small_f = self.make_font(16, bold=True, mono=True), self.make_font(16), self.make_font(12)
        m = self.MARGIN * s

        def text(x, y, string, font, color, align=None, width=0.0):
            """Text with baseline y; returns: width."""
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

        # title
        y = m + 26 * s
        w_title = text(m, y, "Shortcuts", title_f, fg)
        w_title += 16 * s + text(m + w_title + 16 * s, y, "any key closes", hint_f, dim)
        top = y + 40 * s
        line_h = QFontMetricsF(text_f).height() * 1.45

        # --- left column: picture rows ---
        x, y = m, top
        section_gap = (self.SECTION_GAP * s + self.spread)  # spread: fill the height (set_content)
        heading(x, y, "Keys")
        # Left half of the keyboard with its column stagger (KEYBOARD_STAGGER): on each key
        # the tool icon or a short word, below it what the key does with Shift
        cap_w, cap_h, cap_gap = self.KEY_CAP[0] * s, self.KEY_CAP[1] * s, 6 * s
        label_f = self.make_font(13)
        keys_top = y + 14 * s
        for column, (caps, stagger) in enumerate(zip(KEYBOARD_COLUMNS, KEYBOARD_STAGGER)):
            for row, cap in enumerate(caps):
                r = QRectF(x + column * (cap_w + cap_gap), keys_top + (stagger + row) * (cap_h + cap_gap),
                           cap_w, cap_h)
                if p:
                    self.paint_key(p, r, cap, d["keyboard"].get(cap, {}), key_f, label_f, small_f)
        left_w = len(KEYBOARD_COLUMNS) * (cap_w + cap_gap) - cap_gap
        y = keys_top + (max(KEYBOARD_STAGGER) + 3) * (cap_h + cap_gap) - cap_gap + 10 * s + section_gap

        heading(x, y, "Colors", d["color_hint"])
        # One row per keyboard row of the keys (a s d f g / z x c v b), fields without a key
        # (only reachable by cycling) in rows of their own at the end
        sw, gap = self.SWATCH * s, 10 * s
        color_keys = [d["colors"][i] if i < len(d["colors"]) else "" for i in range(len(self.colors))]
        color_rows = keyboard_rows(color_keys)
        row_h = sw + 24 * s + 10 * s  # field, key below it, gap to the next row
        for row, indexes in enumerate(color_rows):
            for col, i in enumerate(indexes):
                r = QRectF(x + col * (sw + gap), y + 14 * s + row * row_h, sw, sw)
                if p:
                    p.setPen(QPen(th.fg(70), max(1.0, s)))
                    p.setBrush(self.colors[i])
                    p.drawRoundedRect(r, 7 * s, 7 * s)
                text(r.left(), r.bottom() + 24 * s, color_keys[i], key_f, accent, "center", sw)
        colors_w = max(max((len(r) for r in color_rows), default=0) * (sw + gap),
                       QFontMetricsF(head_f).horizontalAdvance("COLORS " + d["color_hint"]) + 12 * s)
        colors_bottom = y + 14 * s + max(1, len(color_rows)) * row_h - 10 * s

        # Size to the right of the colors: keeps the left column short
        sx = x + colors_w + self.COLUMN_GAP * s
        size_w = heading(sx, y, "Size", d["size_hint"])
        step = 64 * s
        for i, keys in enumerate(d["sizes"]):
            cx = sx + 20 * s + i * step
            if p:
                p.setPen(Qt.NoPen)
                p.setBrush(fg)
                radius = 3 * s * (i + 1)
                p.drawEllipse(QPointF(cx, y + 34 * s), radius, radius)
            text(cx - step / 2, y + 74 * s, keys, key_f, accent, "center", step)
        size_w = max(size_w, len(d["sizes"]) * step)
        left_w = max(left_w, sx + size_w - x)
        pictures_bottom = max(colors_bottom, y + 74 * s)  # baseline of the last keys
        y = pictures_bottom + self.SECTION_GAP * s

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

        # --- lists (mouse first), in reading order over three columns: the first below the
        # pictures, the other two to the right of them from the top. Split where the columns
        # end as evenly as possible, so no column leaves a large empty area ---
        groups = ([("Mouse", d["mouse"])] if d["mouse"] else []) + list(d["lists"])
        starts = (y, top, top)

        def group_height(entries):
            return 30 * s + len(entries) * line_h + self.LIST_GAP * s

        def parts(i, j):
            return groups[:i], groups[i:j], groups[j:]

        def bottoms(i, j):
            """Column bottoms, lowest first: compared as a whole, so with the same lowest
            column the others are evened out too."""
            return sorted((start + sum(group_height(e) for _, e in part)
                           for start, part in zip(starts, parts(i, j))), reverse=True)
        i, j = min(((i, j) for i in range(len(groups) + 1) for j in range(i, len(groups) + 1)),
                   key=lambda split: bottoms(*split))
        columns = parts(i, j)

        def column_width(part):
            return list_width([e for _, entries in part for e in entries])
        left_w = max(left_w, column_width(columns[0]))
        xs = [m, m + left_w + self.COLUMN_GAP * s]
        xs.append(xs[1] + (column_width(columns[1]) + self.COLUMN_GAP * s if columns[1] else 0))
        bottom = y
        for cx, cy, part in zip(xs, starts, columns):
            key_w = key_width([e for _, entries in part for e in entries])  # aligned per column
            for name, entries in part:
                heading(cx, cy, name)
                cy = entry_list(cx, cy + 30 * s, entries, key_w) + self.LIST_GAP * s
            bottom = max(bottom, cy)
        rx, right_w = xs[2], column_width(columns[2])
        # Room left below the pictures (nothing below them in the left column): set_content
        # spreads it over the gaps between the picture rows, so they use the full height
        last_line = bottom - self.LIST_GAP * s - line_h
        self.slack = max(0.0, last_line - pictures_bottom) if not columns[0] else 0.0

        width = max(rx + right_w, m + w_title) + m
        height = bottom - self.LIST_GAP * s + m - line_h / 2
        return QSizeF(width, height)

    def paint_key(self, p, r, cap, layers, key_f, label_f, small_f):
        """One key of the keyboard picture in rect r: key name at the top left, in the middle
        the tool icon or the short word, at the bottom what Shift does ("⇧ …") or the tool name.
        Keys without a function only as a faint outline."""
        th, s = self.theme, self.scale
        p.setPen(Qt.NoPen if layers else QPen(th.fg(40), max(1.0, s)))
        p.setBrush(th.fg(22) if layers else Qt.NoBrush)
        p.drawRoundedRect(r, 7 * s, 7 * s)
        p.setFont(key_f)
        p.setPen(th.accent if layers else th.fg(90))
        p.drawText(r.adjusted(7 * s, 4 * s, 0, 0), Qt.AlignLeft | Qt.AlignTop, cap)
        tool, label = layers.get("plain", (None, ""))
        middle = QRectF(r.left(), r.top() + r.height() * 0.28, r.width(), r.height() * 0.42)
        if tool is not None:
            icon = r.height() * 0.42  # icons are built for a 30 field
            p.save()
            p.translate(middle.center().x() - icon / 2, middle.center().y() - icon / 2)
            p.scale(icon / 30, icon / 30)
            pen = QPen(th.foreground, 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(tool_icon(tool))
            p.restore()
        elif label:
            p.setFont(label_f)
            p.setPen(th.foreground)
            p.drawText(middle, Qt.AlignCenter, label)
        bottom = QRectF(r.left(), r.bottom() - r.height() * 0.3, r.width(), r.height() * 0.26)
        shift = layers.get("shift")
        if shift or tool is not None:
            p.setFont(small_f)
            p.setPen(th.fg(150))
            p.drawText(bottom, Qt.AlignCenter, f"⇧ {shift[1]}" if shift else label)

    def paintEvent(self, event):
        if not self.data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        background = QColor(self.theme.background)
        background.setAlpha(255)  # opaque: easy to read over any image
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
