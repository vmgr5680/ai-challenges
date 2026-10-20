"""BEFORE: the check sits only at the REST door (the shape of Langflow 1.9.0 to 1.10.2).

Toy model (see toy_app.py), plus the real-release check on the downloaded wheels.
Run: python3 reproduce.py
"""

import tempfile
from pathlib import Path

from toy_app import run_all

if __name__ == "__main__":
    print("BEFORE (toy): policy at the door only")
    with tempfile.TemporaryDirectory() as d:
        run_all(validate_at_sink=False, workdir=Path(d))
    try:
        from check_releases import report

        print("\nReal releases (source read from the wheels, nothing executed):")
        report()
    except Exception as e:  # offline and no cached wheels
        print(f"\n(real-release check skipped: {e}; run wheels.py once)")
