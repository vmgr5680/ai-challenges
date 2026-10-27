"""Local HTTP servers so detect.py can be run end to end without a real provider.

  python3 servers.py            # fake provider on :8701, typed (buggy) gateway on :8702,
                                # preserving (fixed) gateway on :8703
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gateway
from fake_anthropic import FakeAnthropic


def _handler(respond):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = json.dumps(respond(body)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass
    return H


def start(port: int, respond) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), _handler(respond))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def start_all(base: int = 8701):
    upstream = FakeAnthropic()
    return [
        start(base, upstream.messages),
        start(base + 1, lambda b: upstream.messages(gateway.translate_typed(b))),
        start(base + 2, lambda b: upstream.messages(gateway.translate_preserving(b))),
    ]


if __name__ == "__main__":
    import time
    start_all()
    print("provider :8701  typed gateway :8702  preserving gateway :8703  (Ctrl-C to stop)")
    while True:
        time.sleep(3600)
