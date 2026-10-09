"""Undo/redo commands for the drawing surface.

Qt concept: every change is a QUndoCommand with redo() and undo().
QUndoStack.push(cmd) calls cmd.redo() right away and stores the command;
stack.undo() / stack.redo() then walk backwards or forwards through them.
Doing something new after an undo discards the redo steps.

The commands must therefore be written so that redo() is also correct
when the change has already happened (e.g. the item is already in the scene).
"""
import time

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QUndoCommand

from elements import is_label


class AddItemCommand(QUndoCommand):
    """New object (shape or text) in the scene."""

    def __init__(self, scene, item, text="Add object"):
        super().__init__(text)
        self.scene = scene
        self.item = item  # keep a reference, even while the item is not in the scene

    def redo(self):
        if self.item.scene() is None:
            self.scene.addItem(self.item)

    def undo(self):
        self.scene.removeItem(self.item)


def item_above(item):
    """The element directly above item (same level of the scene) or None if it is at the top."""
    scene = item.scene()
    if scene is None:
        return None
    siblings = [i for i in scene.items(Qt.AscendingOrder) if not is_label(i)]  # not parentItem(), see is_label
    index = siblings.index(item)
    return siblings[index + 1] if index + 1 < len(siblings) else None


def apply_order(order):
    """Bring elements into the order order (bottom -> top).

    Qt concept: with equal zValue the scene draws in the order of the siblings;
    stackBefore(b) puts an element directly below b. Applied from top to bottom this gives
    the whole order; other items (e.g. the screenshot) stay where they are.
    """
    for lower, upper in reversed(list(zip(order, order[1:]))):
        lower.stackBefore(upper)


class RemoveItemCommand(QUndoCommand):
    """Remove an object – the counterpart to AddItemCommand. Undo puts it back at
    its old place in the stacking order (not on top)."""

    def __init__(self, scene, item, text="Remove object"):
        super().__init__(text)
        self.scene = scene
        self.item = item
        self.above = None  # element it was below (remembered when removing)

    def redo(self):
        if self.item.scene() is not None:
            self.above = item_above(self.item)
            self.scene.removeItem(self.item)

    def undo(self):
        self.scene.addItem(self.item)
        if self.above is not None and self.above.scene() is self.scene:
            self.item.stackBefore(self.above)


class ReorderCommand(QUndoCommand):
    """Stacking order (front/back) changed; old/new: elements bottom -> top."""

    def __init__(self, old, new, text="Reorder"):
        super().__init__(text)
        self.old = list(old)
        self.new = list(new)

    def redo(self):
        apply_order(self.new)

    def undo(self):
        apply_order(self.old)


class MoveItemCommand(QUndoCommand):
    """One or more objects moved (multi-selection = one undo step).

    items, old_positions, new_positions: one object each or lists of equal length.
    mergeable=True (moving by key): steps in quick succession on the same
    objects are merged into one undo step (see PropertyCommand).
    """

    MERGE_ID = 2
    MERGE_WINDOW = 1.0

    def __init__(self, items, old_positions, new_positions, text="Move", mergeable=False):
        super().__init__(text)
        if not isinstance(items, (list, tuple)):  # a single object
            items, old_positions, new_positions = [items], [old_positions], [new_positions]
        self.items = list(items)
        self.old_positions = [QPointF(p) for p in old_positions]  # copies: better safe than sorry
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
    """Content, color, font size and font kind of a text object changed."""

    def __init__(self, item, old, new, text="Edit text"):
        super().__init__(text)
        self.item = item
        self.old = old  # TextElement.edit_state(): (text, QColor, font size, font kind)
        self.new = new

    def apply(self, state):
        text, color, size, kind = state
        self.item.setPlainText(text)
        if not is_label(self.item):  # a label always has the color of its shape
            self.item.set_color(color)
        self.item.font_kind = kind
        self.item.set_font_size(size)  # builds the font of the kind anew

    def redo(self):
        self.apply(self.new)

    def undo(self):
        self.apply(self.old)


class SetLabelCommand(QUndoCommand):
    """Label of a rectangle/ellipse attached, replaced or removed (old/new: TextElement or None)."""

    def __init__(self, shape, old, new, text="Label"):
        super().__init__(text)
        self.shape = shape
        self.old = old
        self.new = new

    def redo(self):
        self.shape.set_label(self.new)

    def undo(self):
        self.shape.set_label(self.old)


class PropertyCommand(QUndoCommand):
    """A property changed, e.g. color or size of a selected element.

    setter is the method that sets the value (e.g. item.set_color).

    mergeable=True (e.g. for the mouse wheel): if changes to the same property
    follow in quick succession, the undo stack merges them into one step.
    Qt concept: push() calls mergeWith() of the topmost command if both
    have the same id() >= 0; if mergeWith returns True, the new command
    is not stored separately.
    """

    MERGE_ID = 1
    MERGE_WINDOW = 1.0  # seconds; a longer pause = new undo step

    def __init__(self, setter, old, new, text="Change property", mergeable=False):
        super().__init__(text)
        self.setter = setter
        self.old = old
        self.new = new
        self.mergeable = mergeable
        self.time = time.monotonic()

    def id(self):
        return self.MERGE_ID if self.mergeable else -1  # -1 = never merge

    def mergeWith(self, other):
        # Same method on the same object (bound methods compare both)
        if other.setter != self.setter or other.time - self.time > self.MERGE_WINDOW:
            return False
        self.new = other.new   # the old value stays, the new value is taken over
        self.time = other.time
        return True

    def redo(self):
        self.setter(self.new)

    def undo(self):
        self.setter(self.old)


class MultiPropertyCommand(QUndoCommand):
    """The same kind of change on several objects, one undo step (multi-selection).

    changes: list of (setter, old, new), e.g. [(a.set_color, red, blue), (b.set_color, …)].
    mergeable as with PropertyCommand: same setters in quick succession = one step.
    """

    MERGE_ID = 3
    MERGE_WINDOW = PropertyCommand.MERGE_WINDOW

    def __init__(self, changes, text="Change property", mergeable=False):
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
    """One object: PropertyCommand, several: MultiPropertyCommand (same behavior)."""
    if len(changes) == 1:
        setter, old, new = changes[0]
        return PropertyCommand(setter, old, new, text, mergeable)
    return MultiPropertyCommand(changes, text, mergeable)
