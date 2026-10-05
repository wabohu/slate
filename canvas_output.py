"""Output part of the Canvas: render, copy, save and export the image, plus
messages (report) and prompts (ask) via dunst/rofi or Qt.

Mixin like BoardMixin (canvas_board.py): no __init__ of its own, Canvas inherits from it.
The actual work (rendering, clipboard, writing PNGs, dunst, rofi) is done by
export.py, document.py and notify.py; this file only holds what the Canvas contributes.

Manages (created in Canvas.__init__): document_path.
Reads from the Canvas: board, board_color, background_image, export_rect, export_size,
scene_, settings, toast, undo_stack, editing_text, finish_text(), update_bars(),
elements(), update_title().
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QPainter

from commands import AddItemCommand
from document import build_document, elements_from_dicts, save_document
from elements import ImageElement, ShapeElement, blur_block, new_id, pixelate
from export import (copy_data_to_clipboard, copy_text_to_clipboard, copy_to_clipboard, data_from_clipboard,
                    new_file_path, png_bytes, render_scene, save_png, short_path)
from notify import NOT_AVAILABLE, ask, notify
from settings import BOARD_EXPORT_MARGIN
from tools import Tool

# Copied elements in the clipboard: own data type, JSON as in the file format
ELEMENTS_MIME = "application/x-slate-elements"
CLIP_FORMAT = "slate-elements"
DUPLICATE_OFFSET = 20  # Ctrl+D: offset in screen pixels


def rich_copy_path():
    """Private file with the editable version of the most recently copied image."""
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / "slate" / "clipboard.json"


class OutputMixin:
    # --- Image: render, copy, save ---
    def render_image(self):
        """Screenshot plus drawings as a QImage, without the bar and without the text cursor."""
        if self.editing_text:
            self.finish_text()
        self.scene_.clearSelection()  # otherwise the dashed selection frame would be in the image
        self.update_bars()
        if self.board:  # only the used area, scale 1:1
            rect = self.used_rect()
            return render_scene(self.scene_, rect, rect.size().toSize())
        return render_scene(self.scene_, *self.output_area())  # whole screenshot or crop

    def used_rect(self):
        """Whiteboard: area of all elements plus margin; empty = visible area."""
        items = self.elements()
        if not items:
            return QRectF(self.mapToScene(self.viewport().rect()).boundingRect().toAlignedRect())
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-BOARD_EXPORT_MARGIN, -BOARD_EXPORT_MARGIN,
                             BOARD_EXPORT_MARGIN, BOARD_EXPORT_MARGIN)
        return QRectF(rect.toAlignedRect())  # whole pixels, so the image does not get blurry

    # --- Copy, paste, duplicate elements ---
    def copy_selection_or_image(self):
        """Ctrl+C: with a selection the elements (for pasting, also in another window),
        otherwise the whole image as before."""
        items = self.selected_elements()
        if not items or self.editing_text:
            return self.copy_image()
        data = json.dumps({"format": CLIP_FORMAT, "elements": [i.to_dict() for i in items]})
        copy_data_to_clipboard(data.encode(), ELEMENTS_MIME)
        self.report(f"{len(items)} element(s) copied (Ctrl+V pastes)")

    def paste_elements(self):
        """Ctrl+V: paste copied elements at the mouse position (otherwise in the center)."""
        dicts = self.clipboard_elements()
        mouse = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(mouse):
            mouse = self.viewport().rect().center()
        self.insert_copies(dicts, target=self.mapToScene(mouse))

    def clipboard_elements(self):
        """What Ctrl+V pastes, as element dicts: copied elements; otherwise an image from the
        clipboard, namely the editable version if it is our copied image."""
        raw = data_from_clipboard(ELEMENTS_MIME)
        if raw:
            try:
                return json.loads(raw)["elements"]
            except (ValueError, KeyError, TypeError):
                pass  # unusable: maybe there is an image in it
        png = data_from_clipboard("image/png")
        if png:
            try:
                rich = json.loads(rich_copy_path().read_text())
                if rich.get("png_sha256") == hashlib.sha256(png).hexdigest():
                    return rich["elements"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
            image = QImage.fromData(png)
        else:  # other image formats (JPG …), as far as Qt knows them
            image = QGuiApplication.clipboard().image()
        if image.isNull():
            return []
        return [ImageElement(QPointF(0, 0), image).to_dict()]

    def duplicate_selected(self):
        """Ctrl+D: duplicate the selection slightly offset (the clipboard stays untouched)."""
        items = self.selected_elements()
        if items:
            step = DUPLICATE_OFFSET / self.zoom()
            self.insert_copies([i.to_dict() for i in items], offset=QPointF(step, step))

    def insert_copies(self, dicts, target=None, offset=None):
        """Create elements from dicts anew (new IDs, markers keep counting), either with their
        center at target or shifted by offset; one undo step, selected afterwards."""
        dicts = [d for d in dicts
                 if not (self.board and d.get("tool") == "blur")]  # nothing to pixelate on the whiteboard
        # New IDs; lines/arrows stay docked to the copies of their shapes if those are copied
        # along, otherwise the end becomes free (it must not jump back to the original)
        fresh = {d.get("id"): new_id() for d in dicts if d.get("id") is not None}
        dicts = [dict(d, id=fresh.get(d.get("id")) or new_id(),
                      **({"ends": [fresh.get(e) for e in d["ends"]]} if "ends" in d else {}))
                 for d in dicts]
        items = elements_from_dicts(dicts)
        if not items:
            self.report("Nothing to paste (copy elements or an image)")
            return
        order = self.next_marker_order()
        for item in sorted(items, key=lambda i: getattr(i, "marker_order", 0)):
            if isinstance(item, ShapeElement) and item.tool == Tool.MARKER:
                item.marker_order = order
                order += 1
        if target is not None:
            box = QRectF()
            for item in items:
                box = box.united(item.sceneBoundingRect())
            offset = target - box.center()
        for item in items:
            item.setPos(item.pos() + offset)
        if self.editing_text:
            self.finish_text()
        self.set_tool(Tool.SELECT)
        self.scene_.clearSelection()
        self.undo_stack.beginMacro("Paste")
        for item in items:
            self.undo_stack.push(AddItemCommand(self.scene_, item, "Paste"))
        self.undo_stack.endMacro()
        for item in items:
            item.setSelected(True)
        self.update_bars()

    def copy_image(self):
        """Finished image to the clipboard (Enter, Ctrl+C without a selection). In screenshot mode
        also store the editable version (rich_copy), for pasting into the whiteboard."""
        image = self.render_image()
        ok, message = copy_to_clipboard(image)
        if ok and not self.board:
            self.store_rich_copy(png_bytes(image))
        self.report(message, error=not ok)
        return ok

    def store_rich_copy(self, png):
        """Editable version of the copied image: screenshot part as an image element (blur
        burned in) plus the markings in it as elements. Lives in a private file,
        recognized by the fingerprint of the PNG (xclip only offers one data type)."""
        area, size = self.output_area()
        factor = size.width() / max(1.0, area.width())
        background = self.background_to_save().copy(QRectF(area.x() * factor, area.y() * factor,
                                                           size.width(), size.height()).toRect())
        dicts = [ImageElement(area.topLeft(), background, area.size()).to_dict()]
        dicts += [e.to_dict() for e in self.elements()
                  if e.sceneBoundingRect().intersects(area)
                  and not (isinstance(e, ShapeElement) and e.tool == Tool.BLUR)]  # already in the image
        try:
            path = rich_copy_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"format": CLIP_FORMAT, "png_sha256": hashlib.sha256(png).hexdigest(),
                                        "elements": dicts}))
            path.chmod(0o600)
        except OSError as e:
            print(f"[output] editable copy not stored: {e}", file=sys.stderr)

    def copy_and_quit(self):
        """Enter: copy and quit; on the whiteboard only copy (the window stays)."""
        if self.copy_image() and not self.board:
            self.close()

    def copy_path_and_quit(self):
        """Shift+Enter: save like Ctrl+S, absolute path of the file to the clipboard,
        quit; on the whiteboard the window stays open (as with Enter)."""
        path = self.save_drawing()
        if path is None:
            return  # save_drawing has already reported the error
        path = Path(path).resolve()
        copy_text_to_clipboard(str(path))
        self.report(f"Path copied: {short_path(path)}")
        if not self.board:
            self.close()

    def export_image(self):
        """Clean PNG without editing data, always as a new file."""
        path, message = save_png(self.render_image(), self.settings.output_dir)
        self.report(message, error=path is None)

    def save_drawing(self):
        """Editable drawing: a new file the first time, after that overwrite the same one.
        Returns: path of the file, None on error."""
        rendered = self.render_image()
        try:
            path = self.document_path or new_file_path(self.settings.output_dir, "_board" if self.board else "")
        except OSError as e:
            self.report(f"Saving failed: {e}", error=True)
            return None
        background = self.board_color if self.board else self.background_to_save()
        crop = None if self.board else self.crop_rect
        ok, message = save_document(path, rendered, build_document(background, self.elements(), crop))
        if ok:
            self.document_path = path
            self.undo_stack.setClean()  # remember the state: from here on "nothing unsaved"
            if self.board:
                self.update_title()
        self.report(message, error=not ok)
        return path if ok else None

    def background_to_save(self):
        """Raw image for the editable file, with blur areas burned in: no saved
        file ever contains what was pixelated. In the running tool the raw image
        stays unchanged (blur can still be moved/deleted there)."""
        blurs = [e for e in self.elements() if isinstance(e, ShapeElement) and e.tool == Tool.BLUR]
        if not blurs:
            return self.background_image
        image = self.background_image.copy()
        factor = self.scene_.blur_scale
        painter = QPainter(image)
        for element in blurs:
            r = element.mapRectToScene(element.path().boundingRect())
            result = pixelate(self.background_image, QRectF(r.x() * factor, r.y() * factor,
                                                            r.width() * factor, r.height() * factor),
                              blur_block(element.width) * factor)
            if result:
                painter.drawImage(result[1].topLeft(), result[0])
        painter.end()
        return image

    # --- Messages and prompts ---
    def report(self, text, error=False):
        """Result message (saved, copied, error …): via dunst, otherwise an overlay message."""
        if not (self.settings.use_dunst and notify(text, error=error)):
            self.toast.show_message(text)

    def ask(self, question, choices):
        """Choice via rofi, otherwise None. NOT_AVAILABLE = rofi not usable (use Qt).

        In screenshot mode the overlay takes the focus back afterwards (rofi had it).
        """
        if not self.settings.use_rofi:
            return NOT_AVAILABLE
        self.asking = True  # rofi has the focus now, do not take it back
        try:
            return ask(question, choices, self.settings.rofi_theme)
        finally:
            self.asking = False
            if not self.board:
                self.take_focus()
