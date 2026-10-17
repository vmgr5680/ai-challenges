"""End-to-end check through the LiteLLM proxy server (the setup in issue #45457).

Starts a fake upstream, starts `litellm --config` pointed at it (num_retries: 2),
then streams one chat completion through the proxy with the OpenAI Python SDK,
first plainly and then wrapped in stream_guard.first_chunk_retry().

    .venv-<ver>/bin/python proxy_probe.py "<label>"

Everything binds to 127.0.0.1. Needs litellm[proxy] in the venv.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from openai import AsyncOpenAI

from fake_upstream import FakeUpstream
from stream_guard import first_chunk_retry

CONFIG = """model_list:
  - model_name: chat
    litellm_params:
      model: openai/fake
      api_base: {base}/v1
      api_key: sk-fake
  - model_name: messages
    litellm_params:
      model: anthropic/fake
      api_base: {base}
      api_key: sk-fake
  - model_name: genai
    litellm_params:
      model: gemini/fake
      api_base: {base}
      api_key: fake
router_settings:
  num_retries: 2
  retry_after: 0
litellm_settings:
  telemetry: false
general_settings:
  master_key: sk-local-test
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(url: str, seconds: float = 90) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    raise RuntimeError("proxy did not start")


async def _stream_once(client: AsyncOpenAI) -> str:
    s = await client.chat.completions.create(model="chat", stream=True,
                                             messages=[{"role": "user", "content": "hi"}])
    out = []
    async for chunk in s:
        if chunk.choices and chunk.choices[0].delta.content:
            out.append(chunk.choices[0].delta.content)
    return "".join(out)


async def _guarded(client: AsyncOpenAI) -> str:
    async def open_stream():
        return await client.chat.completions.create(model="chat", stream=True,
                                                    messages=[{"role": "user", "content": "hi"}])
    out = []
    async for chunk in await first_chunk_retry(open_stream, retries=2):
        if chunk.choices and chunk.choices[0].delta.content:
            out.append(chunk.choices[0].delta.content)
    return "".join(out)


RAW = {
    "/chat/completions": ("/v1/chat/completions",
                          {"model": "chat", "stream": True, "messages": [{"role": "user", "content": "hi"}]}),
    "/v1/messages": ("/v1/messages",
                     {"model": "messages", "stream": True, "max_tokens": 16,
                      "messages": [{"role": "user", "content": "hi"}]}),
    "streamGenerateContent": ("/v1beta/models/genai:streamGenerateContent?alt=sse",
                              {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}),
}


def _raw(port: int, path: str, body: dict) -> str:
    """One HTTP request, no client retries: what does the proxy actually answer?"""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer sk-local-test"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status, text = resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode(errors="replace")
    if "Hello" in text:
        what = "stream completed: got 'Hello'"
    elif status == 200 and "error" in text.lower():
        what = "an error event inside a 200 stream"
    elif status >= 400:
        what = "an HTTP error (a client can retry this)"
    else:
        what = "an empty stream"
    return f"HTTP {status}, {what}"


class _Proxy:
    def __init__(self, base: str) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        cfg = Path(self.tmp.name) / "config.yaml"
        cfg.write_text(CONFIG.format(base=base))
        self.port = _free_port()
        exe = Path(sys.executable).with_name("litellm")
        env = dict(os.environ, LITELLM_LOG="ERROR", LITELLM_TELEMETRY="False")
        self.proc = subprocess.Popen([str(exe), "--config", str(cfg), "--host", "127.0.0.1", "--port", str(self.port)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        _wait(f"http://127.0.0.1:{self.port}/health/liveliness")

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=20)
        self.tmp.cleanup()


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    from importlib.metadata import version
    print(f"litellm proxy {version('litellm')}  {label}  (router num_retries: 2)")
    print(" raw HTTP client, no client-side retries:")
    for name, (path, body) in RAW.items():
        with FakeUpstream(drops=1) as up:
            proxy = _Proxy(up.base)
            try:
                seen = _raw(proxy.port, path, body)
            finally:
                proxy.close()
            print(f"  {name:24s} upstream attempts={up.hits}  client saw: {seen}")
    print(" OpenAI SDK client on /chat/completions:")
    for mode, sdk_retries in (("SDK default retries", 2), ("SDK retries off", 0),
                              ("retries off + guard", 0)):
        with FakeUpstream(drops=1) as up:
            proxy = _Proxy(up.base)
            try:
                client = AsyncOpenAI(base_url=f"http://127.0.0.1:{proxy.port}", api_key="sk-local-test",
                                     max_retries=sdk_retries)
                try:
                    text = asyncio.run(_guarded(client) if "guard" in mode else _stream_once(client))
                    seen = f"got {text!r}" if text else "stream ended with no content"
                except Exception as e:  # noqa: BLE001
                    seen = f"{type(e).__name__} (HTTP {getattr(e, 'status_code', '?')})"
            finally:
                proxy.close()
            print(f"  {mode:24s} upstream attempts={up.hits}  client saw: {seen}")


if __name__ == "__main__":
    main()
