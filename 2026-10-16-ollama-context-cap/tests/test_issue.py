"""Tests: the bug reproduces, the fixes hold, the guard catches the cut.

    python3 -m unittest discover -s tests -v

Offline tests use fake_ollama.py (simulated server behaviour, no model).
Live tests run only when OLLAMA_TEST_URL points at a real Ollama server
started with its default context and with OLLAMA_MODEL pulled.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common import CODENAME, build_conversation, post, v1_chat  # noqa: E402
from fake_ollama import FakeOllama  # noqa: E402
from guard import ContextTruncated, TruncationGuard  # noqa: E402

MODEL = "toy"
LONG = build_conversation(6)     # ~7k simulated tokens, over the 4096 default


class SimulatedServer(unittest.TestCase):
    def setUp(self):
        self.srv = FakeOllama(default_ctx=4096).__enter__()

    def tearDown(self):
        self.srv.__exit__()

    def test_bug_v1_drops_task_and_returns_200(self):
        status, body = v1_chat(LONG, model=MODEL, base_url=self.srv.url)
        self.assertEqual(status, 200)
        self.assertNotEqual(body["choices"][0]["message"]["content"], CODENAME)

    def test_bug_v1_ignores_num_ctx_in_body(self):
        _, plain = v1_chat(LONG, model=MODEL, base_url=self.srv.url)
        _, extra = v1_chat(LONG, model=MODEL, base_url=self.srv.url, options={"num_ctx": 16384})
        self.assertEqual(plain["usage"], extra["usage"])

    def test_fix_native_num_ctx_keeps_task(self):
        _, body = post("/api/chat", {"model": MODEL, "messages": LONG, "options": {"num_ctx": 16384}},
                       self.srv.url)
        self.assertEqual(body["message"]["content"], CODENAME)

    def test_fix_derived_model_works_on_v1(self):
        post("/api/create", {"model": "toy-16k", "from": MODEL, "parameters": {"num_ctx": 16384}}, self.srv.url)
        _, body = v1_chat(LONG, model="toy-16k", base_url=self.srv.url)
        self.assertEqual(body["choices"][0]["message"]["content"], CODENAME)

    def test_fix_truncate_false_fails_closed(self):
        status, body = post("/api/chat", {"model": MODEL, "messages": LONG, "truncate": False}, self.srv.url)
        self.assertEqual(status, 400)
        self.assertIn("exceeds the available context size", body["error"])

    def test_guard_raises_when_history_is_cut(self):
        guard = TruncationGuard()
        with self.assertRaises(ContextTruncated):
            for n in range(7):
                msgs = build_conversation(n)
                _, body = v1_chat(msgs, model=MODEL, base_url=self.srv.url)
                guard.check(msgs, body["usage"]["prompt_tokens"])


class GuardLogic(unittest.TestCase):
    def test_no_alarm_while_prompt_grows(self):
        g = TruncationGuard(context_length=4096)
        for n, toks in [(3, 77), (5, 962), (7, 1849)]:
            self.assertEqual(g.check([{}] * n, toks), [])

    def test_alarm_on_drop_measured_on_real_server(self):
        # numbers from OUTPUTS.txt (real Ollama, turns 4 -> 5)
        g = TruncationGuard()
        g.check([{}] * 12, 3631)
        with self.assertRaises(ContextTruncated):
            g.check([{}] * 14, 3607)

    def test_headroom_warning(self):
        g = TruncationGuard(context_length=4096, raise_on_truncation=False)
        self.assertTrue(g.check([{}] * 12, 3631)[0].startswith("near limit"))


@unittest.skipUnless(os.environ.get("OLLAMA_TEST_URL"), "set OLLAMA_TEST_URL for live tests")
class LiveOllama(unittest.TestCase):
    url = os.environ.get("OLLAMA_TEST_URL")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")

    def test_live_bug_v1_ignores_num_ctx(self):
        _, body = v1_chat(LONG, model=self.model, base_url=self.url, options={"num_ctx": 16384})
        self.assertLess(body["usage"]["prompt_tokens"], 4096)

    def test_live_fix_native_num_ctx(self):
        _, body = post("/api/chat", {"model": self.model, "messages": LONG, "stream": False,
                                     "options": {"num_ctx": 16384, "temperature": 0}}, self.url)
        self.assertGreater(body["prompt_eval_count"], 4096)
        self.assertIn(CODENAME, body["message"]["content"])

    def test_live_truncate_false_fails_closed(self):
        status, _ = post("/api/chat", {"model": self.model, "messages": LONG, "stream": False,
                                       "truncate": False}, self.url)
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
