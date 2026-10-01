"""Fokus zurückgeben nach dem Screenshot-Overlay (herbstluftwm).

Das Overlay läuft am Window-Manager vorbei und holt sich den Tastaturfokus selbst
(activateWindow). Früher hatte danach kein Fenster mehr den Fokus, weil herbstluftwm
von diesem Fokuswechsel nichts mitbekommt und ihn beim Schließen nicht zurückgibt.
Darum gibt das Tool ihn beim Schließen selbst zurück: an das Fenster, das herbstluftwm
in diesem Moment als fokussiert führt. So passt es auch, wenn du per Hotkey inzwischen
den Tag oder das Fenster gewechselt hast.

Ohne herbstluftwm (herbstclient fehlt) oder ohne fokussiertes Fenster passiert nichts.
Ohne Bildschirm (Tests, QT_QPA_PLATFORM=offscreen) werden nie externe Programme gestartet.
"""
import os
import shutil
import subprocess
import sys


def _run(cmd):
    """Befehl ausführen, Ausgabe zurück; bei jedem Problem None."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[wm] {' '.join(cmd)} fehlgeschlagen: {e}", file=sys.stderr)
        return None
    return result.stdout.strip()


def focused_window():
    """X-Fenster-ID des Fensters, das herbstluftwm gerade fokussiert hat, sonst None."""
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or not shutil.which("herbstclient"):
        return None
    # Ohne fokussiertes Fenster (leerer Tag) gibt es das Attribut nicht -> Fehler, None
    try:
        result = subprocess.run(["herbstclient", "attr", "clients.focus.winid"],
                                capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    winid = result.stdout.strip()
    return winid if result.returncode == 0 and winid else None


def restore_focus():
    """Tastaturfokus an das von herbstluftwm fokussierte Fenster zurückgeben."""
    winid = focused_window()
    if winid is None:
        return
    if shutil.which("xdotool"):
        _run(["xdotool", "windowfocus", winid])  # setzt den X-Fokus direkt
    else:
        _run(["herbstclient", "jumpto", winid])
