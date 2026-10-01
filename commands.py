"""Undo/Redo-Befehle für die Zeichenfläche.

Qt-Konzept: Jede Änderung ist ein QUndoCommand mit redo() und undo().
QUndoStack.push(cmd) ruft sofort cmd.redo() auf und legt den Befehl ab;
stack.undo() / stack.redo() laufen dann rückwärts bzw. vorwärts durch.
Wer nach einem Undo etwas Neues macht, verwirft damit die Redo-Schritte.

Die Befehle müssen darum so geschrieben sein, dass redo() auch dann stimmt,
wenn die Änderung schon passiert ist (z. B. Item liegt schon in der Szene).
"""
import time

from PySide6.QtCore import QPointF
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


class RemoveItemCommand(QUndoCommand):
    """Objekt entfernen – das Gegenstück zu AddItemCommand."""

    def __init__(self, scene, item, text="Objekt entfernen"):
        super().__init__(text)
        self.scene = scene
        self.item = item

    def redo(self):
        if self.item.scene() is not None:
            self.scene.removeItem(self.item)

    def undo(self):
        self.scene.addItem(self.item)


class MoveItemCommand(QUndoCommand):
    """Objekt von old_pos nach new_pos verschoben.

    mergeable=True (Verschieben per Taste): Schritte kurz hintereinander am selben
    Objekt werden zu einem Undo-Schritt zusammengefasst (siehe PropertyCommand).
    """

    MERGE_ID = 2
    MERGE_WINDOW = 1.0

    def __init__(self, item, old_pos, new_pos, text="Verschieben", mergeable=False):
        super().__init__(text)
        self.item = item
        self.old_pos = QPointF(old_pos)  # Kopien: setPos ändert die Originale nicht, aber sicher ist sicher
        self.new_pos = QPointF(new_pos)
        self.mergeable = mergeable
        self.time = time.monotonic()

    def id(self):
        return self.MERGE_ID if self.mergeable else -1

    def mergeWith(self, other):
        if other.item is not self.item or other.time - self.time > self.MERGE_WINDOW:
            return False
        self.new_pos = other.new_pos
        self.time = other.time
        return True

    def redo(self):
        self.item.setPos(self.new_pos)

    def undo(self):
        self.item.setPos(self.old_pos)


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
