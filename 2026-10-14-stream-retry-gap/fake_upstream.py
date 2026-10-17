"""A local fake model server that drops the first N streams before the first event.

Stdlib only. It answers three streaming routes:

- POST .../chat/completions                 (OpenAI-compatible SSE)
- POST .../messages                         (Anthropic Messages SSE)
- POST ...:streamGenerateContent?alt=sse    (Google GenAI SSE)

For the first ``drops`` streaming requests it sends ``200 OK`` with SSE headers
and chunked transfer encoding, then closes the socket before the first chunk.
That is the failure in LiteLLM issues #44238 and #45457: the client has a
successful status line, and the body read fails with "Connection closed".
Every later request gets a short, valid stream.

Nothing here talks to a real provider. Bind is 127.0.0.1 only.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPENAI_STREAM = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":0,"model":"fake",'
    '"choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}\n\n'
    'data: {"id":"c1","object":"chat.completion.chunk","created":0,"model":"fake",'
    '"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
    "data: [DONE]\n\n"
)

ANTHROPIC_STREAM = "".join(
    f"event: {name}\ndata: {json.dumps(body)}\n\n"
    for name, body in [
        ("message_start", {"type": "message_start", "message": {
            "id": "m1", "type": "message", "role": "assistant", "model": "fake",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 3, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "Hello"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta",
                           "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 1}}),
        ("message_stop", {"type": "message_stop"}),
    ]
)

GEMINI_STREAM = (
    'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}],"role":"model"},'
    '"finishReason":"STOP","index":0}],'
    '"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":1,"totalTokenCount":4}}\n\n'
)


class FakeUpstream:
    """Counts streaming requests; drops the first ``drops`` of them before any event."""

    def __init__(self, drops: int = 1) -> None:
        self.drops = drops
        self.hits = 0
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # keep test output clean
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                with outer.lock:
                    outer.hits += 1
                    drop = outer.hits <= outer.drops
                if "streamGenerateContent" in self.path:
                    body = GEMINI_STREAM
                elif self.path.rstrip("/").endswith("/messages"):
                    body = ANTHROPIC_STREAM
                else:
                    body = OPENAI_STREAM
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                if drop:
                    # Status line and headers are out. Close before the first chunk.
                    self.wfile.flush()
                    self.close_connection = True
                    self.connection.shutdown(2)
                    return
                data = body.encode()
                self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n0\r\n\r\n")
                self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeUpstream":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
