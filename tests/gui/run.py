#!/usr/bin/env python3
"""Alle GUI-Szenarien (tests/gui/test_*.py) nacheinander, je in einem eigenen X-Server.

    python tests/gui/run.py

Rückgabewert 0 = alle ok. Bildschirmfotos: tests/gui/out/<szenario>/.
"""
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
failed = []
for scenario in sorted(here.glob("test_*.py")):
    print(f"=== {scenario.stem}", flush=True)
    if subprocess.run([sys.executable, str(scenario)]).returncode != 0:
        failed.append(scenario.stem)
    print(flush=True)
print("Alle GUI-Szenarien OK." if not failed else f"Fehlgeschlagen: {', '.join(failed)}")
sys.exit(1 if failed else 0)
