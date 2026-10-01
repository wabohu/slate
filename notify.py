"""Meldungen und Nachfragen über externe Programme: dunst (notify-send) und rofi.

Beide Funktionen melden zurück, ob es geklappt hat. Klappt es nicht (Programm
fehlt, Fehler, Zeitüberschreitung), nimmt der Aufrufer die Qt-Lösung (Toast bzw.
QMessageBox). Das Tool stürzt deswegen nie ab.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROFI_THEME = Path(__file__).resolve().parent / "rofi" / "annotate.rasi"
ROFI_COLORS = Path.home() / ".config" / "rofi" / "colors.rasi"
NOT_AVAILABLE = object()  # Rückgabe von ask(), wenn rofi nicht benutzbar ist

_last_notification_id = None  # gleiche Benachrichtigung ersetzen statt neue stapeln


def _headless():
    """Ohne echten Bildschirm (Tests mit QT_QPA_PLATFORM=offscreen) nie externe Fenster
    oder Benachrichtigungen auf dem Desktop erzeugen."""
    return os.environ.get("QT_QPA_PLATFORM") == "offscreen"


def notify(text, error=False, timeout_ms=3000):
    """Benachrichtigung über notify-send (dunst). Rückgabe: True, wenn sie raus ist."""
    global _last_notification_id
    if _headless() or not shutil.which("notify-send"):
        return False
    cmd = ["notify-send", "--app-name=annotate", "--print-id",
           f"--urgency={'critical' if error else 'normal'}", f"--expire-time={timeout_ms}"]
    if _last_notification_id:
        cmd.append(f"--replace-id={_last_notification_id}")
    cmd += ["annotate", text]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[notify] notify-send fehlgeschlagen: {e}", file=sys.stderr)
        return False
    _last_notification_id = result.stdout.strip() or None
    return True


def ask(question, choices, theme=None):
    """Auswahl per rofi -dmenu. Rückgabe: Index der Wahl, None bei Esc/Abbruch,
    NOT_AVAILABLE wenn rofi fehlt oder nicht startet (dann Qt-Dialog nehmen).

    Wichtig: Ein Keyboard-Grab des eigenen Fensters muss vorher freigegeben sein,
    sonst bekommt rofi keine Tasten (siehe Canvas.ask).
    """
    if _headless() or not shutil.which("rofi"):
        return NOT_AVAILABLE
    theme = Path(theme).expanduser() if theme else ROFI_THEME
    # -i: Groß/klein egal, -matching fuzzy: "vw" findet "Verwerfen", "ab" findet "Abbrechen"
    cmd = ["rofi", "-dmenu", "-i", "-matching", "fuzzy", "-no-custom", "-format", "i",
           "-p", "", "-mesg", question]
    if theme.is_file():
        cmd += ["-theme", str(theme)]
        if ROFI_COLORS.is_file():  # eigene Farben zusätzlich laden, falls vorhanden
            cmd += ["-theme-str", f'@import "{ROFI_COLORS}"']
    try:
        result = subprocess.run(cmd, input="\n".join(choices), capture_output=True,
                                text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[notify] rofi fehlgeschlagen: {e}", file=sys.stderr)
        return NOT_AVAILABLE
    if result.returncode == 1:  # Esc
        return None
    try:
        index = int(result.stdout.strip())
    except ValueError:
        print(f"[notify] rofi: unerwartete Ausgabe {result.stdout!r} {result.stderr.strip()!r}",
              file=sys.stderr)
        return NOT_AVAILABLE
    return index if 0 <= index < len(choices) else None
