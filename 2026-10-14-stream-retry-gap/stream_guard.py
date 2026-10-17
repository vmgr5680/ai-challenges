"""Copyable, caller-side fix for any async LLM stream (LiteLLM, an SDK, raw httpx).

`first_chunk_retry(open_stream, retries)` calls ``open_stream()`` and reads the
first chunk inside its own retry loop. If the stream fails before that chunk,
nothing has reached your user yet, so it opens a new stream. Once the first
chunk arrives the stream is committed: it is replayed and later errors
propagate unchanged (retrying then would duplicate text the user already saw).

Stdlib only. Works with any zero-argument coroutine function that returns an
async iterator.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

RETRYABLE = (ConnectionError, TimeoutError, OSError)


def _is_retryable(exc: BaseException) -> bool:
    # httpx.ReadError / litellm.APIConnectionError are not ConnectionError subclasses,
    # so match on name as well as type to stay dependency-free.
    names = {c.__name__ for c in type(exc).__mro__}
    return isinstance(exc, RETRYABLE) or bool(
        names & {"ReadError", "RemoteProtocolError", "APIConnectionError", "ServiceUnavailableError",
                 "InternalServerError", "RateLimitError", "MidStreamFallbackError"}
    )


async def first_chunk_retry(
    open_stream: Callable[[], Awaitable[AsyncIterator[Any]]],
    retries: int = 2,
    backoff_s: float = 0.0,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> AsyncIterator[Any]:
    for attempt in range(retries + 1):
        try:
            stream = await open_stream()
            iterator = stream.__aiter__()
            first = await iterator.__anext__()
        except StopAsyncIteration:
            return _empty()
        except Exception as exc:  # noqa: BLE001
            if attempt == retries or not _is_retryable(exc):
                raise
            if on_retry:
                on_retry(attempt + 1, exc)
            await asyncio.sleep(backoff_s * (2 ** attempt))
            continue
        return _replay(first, iterator)
    raise AssertionError("unreachable")


async def _replay(first: Any, rest: AsyncIterator[Any]) -> AsyncIterator[Any]:
    yield first
    async for item in rest:
        yield item


async def _empty() -> AsyncIterator[Any]:
    return
    yield  # pragma: no cover
