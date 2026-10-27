"""Tests: prove the bug, prove the fix, check the detector and the guard.

Run from the issue folder:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import detect  # noqa: E402
import gateway  # noqa: E402
import servers  # noqa: E402
import session  # noqa: E402
from roundtrip_guard import lost_fields  # noqa: E402


def total(rows):
    return sum(r["cost"] for r in rows)


class Bug(unittest.TestCase):
    def test_typed_gateway_drops_marker(self):
        body = session.request_for_turn([], "q")
        self.assertIn("cache_control", body["system"][0])
        self.assertNotIn("cache_control", gateway.translate_typed(body)["system"][0])

    def test_typed_gateway_never_reads_cache(self):
        rows = session.run(gateway.translate_typed)
        self.assertEqual(sum(r["cache_read_input_tokens"] for r in rows), 0)
        self.assertGreater(total(rows), 4 * total(session.run(gateway.passthrough)))

    def test_top_level_marker_dropped(self):
        body = {**session.request_for_turn([], "q"), "cache_control": {"type": "ephemeral"}}
        self.assertNotIn("cache_control", gateway.translate_typed(body))


class Fix(unittest.TestCase):
    def test_preserving_matches_direct(self):
        self.assertEqual(session.run(gateway.translate_preserving), session.run(gateway.passthrough))

    def test_second_turn_reads_cache(self):
        rows = session.run(gateway.translate_preserving, turns=2)
        self.assertGreater(rows[1]["cache_read_input_tokens"], 0)


class Guard(unittest.TestCase):
    def test_guard_flags_typed_and_passes_fixed(self):
        body = {**session.request_for_turn([], "q"), "cache_control": {"type": "ephemeral"}}
        self.assertIn("system.0.cache_control.type", lost_fields(body, gateway.translate_typed(body)))
        self.assertEqual(lost_fields(body, gateway.translate_preserving(body)), [])
        self.assertEqual(lost_fields(body, gateway.passthrough(body)), [])


class Detect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = servers.start_all(base=18701)

    @classmethod
    def tearDownClass(cls):
        for s in cls.srv:
            s.shutdown()

    def _probe(self, port):
        with redirect_stdout(io.StringIO()):
            return detect.probe(f"http://127.0.0.1:{port}/v1/messages", {}, "claude-example")

    def test_probe_direct_ok(self):
        self.assertEqual(self._probe(18701), 0)

    def test_probe_typed_gateway_flags(self):
        self.assertEqual(self._probe(18702), 1)

    def test_probe_fixed_gateway_ok(self):
        self.assertEqual(self._probe(18703), 0)

    def test_scan(self):
        bad = [{"usage": {"input_tokens": 5000, "cache_read_input_tokens": 0}}] * 3
        good = bad + [{"usage": {"input_tokens": 10, "cache_read_input_tokens": 4990}}]
        for rows, want in ((bad, 1), (good, 0)):
            with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
                f.write("\n".join(json.dumps(r) for r in rows))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(detect.scan(f.name), want)
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
