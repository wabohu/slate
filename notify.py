"""Messages and prompts via external programs: dunst (notify-send) and rofi.

Both functions report back whether it worked. If it does not work (program
missing, error, timeout), the caller uses the Qt solution (Toast or
QMessageBox). The tool never crashes because of this.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROFI_THEME = Path(__file__).resolve().parent / "rofi" / "slate.rasi"
ROFI_COLORS = Path.home() / ".config" / "rofi" / "colors.rasi"
NOT_AVAILABLE = object()  # return value of ask() when rofi is not usable

_last_notification_id = None  # replace the same notification instead of stacking new ones


def _headless():
    """Without a real screen (tests with QT_QPA_PLATFORM=offscreen) never create external
    windows or notifications on the desktop."""
    return os.environ.get("QT_QPA_PLATFORM") == "offscreen"


def notify(text, error=False, timeout_ms=3000):
    """Notification via notify-send (dunst). Returns: True if it went out."""
    global _last_notification_id
    if _headless() or not shutil.which("notify-send"):
        return False
    cmd = ["notify-send", "--app-name=slate", "--print-id",
           f"--urgency={'critical' if error else 'normal'}", f"--expire-time={timeout_ms}"]
    if _last_notification_id:
        cmd.append(f"--replace-id={_last_notification_id}")
    cmd += ["slate", text]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[notify] notify-send failed: {e}", file=sys.stderr)
        return False
    _last_notification_id = result.stdout.strip() or None
    return True


def ask(question, choices, theme=None):
    """Choice via rofi -dmenu. Returns: index of the choice, None on Esc/cancel,
    NOT_AVAILABLE if rofi is missing or does not start (then use a Qt dialog).

    rofi grabs the keyboard itself; an own keyboard grab would have to be
    released beforehand (the tool no longer uses one, see Canvas.show_overlay).
    """
    if _headless() or not shutil.which("rofi"):
        return NOT_AVAILABLE
    theme = Path(theme).expanduser() if theme else ROFI_THEME
    # -i: case-insensitive, -matching fuzzy: "dc" finds "Discard", "cn" finds "Cancel"
    cmd = ["rofi", "-dmenu", "-i", "-matching", "fuzzy", "-no-custom", "-format", "i",
           "-p", "", "-mesg", question]
    if theme.is_file():
        cmd += ["-theme", str(theme)]
        if ROFI_COLORS.is_file():  # also load own colors, if present
            cmd += ["-theme-str", f'@import "{ROFI_COLORS}"']
    try:
        result = subprocess.run(cmd, input="\n".join(choices), capture_output=True,
                                text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[notify] rofi failed: {e}", file=sys.stderr)
        return NOT_AVAILABLE
    if result.returncode == 1:  # Esc
        return None
    try:
        index = int(result.stdout.strip())
    except ValueError:
        print(f"[notify] rofi: unexpected output {result.stdout!r} {result.stderr.strip()!r}",
              file=sys.stderr)
        return NOT_AVAILABLE
    return index if 0 <= index < len(choices) else None
