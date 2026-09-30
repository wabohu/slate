"""Undo/Redo-Befehle für die Zeichenfläche.

Qt-Konzept: Jede Änderung ist ein QUndoCommand mit redo() und undo().
QUndoStack.push(cmd) ruft sofort cmd.redo() auf und legt den Befehl ab;
stack.undo() / stack.redo() laufen dann rückwärts bzw. vorwärts durch.
Wer nach einem Undo etwas Neues macht, verwirft damit die Redo-Schritte.

Die Befehle müssen darum so geschrieben sein, dass redo() auch dann stimmt,
wenn die Änderung schon passiert ist (z. B. Item liegt schon in der Szene).
"""
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
    """Objekt von old_pos nach new_pos verschoben."""

    def __init__(self, item, old_pos, new_pos, text="Verschieben"):
        super().__init__(text)
        self.item = item
        self.old_pos = old_pos
        self.new_pos = new_pos

    def redo(self):
        self.item.setPos(self.new_pos)

    def undo(self):
        self.item.setPos(self.old_pos)


class EditTextCommand(QUndoCommand):
    """Inhalt und Farbe eines Textobjekts geändert."""

    def __init__(self, item, old, new, text="Text bearbeiten"):
        super().__init__(text)
        self.item = item
        self.old = old  # (Text, QColor)
        self.new = new

    def apply(self, state):
        text, color = state
        self.item.setPlainText(text)
        self.item.set_color(color)

    def redo(self):
        self.apply(self.new)

    def undo(self):
        self.apply(self.old)
