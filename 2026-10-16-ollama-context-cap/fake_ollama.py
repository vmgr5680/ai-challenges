"""SIMULATED Ollama server for offline tests (stdlib only, no model).

It mimics the behaviour read from Ollama's source and measured on the real
server (see README and OUTPUTS.txt), not the model:

- /v1/chat/completions decodes only known OpenAI fields; `options`,
  `num_ctx` and other extras are ignored (Go JSON binding drops unknown keys).
- The working context is the model's num_ctx if set, else the server default.
- When the conversation is too long, whole messages are dropped from the
  front; system messages and the last message are always kept
  (server/prompt.go chatPrompt). The response is still 200.
- /api/chat honours options.num_ctx, and `truncate: false` returns 400.

Token count is simulated as len(text) // 3. The "model" answers with the
codename if the message that contains it survived, else "UNKNOWN".
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import CODENAME


def ntok(msgs):
    return sum(len(m.get("content") or "") // 3 + 4 for m in msgs)


def truncate(msgs, num_ctx):
    last = len(msgs) - 1
    for i in range(len(msgs)):
        system = [m for m in msgs[:i] if m["role"] == "system"]
        kept = system + msgs[i:]
        if ntok(kept) <= num_ctx or i == last:
            return kept
    return msgs


def answer(kept):
    return CODENAME if any(CODENAME in (m.get("content") or "") for m in kept[:-1]) else "UNKNOWN"


class FakeOllama:
    def __init__(self, default_ctx=4096):
        self.default_ctx = default_ctx
        self.model_ctx: dict[str, int] = {}
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                msgs = body.get("messages", [])
                model = body.get("model")
                if self.path == "/v1/chat/completions":
                    ctx = fake.model_ctx.get(model, fake.default_ctx)   # extras ignored
                    kept = truncate(msgs, ctx)
                    return self._send(200, {
                        "choices": [{"message": {"role": "assistant", "content": answer(kept)},
                                     "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": ntok(kept), "completion_tokens": 1},
                    })
                if self.path == "/api/chat":
                    opts = body.get("options") or {}
                    ctx = opts.get("num_ctx") or fake.model_ctx.get(model, fake.default_ctx)
                    if body.get("truncate") is False and ntok(msgs) > ctx:
                        return self._send(400, {"error": (
                            f"request ({ntok(msgs)} tokens) exceeds the available context "
                            f"size ({ctx} tokens), try increasing it")})
                    kept = truncate(msgs, ctx)
                    return self._send(200, {"message": {"role": "assistant", "content": answer(kept)},
                                            "prompt_eval_count": ntok(kept)})
                if self.path == "/api/create":
                    fake.model_ctx[body["model"]] = body["parameters"]["num_ctx"]
                    return self._send(200, {"status": "success"})
                self._send(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
