"""Undo/Redo-Befehle für die Zeichenfläche.

Qt-Konzept: Jede Änderung ist ein QUndoCommand mit redo() und undo().
QUndoStack.push(cmd) ruft sofort cmd.redo() auf und legt den Befehl ab;
stack.undo() / stack.redo() laufen dann rückwärts bzw. vorwärts durch.
Wer nach einem Undo etwas Neues macht, verwirft damit die Redo-Schritte.

Die Befehle müssen darum so geschrieben sein, dass redo() auch dann stimmt,
wenn die Änderung schon passiert ist (z. B. Item liegt schon in der Szene).
"""
import time

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QUndoCommand


class AddItemCommand(QUndoCommand):
    """Neues Objekt (Form oder Text) in der Szene."""

    def __init__(self, scene, item, text="Objekt hinzufügen"):
        super().__init__(text)
        self.scene = scene
        self.item = item  # Referenz halten, auch wenn das Item gerade nicht in der Szene ist

    def redo(self):
        if self.item.scene() is None:
            self.scene.addItem(self.item)

    def undo(self):
        self.scene.removeItem(self.item)


def item_above(item):
    """Das Element direkt über item (gleiche Ebene der Szene) oder None, wenn es ganz oben liegt."""
    scene = item.scene()
    if scene is None:
        return None
    siblings = [i for i in scene.items(Qt.AscendingOrder) if i.parentItem() is None]
    index = siblings.index(item)
    return siblings[index + 1] if index + 1 < len(siblings) else None


def apply_order(order):
    """Elemente in die Reihenfolge order bringen (unten -> oben).

    Qt-Konzept: Bei gleichem zValue zeichnet die Szene in der Reihenfolge der Geschwister;
    stackBefore(b) legt ein Element direkt unter b. Von oben nach unten angewendet ergibt
    das die ganze Reihenfolge; andere Items (z. B. der Screenshot) bleiben, wo sie sind.
    """
    for lower, upper in reversed(list(zip(order, order[1:]))):
        lower.stackBefore(upper)


class RemoveItemCommand(QUndoCommand):
    """Objekt entfernen – das Gegenstück zu AddItemCommand. Undo legt es wieder an
    seinen alten Platz in der Reihenfolge (nicht obenauf)."""

    def __init__(self, scene, item, text="Objekt entfernen"):
        super().__init__(text)
        self.scene = scene
        self.item = item
        self.above = None  # Element, unter dem es lag (beim Entfernen gemerkt)

    def redo(self):
        if self.item.scene() is not None:
            self.above = item_above(self.item)
            self.scene.removeItem(self.item)

    def undo(self):
        self.scene.addItem(self.item)
        if self.above is not None and self.above.scene() is self.scene:
            self.item.stackBefore(self.above)


class ReorderCommand(QUndoCommand):
    """Reihenfolge (Vorder-/Hintergrund) geändert; old/new: Elemente unten -> oben."""

    def __init__(self, old, new, text="Reihenfolge"):
        super().__init__(text)
        self.old = list(old)
        self.new = list(new)

    def redo(self):
        apply_order(self.new)

    def undo(self):
        apply_order(self.old)


class MoveItemCommand(QUndoCommand):
    """Ein oder mehrere Objekte verschoben (Mehrfachauswahl = ein Undo-Schritt).

    items, old_positions, new_positions: je ein Objekt bzw. Listen gleicher Länge.
    mergeable=True (Verschieben per Taste): Schritte kurz hintereinander an denselben
    Objekten werden zu einem Undo-Schritt zusammengefasst (siehe PropertyCommand).
    """

    MERGE_ID = 2
    MERGE_WINDOW = 1.0

    def __init__(self, items, old_positions, new_positions, text="Verschieben", mergeable=False):
        super().__init__(text)
        if not isinstance(items, (list, tuple)):  # ein einzelnes Objekt
            items, old_positions, new_positions = [items], [old_positions], [new_positions]
        self.items = list(items)
        self.old_positions = [QPointF(p) for p in old_positions]  # Kopien: sicher ist sicher
        self.new_positions = [QPointF(p) for p in new_positions]
        self.mergeable = mergeable
        self.time = time.monotonic()

    def id(self):
        return self.MERGE_ID if self.mergeable else -1

    def mergeWith(self, other):
        same = len(other.items) == len(self.items) and all(a is b for a, b in zip(other.items, self.items))
        if not same or other.time - self.time > self.MERGE_WINDOW:
            return False
        self.new_positions = other.new_positions
        self.time = other.time
        return True

    def redo(self):
        for item, pos in zip(self.items, self.new_positions):
            item.setPos(pos)

    def undo(self):
        for item, pos in zip(self.items, self.old_positions):
            item.setPos(pos)


