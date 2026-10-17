"""AFTER, two ways.

Run under the fixed release to see the official fix:

    .venv-2.30.0/bin/python fix.py

Run under the affected release to see `LocalOnlyGuard` close both holes without upgrading:

    .venv-2.27.1/bin/python fix.py --guard
"""

import sys

from local_guard import LocalOnlyGuard
from scenarios import print_report, run_scenarios

if __name__ == '__main__':
    if '--guard' in sys.argv:
        print_report('AFTER (LocalOnlyGuard)', run_scenarios(wrap=LocalOnlyGuard))
    else:
        print_report('AFTER (upgrade)', run_scenarios())
