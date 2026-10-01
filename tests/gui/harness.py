"""Harness für GUI-Tests: eigener unsichtbarer X-Server mit herbstluftwm und sxhkd.

Deine echte Sitzung bleibt unberührt: Alles läuft auf einem eigenen Display (Xvfb),
mit eigenem HOME (Config, Verlauf, Ausgabeordner in einem Temp-Ordner) und ohne
Verbindung zum Session-D-Bus (keine Benachrichtigungen auf deinem Desktop).

    with Session("name") as s:
        s.key("alt+Escape")          # Taste(n) über xdotool, landet bei sxhkd bzw. im Fokus
        s.drag(100, 100, 300, 200)   # Maus ziehen
        s.screenshot("01-schritt")   # Bild nach tests/gui/out/<name>/

Ablage der Bildschirmfotos: tests/gui/out/ (nicht im Git). Claude kann sie lesen.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
ANNOTATE = REPO / "annotate.py"
KEYSINK = Path(__file__).resolve().parent / "keysink.py"

# Belegung im Test: Start wie bei dir per Alt+Escape (über das ausführbare annotate.py,
# prüft also auch das Ausführbar-Bit), dazu zwei Test-Hotkeys
SXHKDRC = """\
alt + Escape
  {annotate}

alt + Delete
  {annotate} --board

super + k
  touch {tmp}/hotkey-fired

super + j
  herbstclient jumpto $(xdotool search --name '^keysink$' | head -1)
"""

ANNOTATE_CONFIG = """\
[ui]
messages = "toast"   # kein dunst im Test

[output]
dir = "{tmp}/output"
"""

failures = []
_app = None  # QGuiApplication für load_elements


def check(name, condition):
    print(f"{'OK  ' if condition else 'FEHLER'}  {name}", flush=True)
    if not condition:
        failures.append(name)
    return condition


def summary():
    print("\nAlles OK." if not failures else f"\n{len(failures)} Fehler.")
    return 1 if failures else 0


def wait(condition, timeout=5.0, step=0.05):
    """condition() wiederholt prüfen, bis wahr oder Zeit um. Rückgabe: wahr/falsch."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if condition():
                return True
        except (subprocess.SubprocessError, OSError, ValueError):
            pass
        time.sleep(step)
    return False


def _free_display():
    for n in range(90, 140):
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(f"/tmp/.X{n}-lock").exists():
            return f":{n}"
    raise RuntimeError("kein freies Display gefunden")