class EditTextCommand(QUndoCommand):
    """Inhalt, Farbe und Schriftgröße eines Textobjekts geändert."""

    def __init__(self, item, old, new, text="Text bearbeiten"):
        super().__init__(text)
        self.item = item
        self.old = old  # (Text, QColor, Schriftgröße)
        self.new = new

    def apply(self, state):
        text, color, size = state
        self.item.setPlainText(text)
        self.item.set_color(color)
        self.item.set_font_size(size)

    def redo(self):
        self.apply(self.new)

    def undo(self):
        self.apply(self.old)


class PropertyCommand(QUndoCommand):
    """Eine Eigenschaft geändert, z. B. Farbe oder Größe eines ausgewählten Elements.

    setter ist die Methode, die den Wert setzt (z. B. item.set_color).

    mergeable=True (z. B. beim Mausrad): Folgen kurz hintereinander Änderungen
    derselben Eigenschaft, fasst der Undo-Stack sie zu einem Schritt zusammen.
    Qt-Konzept: push() ruft mergeWith() des obersten Befehls auf, wenn beide
    dieselbe id() >= 0 haben; gibt mergeWith True zurück, wird der neue Befehl
    nicht einzeln abgelegt.
    """

    MERGE_ID = 1
    MERGE_WINDOW = 1.0  # Sekunden; längere Pause = neuer Undo-Schritt

    def __init__(self, setter, old, new, text="Eigenschaft ändern", mergeable=False):
        super().__init__(text)
        self.setter = setter
        self.old = old
        self.new = new
        self.mergeable = mergeable
        self.time = time.monotonic()

    def id(self):
        return self.MERGE_ID if self.mergeable else -1  # -1 = nie zusammenfassen

    def mergeWith(self, other):
        # Gleiche Methode am gleichen Objekt (gebundene Methoden vergleichen beides)
        if other.setter != self.setter or other.time - self.time > self.MERGE_WINDOW:
            return False
        self.new = other.new   # alter Wert bleibt, neuer Wert wird übernommen
        self.time = other.time
        return True

    def redo(self):
        self.setter(self.new)

    def undo(self):
        self.setter(self.old)


class MultiPropertyCommand(QUndoCommand):
    """Dieselbe Art Änderung an mehreren Objekten, ein Undo-Schritt (Mehrfachauswahl).

    changes: Liste von (setter, alt, neu), z. B. [(a.set_color, rot, blau), (b.set_color, …)].
    mergeable wie bei PropertyCommand: gleiche Setter kurz hintereinander = ein Schritt.
    """

    MERGE_ID = 3
    MERGE_WINDOW = PropertyCommand.MERGE_WINDOW

    def __init__(self, changes, text="Eigenschaft ändern", mergeable=False):
        super().__init__(text)
        self.changes = list(changes)
        self.mergeable = mergeable
        self.time = time.monotonic()

    def id(self):
        return self.MERGE_ID if self.mergeable else -1

    def mergeWith(self, other):
        setters = [c[0] for c in self.changes]
        if [c[0] for c in other.changes] != setters or other.time - self.time > self.MERGE_WINDOW:
            return False
        self.changes = [(setter, old, new) for (setter, old, _), (_, _, new) in zip(self.changes, other.changes)]
        self.time = other.time
        return True

    def redo(self):
        for setter, _, new in self.changes:
            setter(new)

    def undo(self):
        for setter, old, _ in self.changes:
            setter(old)


def property_command(changes, text, mergeable=False):
    """Ein Objekt: PropertyCommand, mehrere: MultiPropertyCommand (gleiches Verhalten)."""
    if len(changes) == 1:
        setter, old, new = changes[0]
        return PropertyCommand(setter, old, new, text, mergeable)
    return MultiPropertyCommand(changes, text, mergeable)
