"""AFTER: the same policy, enforced at the sink (the shape of the 1.10.3 fix, PR #14036).

1. Toy model: `launch_stdio` calls the policy itself, so every way in is covered.
2. The real validator from lfx 1.10.3 on sample configs (real_validator.py).
Run: python3 fix.py
"""

import tempfile
from pathlib import Path

from toy_app import run_all

if __name__ == "__main__":
    print("AFTER (toy): policy at the sink")
    with tempfile.TemporaryDirectory() as d:
        run_all(validate_at_sink=True, workdir=Path(d))
    try:
        from real_validator import run

        print()
        run()
    except Exception as e:
        print(f"\n(real validator skipped: {e}; run wheels.py once)")
