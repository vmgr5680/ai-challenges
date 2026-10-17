"""Tests: the bug reproduces, the fix holds, the guard works on real LiteLLM.

    python3 -m unittest discover -s tests -v

The pinned-release tests run only if the matching venv exists (see README).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detect import scan  # noqa: E402
from pattern import (  # noqa: E402
    ScriptedUpstream, StreamDropped, consume, retry_open_only, retry_until_first_event,
)
from stream_guard import first_chunk_retry  # noqa: E402


class ToyModel(unittest.TestCase):
    def test_bug_reproduces_retry_wraps_open_only(self):
        up = ScriptedUpstream(["drop", "ok"])
        stream = retry_open_only(up, num_retries=2)
        with self.assertRaises(StreamDropped):
            consume(stream)
        self.assertEqual(up.attempts, 1)

    def test_fix_retries_until_first_event(self):
        up = ScriptedUpstream(["drop", "drop", "ok"])
        self.assertEqual(consume(retry_until_first_event(up, num_retries=2)), "Hello!")
        self.assertEqual(up.attempts, 3)

    def test_fix_respects_budget(self):
        up = ScriptedUpstream(["drop"] * 5)
        with self.assertRaises(StreamDropped):
            consume(retry_until_first_event(up, num_retries=2))
        self.assertEqual(up.attempts, 3)


class AsyncGuard(unittest.TestCase):
    def test_guard_retries_pre_first_chunk_drop(self):
        attempts = 0

        async def open_stream():
            nonlocal attempts
            attempts += 1
            fail = attempts == 1

            async def gen():
                if fail:
                    raise ConnectionError("Connection closed.")
                yield "Hello"
            return gen()

        async def run():
            return [c async for c in await first_chunk_retry(open_stream, retries=2)]

        self.assertEqual(asyncio.run(run()), ["Hello"])
        self.assertEqual(attempts, 2)

    def test_guard_does_not_retry_after_first_chunk(self):
        attempts = 0

        async def open_stream():
            nonlocal attempts
            attempts += 1

            async def gen():
                yield "Hel"
                raise ConnectionError("Connection closed.")
            return gen()

        async def run():
            return [c async for c in await first_chunk_retry(open_stream, retries=2)]

        with self.assertRaises(ConnectionError):
            asyncio.run(run())
        self.assertEqual(attempts, 1)

    def test_guard_does_not_retry_client_errors(self):
        attempts = 0

        async def open_stream():
            nonlocal attempts
            attempts += 1
            raise ValueError("400 bad request")

        with self.assertRaises(ValueError):
            asyncio.run(first_chunk_retry(open_stream, retries=2))
        self.assertEqual(attempts, 1)


class Detect(unittest.TestCase):
    def test_flags_unguarded_and_retry_only_config(self):
        found = "\n".join(scan([ROOT / "samples"]))
        self.assertIn("agent_unguarded.py", found)
        self.assertIn("proxy_config_retries_only.yaml", found)
        self.assertNotIn("agent_guarded.py", found)


def _venv(v: str) -> Path:
    return ROOT / f".venv-{v}" / "bin" / "python"


def _run(v: str, script: str) -> str:
    return subprocess.run([str(_venv(v)), script, "test"], cwd=ROOT, capture_output=True,
                          text=True, timeout=600).stdout


class PinnedReleases(unittest.TestCase):
    @unittest.skipUnless(_venv("1.105.1").exists(), "venv .venv-1.105.1 missing")
    def test_latest_stable_retries_no_route(self):
        out = _run("1.105.1", "litellm_probe.py")
        self.assertEqual(out.count("upstream attempts=1"), 3, out)

    @unittest.skipUnless(_venv("1.106.0rc2").exists(), "venv .venv-1.106.0rc2 missing")
    def test_rc_fixes_messages_only(self):
        out = _run("1.106.0rc2", "litellm_probe.py")
        line = next(l for l in out.splitlines() if "/v1/messages" in l)
        self.assertIn("upstream attempts=2", line)
        self.assertEqual(out.count("NOT retried"), 2, out)

    @unittest.skipUnless(_venv("1.105.1").exists(), "venv .venv-1.105.1 missing")
    def test_guard_fixes_all_routes_on_stable(self):
        out = _run("1.105.1", "litellm_guarded.py")
        self.assertEqual(out.count("got 'Hello'"), 3, out)


if __name__ == "__main__":
    unittest.main()
