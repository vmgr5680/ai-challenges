"""Run from the issue folder:  python3 -m unittest discover -s tests -v

Each test runs the scenarios inside the venv for one pinned release (see README:
`make venvs`), so the BEFORE and AFTER claims are checked against real releases.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from local_guard import content_type_is_json, host_is_local  # noqa: E402

SNIPPET = """
import json, sys
sys.path.insert(0, {here!r})
import scenarios
from local_guard import LocalOnlyGuard
wrap = LocalOnlyGuard if {guard!r} else None
print(json.dumps([r['tool_ran'] for r in scenarios.run_scenarios(wrap=wrap)]))
"""


def tool_ran(release: str, guard: bool = False) -> list[bool]:
    py = HERE / f'.venv-{release}' / 'bin' / 'python'
    if not py.exists():
        raise unittest.SkipTest(f'{py} missing; create the venvs first (see README)')
    out = subprocess.run([str(py), '-c', SNIPPET.format(here=str(HERE), guard=guard)],
                         capture_output=True, text=True, check=True, cwd=HERE).stdout
    return json.loads(out.strip().splitlines()[-1])


class BugReproduces(unittest.TestCase):
    def test_affected_release_lets_both_web_pages_run_the_tool(self):
        self.assertEqual(tool_ran('2.27.1'), [True, True, True])

    def test_first_fix_alone_leaves_dns_rebinding_open(self):
        self.assertEqual(tool_ran('2.28.0'), [True, False, True])


class FixWorks(unittest.TestCase):
    def test_fixed_release_blocks_both_and_keeps_own_tab(self):
        self.assertEqual(tool_ran('2.30.0'), [True, False, False])

    def test_guard_on_affected_release_blocks_both_and_keeps_own_tab(self):
        self.assertEqual(tool_ran('2.27.1', guard=True), [True, False, False])


class GuardUnits(unittest.TestCase):
    def test_local_hosts_accepted(self):
        for h in ['127.0.0.1:7932', 'localhost:7932', '[::1]:7932', 'app.localhost', '192.168.1.5', 'localhost.']:
            self.assertTrue(host_is_local(h), h)

    def test_foreign_and_tricky_hosts_rejected(self):
        for h in ['attacker.example:7932', 'evil.example@127.0.0.1', 'localhost.evil.example', '', 'localhost..']:
            self.assertFalse(host_is_local(h), h)

    def test_allowed_host_list(self):
        self.assertTrue(host_is_local('ui.example.com', ('ui.example.com',)))

    def test_content_type(self):
        self.assertTrue(content_type_is_json('Application/JSON; charset=utf-8'))
        for ct in ['text/plain', 'multipart/form-data; boundary=x', 'application/x-www-form-urlencoded', '']:
            self.assertFalse(content_type_is_json(ct), ct)


if __name__ == '__main__':
    unittest.main()
