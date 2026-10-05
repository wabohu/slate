"""History part of the Canvas (roadmap 10): save screenshots automatically, browse with ← →.

Flow in screenshot mode (never on the whiteboard):
- Start: start_history() remembers the file name for a new entry (time of the
  screenshot), but writes nothing yet. Screenshots without changes never end up in the history.
- Every change (undo stack changes): save after a short pause; the first time
  the file is created (and old entries are cleaned up). So even a crash costs
  at most the last second. While typing, drawing or
  dragging, saving waits until the action is finished.
- Quit: save anything pending right away (flush_history).
- ← / →: save the current state, load the older or newer entry into the same canvas.
  Undo starts over there; changes go into that entry again.

Qt concept QTimer: a single-shot timer (setSingleShot) calls a function when it expires.
Calling start() again resets it; so it only saves once things have been quiet for a while.

Mixin like BoardMixin (canvas_board.py). Manages (created in Canvas.__init__):
history_path (current entry or None = no history), history_timer.
Reads from the Canvas: board, settings, scene_, export_rect, export_size, background_image,
editing_text, current_item, dragging, resizing, elements(), finish_text(),
replace_content(), report().
"""
import sys

from PySide6.QtGui import QImage, QPixmap

import history
from document import build_document, load_document, save_document
from export import render_scene

HISTORY_SAVE_DELAY_MS = 1000  # this long quiet after a change, then it is saved


class HistoryMixin:
    def start_history(self, path=None):
        """Turn the history on for this session. path=None: new entry (fresh
        screenshot); otherwise an existing entry (opened from the history)."""
        if self.board or not self.settings.history_enabled:
            return
        directory = self.settings.history_dir
        if path is None:
            try:
                path = history.new_entry(directory)  # only the name, the file comes when saving
            except OSError as e:
                self.report(f"History off: {e}", error=True)
                return
        self.history_path = path

    def schedule_history_save(self, _index=None):
        """After a change: schedule saving (restart the timer)."""
        if self.history_path is not None:
            self.history_timer.start(HISTORY_SAVE_DELAY_MS)

    def busy(self):
        """Is an action in progress (typing, drawing, dragging)? Then do not save."""
        return bool(self.editing_text or self.current_item or self.dragging or self.resizing or self.rotating)

    def save_history(self):
        """Write the current state into the history entry (called by the timer)."""
        if self.history_path is None:
            return
        if self.busy():
            self.history_timer.start(HISTORY_SAVE_DELAY_MS)  # try again later
            return
        if not self.history_path.exists():  # first state of this entry: make room
            history.prune(self.settings.history_dir, self.settings.history_keep - 1)
        # Render directly instead of render_image(): that would end selection and text input
        rendered = render_scene(self.scene_, *self.output_area())
        ok, message = save_document(self.history_path, rendered,
                                    build_document(self.background_to_save(), self.elements(), self.crop_rect))
        if not ok:
            print(f"[history] {message}", file=sys.stderr)

    def flush_history(self):
        """When quitting or browsing: save anything pending right away."""
        if self.history_path is None or not self.history_timer.isActive():
            return
        self.history_timer.stop()
        if self.editing_text:
            self.finish_text()
        self.save_history()

    def history_step(self, step):
        """← (step=-1) older, → (step=+1) newer entry."""
        if self.board:
            return
        if self.history_path is None:
            self.report("No history (turned off or file opened from outside the history)")
            return
        self.flush_history()
        files = history.entries(self.settings.history_dir)
        names = [p.name for p in files]
        current = names.index(self.history_path.name) if self.history_path.name in names else len(files)
        target = current + step
        if not 0 <= target < len(files):
            self.report("Oldest entry in the history" if step < 0 else "Newest entry in the history")
            return
        background, elements, _, message, crop = load_document(files[target], with_crop=True)
        if not isinstance(background, QImage):  # unreadable (None) or whiteboard (QColor)
            self.report(f"History: {message}", error=True)
            return
        self.replace_content(QPixmap.fromImage(background), elements)
        self.set_crop(crop)
        self.history_path = files[target]
        self.report(f"History {target + 1}/{len(files)}: {history.label(files[target])}")
