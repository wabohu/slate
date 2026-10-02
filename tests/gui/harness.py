"""Harness for GUI tests: a separate invisible X server with herbstluftwm and sxhkd.

Your real session stays untouched: everything runs on a separate display (Xvfb),
with a separate HOME (config, history, output folder in a temp folder) and without
a connection to the session D-Bus (no notifications on your desktop).

    with Session("name") as s:
        s.key("alt+Escape")          # key(s) via xdotool, goes to sxhkd or the focus
        s.drag(100, 100, 300, 200)   # drag the mouse
        s.screenshot("01-step")     # image to tests/gui/out/<name>/

Screenshots are stored in tests/gui/out/ (not in Git). Claude can read them.
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
SLATE = REPO / "slate.py"
KEYSINK = Path(__file__).resolve().parent / "keysink.py"

# Bindings in the test: start via Alt+Escape as in real use (via the executable slate.py,
# so it also checks the executable bit), plus two test hotkeys
SXHKDRC = """\
alt + Escape
  {slate}

alt + Delete
  {slate} --board

super + k
  touch {tmp}/hotkey-fired

super + j
  herbstclient jumpto $(xdotool search --name '^keysink$' | head -1)
"""

SLATE_CONFIG = """\
[ui]
messages = "toast"   # no dunst in the test

[output]
dir = "{tmp}/output"
"""

failures = []
_app = None  # QGuiApplication for load_elements


def check(name, condition):
    print(f"{'OK  ' if condition else 'FAIL  '}  {name}", flush=True)
    if not condition:
        failures.append(name)
    return condition


def summary():
    print("\nAll OK." if not failures else f"\n{len(failures)} failed.")
    return 1 if failures else 0


def wait(condition, timeout=5.0, step=0.05):
    """Check condition() repeatedly until true or time is up. Returns: true/false."""
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
    raise RuntimeError("no free display found")


class Session:
    def __init__(self, name, size="1920x1080"):
        self.name = name
        self.size = size
        self.tmp = Path(tempfile.mkdtemp(prefix="slate-gui-"))
        self.out = OUT / name
        self.procs = []
        self.display = _free_display()

    # --- setup / teardown ---
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
        (home / ".config" / "slate").mkdir(parents=True)
        (home / ".config" / "slate" / "config.toml").write_text(SLATE_CONFIG.format(tmp=self.tmp))
        sxhkdrc = self.tmp / "sxhkdrc"
        sxhkdrc.write_text(SXHKDRC.format(slate=SLATE, tmp=self.tmp))
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
            raise RuntimeError("Xvfb does not start")
        self.spawn(["herbstluftwm", "--autostart", str(autostart)])
        if not wait(lambda: self.run(["herbstclient", "get", "focus_follows_mouse"]).stdout.strip() == "true", 10):
            raise RuntimeError("herbstluftwm does not start")
        self.spawn(["sxhkd", "-c", str(sxhkdrc)], log="sxhkd")  # including the output of slate
        time.sleep(0.5)  # sxhkd does not report when it is ready

    def stop(self):
        for pid in self.slate_pids():
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

    # --- processes and windows ---
    def slate_pids(self):
        """PIDs of slate.py on THIS display (never your real instances)."""
        pids = []
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                cmdline = (proc / "cmdline").read_bytes()
                if b"slate.py" not in cmdline:
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
        """Is a rofi window visible right now?"""
        return bool(self.run(["xdotool", "search", "--onlyvisible", "--class", "rofi"]).stdout.strip())

    def focus_id(self):
        result = self.run(["xdotool", "getwindowfocus"])
        return int(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None

    # --- input ---
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

    # --- results ---
    def screenshot(self, name):
        path = self.out / f"{name}.png"
        self.run(["import", "-window", "root", str(path)])
        return path

    def pixel(self, x, y, name="pixel"):
        """Color of a screen point as "#rrggbb" (via a screenshot)."""
        return _qt_image(self.screenshot(name)).pixelColor(x, y).name()

    def history_entries(self):
        directory = Path(self.env["XDG_DATA_HOME"]) / "slate" / "history"
        return sorted(directory.glob("slate_*.png")) if directory.exists() else []

    def start_keysink(self):
        """Start the test window, wait until it is there and has the focus. Returns: output file."""
        out = self.tmp / "keysink.txt"
        self.spawn([sys.executable, str(KEYSINK), str(out)], log="keysink")
        if not wait(lambda: self.window_named("keysink") is not None, 10):
            raise RuntimeError("keysink window does not appear")
        return out


def _qt():
    """Qt in the test process itself, without a screen (to read images and files)."""
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
    """Read a saved drawing: (background, elements). The background is a QImage
    (screenshot) or a QColor (whiteboard)."""
    _qt()
    from document import load_document
    background, elements, _, _ = load_document(path)
    return background, elements


def load_elements(path):
    """Elements of a saved drawing."""
    return load_drawing(path)[1]
