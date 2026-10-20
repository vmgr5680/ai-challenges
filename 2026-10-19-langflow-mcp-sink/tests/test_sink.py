"""Run: python3 -m unittest discover -s tests -v   (from the issue folder)

Toy and detector tests are standard library only. Tests marked "real release" read the
downloaded wheels (python3 wheels.py) and are skipped without them.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import detect  # noqa: E402
from toy_app import run_all  # noqa: E402
from wheels import AFFECTED, FIXED, have_wheels, wheel_dir  # noqa: E402


def quiet(fn, *a, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


class TestToyBug(unittest.TestCase):
    def test_door_only_lets_flow_and_tweak_through(self):
        with tempfile.TemporaryDirectory() as d:
            r = quiet(run_all, validate_at_sink=False, workdir=Path(d))
        self.assertTrue(r["api"].startswith("rejected"))
        self.assertEqual(r["flow"], "launched")
        self.assertEqual(r["tweak"], "launched")


class TestToyFix(unittest.TestCase):
    def test_sink_check_blocks_every_way_in(self):
        with tempfile.TemporaryDirectory() as d:
            r = quiet(run_all, validate_at_sink=True, workdir=Path(d))
        for way in ("api", "flow", "tweak"):
            self.assertTrue(r[way].startswith("rejected"), way)

    def test_sink_check_keeps_allowed_servers_working(self):
        with tempfile.TemporaryDirectory() as d:
            r = quiet(run_all, validate_at_sink=True, workdir=Path(d))
        self.assertEqual(r["good"], "launched")


class TestDetect(unittest.TestCase):
    def test_version_ranges(self):
        self.assertTrue(detect.affected("langflow", "1.1.2"))
        self.assertTrue(detect.affected("langflow", "1.10.2"))
        self.assertTrue(detect.affected("langflow", "1.10.3rc0"))
        self.assertFalse(detect.affected("langflow", "1.10.3"))
        self.assertFalse(detect.affected("langflow", "1.11.0"))
        self.assertFalse(detect.affected("langflow", "1.1.1"))
        self.assertTrue(detect.affected("lfx", "0.4.6"))

    def test_flags_planted_flow_and_passes_clean_one(self):
        flags = quiet(detect.scan_flows, HERE / "examples")
        self.assertEqual(len(flags), 1)
        self.assertIn("flow_planted.json", flags[0])

    def test_flags_inline_code_and_wrappers(self):
        self.assertIsNotNone(detect.judge({"command": "python3", "args": ["-c", "x"]}))
        self.assertIsNotNone(detect.judge({"command": "bash", "args": ["-c", "uvx x"]}))
        self.assertIsNone(detect.judge({"command": "/usr/bin/node", "args": ["server.js"]}))

    def test_scan_handles_server_config_files(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "servers.json").write_text(json.dumps({"mcpServers": {"a": {"command": "curl", "args": []}}}))
            self.assertEqual(len(quiet(detect.scan_flows, Path(d))), 1)


@unittest.skipUnless(have_wheels(), "wheels missing; run python3 wheels.py")
class TestRealReleases(unittest.TestCase):
    def test_last_affected_validates_at_door_not_sink(self):
        from check_releases import door_has_allowlist, sink_validates

        self.assertTrue(door_has_allowlist(wheel_dir("langflow-base", AFFECTED["langflow-base"])))
        self.assertFalse(sink_validates(wheel_dir("lfx", AFFECTED["lfx"])))

    def test_first_fixed_validates_at_sink(self):
        from check_releases import sink_validates

        self.assertTrue(sink_validates(wheel_dir("lfx", FIXED["lfx"])))

    def test_real_validator_verdicts(self):
        from real_validator import run

        verdicts = dict(quiet(run))
        self.assertTrue(verdicts["touch /tmp/marker"].startswith("REJECTED"))
        self.assertTrue(verdicts["python3 -c print('hi')"].startswith("REJECTED"))
        self.assertEqual(verdicts["uvx some-unknown-package"], "allowed")


if __name__ == "__main__":
    unittest.main()