class Session:
    def __init__(self, name, size="1920x1080"):
        self.name = name
        self.size = size
        self.tmp = Path(tempfile.mkdtemp(prefix="annotate-gui-"))
        self.out = OUT / name
        self.procs = []
        self.display = _free_display()

    # --- Aufbau / Abbau ---
    def __enter__(self):
        try:
            self.start()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        home = self.tmp / "home"
        (home / ".config" / "annotate").mkdir(parents=True)
        (home / ".config" / "annotate" / "config.toml").write_text(ANNOTATE_CONFIG.format(tmp=self.tmp))
        sxhkdrc = self.tmp / "sxhkdrc"
        sxhkdrc.write_text(SXHKDRC.format(annotate=ANNOTATE, tmp=self.tmp))
        autostart = self.tmp / "hlwm-autostart"
        autostart.write_text("#!/bin/sh\nherbstclient set focus_follows_mouse true\n")
        autostart.chmod(0o755)

        env = {k: v for k, v in os.environ.items()
               if k not in ("QT_QPA_PLATFORM", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY")}
        env.update(DISPLAY=self.display, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_DATA_HOME=str(home / ".local" / "share"), XDG_RUNTIME_DIR=str(self.tmp))
        self.env = env

        self.spawn(["Xvfb", self.display, "-screen", "0", f"{self.size}x24", "-nolisten", "tcp"])
        if not wait(lambda: self.run(["xdotool", "getdisplaygeometry"]).returncode == 0, 10):
            raise RuntimeError("Xvfb startet nicht")
        self.spawn(["herbstluftwm", "--autostart", str(autostart)])
        if not wait(lambda: self.run(["herbstclient", "get", "focus_follows_mouse"]).stdout.strip() == "true", 10):
            raise RuntimeError("herbstluftwm startet nicht")
        self.spawn(["sxhkd", "-c", str(sxhkdrc)], log="sxhkd")  # inkl. Ausgaben von annotate
        time.sleep(0.5)  # sxhkd meldet nicht, wann es bereit ist

    def stop(self):
        for pid in self.annotate_pids():
            os.kill(pid, signal.SIGKILL)
        for proc in reversed(self.procs):
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def spawn(self, cmd, log=None):
        stream = open(self.out / f"{log}.log", "w") if log else subprocess.DEVNULL
        proc = subprocess.Popen(cmd, env=self.env, stdout=stream, stderr=subprocess.STDOUT)
        self.procs.append(proc)
        return proc

    def run(self, cmd):
        return subprocess.run(cmd, env=self.env, capture_output=True, text=True, timeout=10)

    # --- Prozesse und Fenster ---
    def annotate_pids(self):
        """PIDs von annotate.py auf DIESEM Display (nie deine echten Instanzen)."""
        pids = []
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                cmdline = (proc / "cmdline").read_bytes()
                if b"annotate.py" not in cmdline:
                    continue
                environ = (proc / "environ").read_bytes().split(b"\0")
            except OSError:
                continue
            if f"DISPLAY={self.display}".encode() in environ:
                pids.append(int(proc.name))
        return pids

    def windows_of(self, pid):
        result = self.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)])
        return [int(w) for w in result.stdout.split()]

    def window_named(self, name):
        result = self.run(["xdotool", "search", "--onlyvisible", "--name", f"^{name}$"])
        ids = [int(w) for w in result.stdout.split()]
        return ids[0] if ids else None

    def window_name(self, win):
        result = self.run(["xdotool", "getwindowname", str(win)])
        return result.stdout.strip() if result.returncode == 0 else None

    def rofi_open(self):
        """Ist gerade ein rofi-Fenster sichtbar?"""
        return bool(self.run(["xdotool", "search", "--onlyvisible", "--class", "rofi"]).stdout.strip())

    def focus_id(self):
        result = self.run(["xdotool", "getwindowfocus"])
        return int(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None

    # --- Eingabe ---
    def key(self, *keys):
        self.run(["xdotool", "key", "--clearmodifiers", *keys])

    def type(self, text):
        self.run(["xdotool", "type", "--delay", "30", text])

    def move(self, x, y):
        self.run(["xdotool", "mousemove", str(x), str(y)])

    def drag(self, x1, y1, x2, y2):
        self.run(["xdotool", "mousemove", str(x1), str(y1), "mousedown", "1",
                  "mousemove", str((x1 + x2) // 2), str((y1 + y2) // 2),
                  "mousemove", str(x2), str(y2), "mouseup", "1"])

    # --- Ergebnisse ---
    def screenshot(self, name):
        path = self.out / f"{name}.png"
        self.run(["import", "-window", "root", str(path)])
        return path

    def pixel(self, x, y, name="pixel"):
        """Farbe eines Bildschirmpunkts als "#rrggbb" (über ein Bildschirmfoto)."""
        return _qt_image(self.screenshot(name)).pixelColor(x, y).name()

    def history_entries(self):
        directory = Path(self.env["XDG_DATA_HOME"]) / "annotate" / "history"
        return sorted(directory.glob("annotate_*.png")) if directory.exists() else []

    def start_keysink(self):
        """Testfenster starten, warten bis es da ist und den Fokus hat. Rückgabe: Ausgabedatei."""
        out = self.tmp / "keysink.txt"
        self.spawn([sys.executable, str(KEYSINK), str(out)], log="keysink")
        if not wait(lambda: self.window_named("keysink") is not None, 10):
            raise RuntimeError("keysink-Fenster erscheint nicht")
        return out


def _qt():
    """Qt im Test-Prozess selbst, ohne Bildschirm (zum Lesen von Bildern und Dateien)."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from PySide6.QtGui import QGuiApplication
    global _app
    _app = QGuiApplication.instance() or QGuiApplication([])


def _qt_image(path):
    _qt()
    from PySide6.QtGui import QImage
    return QImage(str(path))


def load_drawing(path):
    """Gespeicherte Zeichnung lesen: (Hintergrund, Elemente). Hintergrund ist ein QImage
    (Screenshot) oder eine QColor (Whiteboard)."""
    _qt()
    from document import load_document
    background, elements, _, _ = load_document(path)
    return background, elements


def load_elements(path):
    """Elemente einer gespeicherten Zeichnung."""
    return load_drawing(path)[1]
