"""Tests: the bug (a .pth line runs at every start) and the fix (outside cleanup, pins, baseline guard).

    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import detect  # noqa: E402
import fix  # noqa: E402
import reproduce  # noqa: E402


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a)


class Bug(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.venv, cls.py = reproduce.setup_hooked("venv-test-bug")
        cls.version = reproduce.installed_version(cls.py)
        cls.results = dict(reproduce.run_starts(cls.py, cls.venv))

    def test_unpinned_install_takes_newest(self):
        self.assertEqual(self.version, "0.0.2")

    def test_plain_start_runs_hook_without_import(self):
        self.assertEqual(self.results["python -c pass"], 1)

    def test_pip_and_isolated_mode_run_hook(self):
        self.assertEqual(self.results["python -m pip --version"], 1)
        self.assertEqual(self.results["python -I -c pass"], 1)

    def test_dash_S_skips_hook(self):
        self.assertEqual(self.results["python -S -c pass"], 0)

    def test_uninstall_runs_hook_first(self):
        self.assertEqual(self.results["pip uninstall -y toy-hook"], 1)


class Detect(unittest.TestCase):
    def make_sp(self, files, dist=None):
        d = tempfile.mkdtemp()
        sp = os.path.join(d, "lib", "python3.99", "site-packages")
        os.makedirs(sp)
        for name, text in files.items():
            with open(os.path.join(sp, name), "w") as f:
                f.write(text)
        if dist:
            info = os.path.join(sp, f"{dist}.dist-info")
            os.makedirs(info)
            with open(os.path.join(info, "RECORD"), "w") as f:
                f.write("".join(f"{n},,\n" for n in files))
        return d, sp

    def test_path_only_pth_is_not_a_hook(self):
        _, sp = self.make_sp({"mypkg.pth": "/some/src\n"})
        self.assertEqual(detect.scan(sp)[0], [])

    def test_real_ioc_hash_of_cook_pth(self):
        # OSV MAL-2026-2144 lists sha256 7f19...2bdb for cook.pth; it is these 12 bytes.
        _, sp = self.make_sp({"cook.pth": "import cook\n"}, dist="litellm-1.107.0")
        hooks, bad = detect.scan(sp)
        self.assertEqual(hooks[0]["owner"], "litellm 1.107.0")
        self.assertTrue(any("hash matches cook.pth" in b for b in bad))
        self.assertTrue(any("litellm 1.107.0 installed" in b for b in bad))

    def test_unowned_sitecustomize_reported(self):
        _, sp = self.make_sp({"sitecustomize.py": "pass\n"})
        self.assertEqual(detect.scan(sp)[0][0]["owner"], "UNOWNED")

    def test_lockfile_pin_flagged(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("litellm==1.107.0\nhttpx==0.28.1\n")
        self.assertEqual(len(quiet(detect.scan_locks, [f.name])), 1)

    def test_exit_status(self):
        venv, _ = self.make_sp({"cook.pth": "import cook\n"})
        self.assertEqual(quiet(detect.main, [venv]), 1)


class Fix(unittest.TestCase):
    def test_cleanup_from_outside_stops_hook(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fix.step1_cleanup()
        self.assertIn("next start ran the hook: no", out.getvalue())

    def test_pinned_install_then_baseline_guard(self):
        venv, py, reqs = quiet(fix.step2_pinned)
        self.assertEqual(reproduce.installed_version(py), "0.0.1")
        self.assertEqual(reproduce.marker_count(venv), 0)
        self.assertEqual(quiet(fix.step3_guard, venv, py), 2)
        with open(os.path.join(reproduce.DEMO, "startup-hooks.json")) as f:
            base = json.load(f)
        self.assertEqual(base, [])
        self.assertNotEqual(quiet(fix.step4_swapped, reqs), 0)


if __name__ == "__main__":
    unittest.main()
