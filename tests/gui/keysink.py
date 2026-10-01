#!/usr/bin/env python3
"""Testfenster für die GUI-Tests: ein Eingabefeld, das alles Getippte in eine Datei schreibt.

Steht stellvertretend für dein Terminal: Kommen Tasten hier an, hat das Fenster den
Fokus. Der Fenstertitel "keysink" macht es per xdotool auffindbar.

    python tests/gui/keysink.py /pfad/zur/ausgabe.txt
"""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QLineEdit

app = QApplication(sys.argv[:1])
out = Path(sys.argv[1])
out.write_text("")
field = QLineEdit()
field.setWindowTitle("keysink")
field.textChanged.connect(out.write_text)
field.show()
sys.exit(app.exec())
