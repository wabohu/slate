"""Give the focus back after the screenshot overlay (herbstluftwm).

The overlay bypasses the window manager and takes the keyboard focus itself
(activateWindow). Earlier, no window had the focus afterwards, because herbstluftwm
does not notice this focus change and does not give it back on close.
So the tool gives it back itself on close: to the window herbstluftwm considers
focused at that moment. This also works if you have switched the tag or window
via a hotkey in the meantime.

Without herbstluftwm (herbstclient missing) or without a focused window nothing happens.
Without a screen (tests, QT_QPA_PLATFORM=offscreen) no external programs are ever started.
"""
import os
import shutil
import subprocess
import sys


def _run(cmd):
    """Run a command, return its output; None on any problem."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[wm] {' '.join(cmd)} failed: {e}", file=sys.stderr)
        return None
    return result.stdout.strip()


def focused_window():
    """X window ID of the window herbstluftwm has focused right now, otherwise None."""
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or not shutil.which("herbstclient"):
        return None
    # Without a focused window (empty tag) the attribute does not exist -> error, None
    try:
        result = subprocess.run(["herbstclient", "attr", "clients.focus.winid"],
                                capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    winid = result.stdout.strip()
    return winid if result.returncode == 0 and winid else None


def restore_focus():
    """Give the keyboard focus back to the window herbstluftwm has focused."""
    winid = focused_window()
    if winid is None:
        return
    if shutil.which("xdotool"):
        _run(["xdotool", "windowfocus", winid])  # sets the X focus directly
    else:
        _run(["herbstclient", "jumpto", winid])
