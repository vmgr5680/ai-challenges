"""AFTER, on real LiteLLM: the same three Router calls as litellm_probe.py, each
wrapped in stream_guard.first_chunk_retry(). Run in a pinned venv:

    .venv-<ver>/bin/python litellm_guarded.py "<label>"
"""

from __future__ import annotations

import asyncio
import sys

import litellm_probe as p
from fake_upstream import FakeUpstream
from stream_guard import first_chunk_retry


async def run_route(route: str) -> tuple[int, str]:
    with FakeUpstream(drops=1) as up:
        r = p._router(up.base)

        async def open_stream():
            if route == "chat":
                return await r.acompletion(model="chat", messages=[{"role": "user", "content": "hi"}], stream=True)
            if route == "messages":
                return await r.aanthropic_messages(model="messages", max_tokens=16, stream=True,
                                                   messages=[{"role": "user", "content": "hi"}])
            return await r.agenerate_content_stream(model="genai", contents=[{"role": "user", "parts": [{"text": "hi"}]}])

        try:
            body = await p._drain(await first_chunk_retry(open_stream, retries=2))
            seen = "stream completed: got 'Hello'" if "Hello" in body else "no content"
        except Exception as e:  # noqa: BLE001
            seen = f"raised {type(e).__name__}"
        return up.hits, seen


async def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"litellm {p._version()}  {label}  + first_chunk_retry(retries=2)")
    for route, name in [("chat", "/chat/completions"), ("messages", "/v1/messages"),
                        ("genai", "streamGenerateContent")]:
        hits, seen = await run_route(route)
        print(f"  {name:24s} upstream attempts={hits}  caller saw: {seen}")


if __name__ == "__main__":
    asyncio.run(main())
