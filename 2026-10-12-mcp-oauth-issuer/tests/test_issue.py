import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from detect import is_affected_version, scan_source  # noqa: E402
from pattern import run_scenarios  # noqa: E402


class PatternTests(unittest.TestCase):
    def test_bug_reproduces_check_skipped_when_discovery_empty(self):
        d = {x.scenario: x for x in run_scenarios(fixed=False)}
        self.assertEqual(d["discovery names an auth server"].outcome, "rejected")
        self.assertEqual(d["discovery returns nothing"].check, "skipped")
        self.assertEqual(d["discovery returns nothing"].outcome, "accepted")

    def test_fix_always_checks_and_rejects(self):
        for x in run_scenarios(fixed=True):
            self.assertEqual(x.check, "ran")
            self.assertEqual(x.outcome, "rejected")


class VersionTests(unittest.TestCase):
    def test_affected(self):
        for v in ["1.9.1", "1.29.1", "2.0.0a1", "2.0.0", "2.1.1"]:
            self.assertTrue(is_affected_version(v), v)

    def test_not_affected(self):
        for v in ["1.9.0", "1.8.0", "1.30.0", "2.2.0", "2.3.0", "3.0.0"]:
            self.assertFalse(is_affected_version(v), v)


class ScanTests(unittest.TestCase):
    def test_before_sample_flags_three_followups(self):
        f = scan_source(HERE / "samples" / "client_before.py")
        self.assertEqual(len(f), 3)
        self.assertTrue(any("without issuer=" in x for x in f))
        self.assertTrue(any("migrate" in x for x in f))
        self.assertTrue(any("clear stored client info" in x for x in f))

    def test_after_sample_is_clean(self):
        self.assertEqual(scan_source(HERE / "samples" / "client_after.py"), [])


class UpgradeTests(unittest.TestCase):
    """Runs warn_check.py in the pinned venvs (skipped if they were not created)."""

    def run_in(self, ver):
        import subprocess
        py = HERE / f".venv-{ver}" / "bin" / "python"
        if not py.exists():
            self.skipTest(f".venv-{ver} not created")
        return subprocess.run([str(py), "warn_check.py"], cwd=HERE, capture_output=True, text=True).stdout

    def test_affected_release_has_no_issuer_option(self):
        self.assertIn("accepts issuer=        : False", self.run_in("2.1.1"))

    def test_fixed_older_line_warning_is_hidden_but_guard_catches_it(self):
        out = self.run_in("1.30.0")
        self.assertIn("shown by default       : False", out)
        self.assertIn("fails the CI guard     : True", out)

    def test_fixed_current_line_warning_is_shown(self):
        out = self.run_in("2.2.0")
        self.assertIn("shown by default       : True", out)
        self.assertIn("fails the CI guard     : True", out)


if __name__ == "__main__":
    unittest.main()
