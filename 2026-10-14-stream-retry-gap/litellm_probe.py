"""Run in a pinned LiteLLM venv. Sends one streaming request per route through
``litellm.Router`` (num_retries=2) at a fake upstream that drops the first
stream before its first event, and reports how many upstream attempts were made
and what the caller saw.

    .venv-<ver>/bin/python litellm_probe.py "<label>"

Offline: the only network peer is the local fake upstream on 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import os
import sys
import warnings

os.environ.setdefault("LITELLM_LOG", "CRITICAL")
warnings.filterwarnings("ignore")

import litellm  # noqa: E402
from litellm import Router  # noqa: E402

from fake_upstream import FakeUpstream  # noqa: E402

litellm.suppress_debug_info = True
litellm.telemetry = False


def _router(base: str) -> Router:
    return Router(
        model_list=[
            {"model_name": "chat", "litellm_params": {
                "model": "openai/fake", "api_base": base + "/v1", "api_key": "sk-fake"}},
            {"model_name": "messages", "litellm_params": {
                "model": "anthropic/fake", "api_base": base, "api_key": "sk-fake"}},
            {"model_name": "genai", "litellm_params": {
                "model": "gemini/fake", "api_base": base, "api_key": "fake"}},
        ],
        num_retries=2,
        retry_after=0,
    )


def _text(obj) -> str:
    s = obj.decode(errors="replace") if isinstance(obj, (bytes, bytearray)) else str(obj)
    return s


async def _drain(stream) -> str:
    out = []
    async for chunk in stream:
        out.append(_text(chunk))
    return "".join(out)


async def run_route(route: str) -> tuple[int, str]:
    with FakeUpstream(drops=1) as up:
        r = _router(up.base)
        try:
            if route == "chat":
                s = await r.acompletion(model="chat", messages=[{"role": "user", "content": "hi"}], stream=True)
            elif route == "messages":
                s = await r.aanthropic_messages(model="messages", max_tokens=16, stream=True,
                                                messages=[{"role": "user", "content": "hi"}])
            else:
                s = await r.agenerate_content_stream(model="genai", contents=[{"role": "user", "parts": [{"text": "hi"}]}])
            body = await _drain(s)
            if "Hello" in body:
                seen = "stream completed: got 'Hello'"
            elif "error" in body.lower():
                seen = "stream ended with an in-band error event"
            else:
                seen = "stream ended with no content"
        except Exception as e:  # noqa: BLE001
            seen = f"raised {type(e).__name__}"
        return up.hits, seen


async def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"litellm {getattr(litellm, '__version__', None) or _version()}  {label}")
    print("upstream drops the 1st stream before its first event; Router num_retries=2")
    for route, name in [("chat", "/chat/completions"), ("messages", "/v1/messages"),
                        ("genai", "streamGenerateContent")]:
        hits, seen = await run_route(route)
        verdict = "retried" if hits > 1 else "NOT retried"
        print(f"  {name:24s} upstream attempts={hits}  {verdict:12s} caller saw: {seen}")


def _version() -> str:
    from importlib.metadata import version
    return version("litellm")


if __name__ == "__main__":
    asyncio.run(main())
