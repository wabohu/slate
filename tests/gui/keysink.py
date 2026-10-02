#!/usr/bin/env python3
"""Test window for the GUI tests: an input field that writes everything typed into a file.

Stands in for your terminal: if keys arrive here, the window has the
focus. The window title "keysink" makes it findable via xdotool.

    python tests/gui/keysink.py /path/to/output.txt
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
