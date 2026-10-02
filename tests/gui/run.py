#!/usr/bin/env python3
"""All GUI scenarios (tests/gui/test_*.py) one after another, each in its own X server.

    python tests/gui/run.py

Exit code 0 = all ok. Screenshots: tests/gui/out/<scenario>/.
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
print("All GUI scenarios OK." if not failed else f"Failed: {', '.join(failed)}")
sys.exit(1 if failed else 0)
