"""BEFORE: run under an affected release (see README) to watch web pages drive the agent.

    .venv-2.27.1/bin/python reproduce.py
"""

from scenarios import print_report, run_scenarios

if __name__ == '__main__':
    print_report('BEFORE', run_scenarios())
