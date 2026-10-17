"""Run: python3 -m unittest discover -s tests -v   (from the issue folder)

Tests marked "real release" need the two venvs from setup_venvs.sh and are
skipped without them; the guard and detector tests are standard library only.
"""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import detect  # noqa: E402
from common import AFFECTED, FIXED, INJECTED, have_venv, run_bundled_cli, sdk_argv  # noqa: E402
from fix import safe_resume_id  # noqa: E402

MINE = "8f8b1c0e-2b1e-4a3f-9c2d-5e6f7a8b9c0d"
THEIRS = "550e8400-e29b-41d4-a716-446655440000"
OWNERS = {MINE: "alice", THEIRS: "bob"}


@unittest.skipUnless(have_venv(AFFECTED), "real release venv missing; run setup_venvs.sh")
class TestBugOnAffectedRelease(unittest.TestCase):
    def test_dash_value_becomes_standalone_token(self):
        argv = sdk_argv(AFFECTED, INJECTED)
        self.assertIn("--resume", argv)
        self.assertIn(INJECTED, argv)  # the "session ID" is its own argv token

    def test_bundled_cli_runs_the_injected_flag(self):
        code, out = run_bundled_cli(AFFECTED, ["--resume", INJECTED, "-p", "hi"])
        self.assertEqual(code, 0)
        self.assertIn("(Claude Code)", out)  # --version ran; no session was resumed


@unittest.skipUnless(have_venv(FIXED), "real release venv missing; run setup_venvs.sh")
class TestFixOnFixedRelease(unittest.TestCase):
    def test_value_bound_with_equals(self):
        argv = sdk_argv(FIXED, INJECTED)
        self.assertIn(f"--resume={INJECTED}", argv)
        self.assertNotIn(INJECTED, argv)
        self.assertNotIn("--resume", argv)

    def test_bundled_cli_rejects_value(self):
        code, out = run_bundled_cli(FIXED, [f"--resume={INJECTED}", "-p", "hi"])
        self.assertNotEqual(code, 0)
        self.assertIn("is not a UUID", out)

    def test_normal_uuid_unchanged(self):
        self.assertIn(f"--resume={MINE}", sdk_argv(FIXED, MINE))


class TestGuard(unittest.TestCase):
    def test_rejects_flags_and_titles(self):
        for raw in [INJECTED, "-r", "--mcp-config", "release-notes", "", f"{MINE} -r"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                safe_resume_id(raw, "alice", OWNERS)

    def test_rejects_other_users_session(self):
        with self.assertRaises(PermissionError):
            safe_resume_id(THEIRS, "alice", OWNERS)

    def test_accepts_own_session_canonicalised(self):
        self.assertEqual(safe_resume_id(MINE.upper(), "alice", OWNERS), MINE)


class TestDetect(unittest.TestCase):
    def run_detect(self, files: dict[str, str]) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            buf = io.StringIO()
            with redirect_stdout(buf):
                found = detect.scan(root)
            return found, buf.getvalue()

    def test_flags_old_python_and_npm(self):
        found, out = self.run_detect({
            "venv/lib/site-packages/claude_agent_sdk-0.2.120.dist-info/METADATA": "",
            "node_modules/@anthropic-ai/claude-agent-sdk/package.json": '{"version": "0.3.207"}',
        })
        self.assertEqual(found, 2)
        self.assertIn("no advisory exists for npm", out)

    def test_fixed_versions_pass(self):
        found, _ = self.run_detect({
            "venv/lib/site-packages/claude_agent_sdk-0.2.168.dist-info/METADATA": "",
            "node_modules/@anthropic-ai/claude-agent-sdk/package.json": '{"version": "0.3.302"}',
        })
        self.assertEqual(found, 0)

    def test_flags_untrusted_call_sites_not_literals(self):
        _, out = self.run_detect({
            "app.py": "opts = ClaudeAgentOptions(resume=body['sid'], session_id='fixed')\n",
            "app.ts": "const o = { resume: req.sessionId, sessionId: 'x' };\n",
        })
        self.assertIn("app.py:1  resume = body['sid']", out)
        self.assertIn("app.ts:1  resume = req.sessionId", out)
        self.assertNotIn("session_id = ", out)
        self.assertNotIn("sessionId = ", out)


if __name__ == "__main__":
    unittest.main()
