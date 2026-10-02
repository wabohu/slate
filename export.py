"""Output: render the scene as an image, copy it to the clipboard, save it as PNG.

X11 peculiarity: the content of the clipboard belongs to the program that copied
it. When that program exits, it is gone. That is why we copy with xclip: it keeps running
in the background after copying and serves the image until something else is copied.
"""
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QRectF, QStandardPaths
from PySide6.QtGui import QGuiApplication, QImage, QPainter


def render_scene(scene, source_rect, size):
    """Area source_rect of the scene as a QImage of size size (pixels).

    source_rect is the area of the screenshot. Taking the whole scene instead,
    a stroke at the edge could enlarge it, and the image would get squashed.
    """
    image = QImage(size, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    scene.render(painter, QRectF(image.rect()), source_rect)
    painter.end()
    return image


def png_bytes(image):
    """QImage -> PNG as bytes (via a buffer in memory)."""
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def copy_to_clipboard(image):
    """Image to the clipboard. Returns: (ok, message)."""
    if shutil.which("xclip"):
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
                input=png_bytes(image),
                # Do not tie the outputs to us, otherwise we would wait for the background process
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=True,
            )
            return True, "Copied to the clipboard"
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[export] xclip failed: {e}", file=sys.stderr)
    # Fallback: Qt clipboard. Only lasts while the tool is running (or a manager takes over)
    QGuiApplication.clipboard().setImage(image)
    print("[export] xclip missing, image only in the Qt clipboard", file=sys.stderr)
    return True, "Copied to the clipboard (without xclip, possibly not permanent)"


def copy_text_to_clipboard(text):
    """Text (e.g. a path) to the clipboard, like copy_to_clipboard. Returns: ok."""
    if shutil.which("xclip"):
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard", "-i"],
                input=text.encode(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=True,
            )
            return True
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[export] xclip failed: {e}", file=sys.stderr)
    QGuiApplication.clipboard().setText(text)
    print("[export] xclip missing, text only in the Qt clipboard", file=sys.stderr)
    return True


def copy_data_to_clipboard(data, mime):
    """Arbitrary data (bytes) with its own data type to the clipboard, e.g. copied
    elements ("application/x-slate-elements"). Via xclip they survive quitting,
    so they can be pasted in another window. Returns: ok."""
    if shutil.which("xclip"):
        try:
            subprocess.run(["xclip", "-selection", "clipboard", "-t", mime, "-i"], input=data,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=True)
            return True
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[export] xclip failed: {e}", file=sys.stderr)
    mime_data = QMimeData()
    mime_data.setData(mime, QByteArray(data))
    QGuiApplication.clipboard().setMimeData(mime_data)
    return True


def data_from_clipboard(mime):
    """Data of this type from the clipboard (bytes) or None. Qt reads the clipboard
    from X, so also what another (already closed) window left behind via xclip.

    As a fallback xclip, but only if the type is in the list of offered types (TARGETS):
    otherwise xclip as the owner answers every request with its content, no matter which
    type was asked for (a PNG would then seemingly turn into "elements")."""
    mime_data = QGuiApplication.clipboard().mimeData()
    if mime_data is not None and mime_data.hasFormat(mime):
        return bytes(mime_data.data(mime))
    if not shutil.which("xclip"):
        return None
    try:
        targets = subprocess.run(["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
                                 capture_output=True, text=True, timeout=5)
        if mime not in targets.stdout.split():
            return None
        result = subprocess.run(["xclip", "-selection", "clipboard", "-t", mime, "-o"],
                                capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 and result.stdout else None


def default_output_dir():
    """~/Pictures/slate or the XDG pictures folder, if it is named differently."""
    pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
    return Path(pictures or Path.home() / "Pictures") / "slate"


def new_file_path(directory, suffix=""):
    """Free file name with a time stamp in the folder (gets created), e.g.
    slate_2026-10-01_14-03-22.png; on a collision _2, _3 … May raise OSError."""
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("slate_%Y-%m-%d_%H-%M-%S") + suffix
    path = directory / f"{stem}.png"
    counter = 2
    while path.exists():  # saving twice in the same second
        path = directory / f"{stem}_{counter}.png"
        counter += 1
    return path


def short_path(path):
    """Path for display, home folder as ~."""
    return str(path).replace(str(Path.home()), "~", 1)


def save_png(image, directory):
    """Clean PNG (without editing data) with a time stamp. Returns: (path or None, message)."""
    try:
        path = new_file_path(directory, suffix="_export")
        if not image.save(str(path), "PNG"):
            raise OSError("QImage.save did not work")
    except OSError as e:
        print(f"[export] Export failed: {e}", file=sys.stderr)
        return None, f"Export failed: {e}"
    return path, f"Exported: {short_path(path)}"
