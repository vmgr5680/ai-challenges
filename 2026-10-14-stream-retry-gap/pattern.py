"""The bug class, in 60 lines of stdlib: a retry wrapper that guards the wrong part
of a streaming call.

A streaming LLM call has two phases:

1. open: send the request, receive "200 OK" and the response headers.
2. read: pull events (tokens) from the body.

Most retry loops wrap phase 1, because that is the function call they can see.
A stream that dies after the headers but before the first event fails in
phase 2, after the retry loop has already counted a success.

`retry_open_only()` is the pre-fix shape (LiteLLM issues #44238, #45457).
`retry_until_first_event()` is the fix: read (and hold) the first event inside
the retry loop, then replay it. Before the first event reaches the caller,
nothing has been committed, so a retry is safe.

`ScriptedUpstream` is a fake model: each attempt either drops before its first
event or streams a short reply. No network.
"""

from __future__ import annotations

from collections.abc import Iterator


class StreamDropped(ConnectionError):
    """The upstream closed the connection while the body was being read."""


class ScriptedUpstream:
    """A fake model server. ``script`` says, per attempt, "drop" or "ok"."""

    def __init__(self, script: list[str]) -> None:
        self.script = list(script)
        self.attempts = 0

    def open_stream(self) -> Iterator[str]:
        """Phase 1 always 'succeeds' (200 OK). The returned iterator is phase 2."""
        outcome = self.script[min(self.attempts, len(self.script) - 1)]
        self.attempts += 1

        def body() -> Iterator[str]:
            if outcome == "drop":
                raise StreamDropped("Connection closed.")
            yield from ["Hel", "lo", "!"]

        return body()


def retry_open_only(upstream: ScriptedUpstream, num_retries: int = 2) -> Iterator[str]:
    """Pre-fix shape: retries cover opening the stream, not reading it."""
    for attempt in range(num_retries + 1):
        try:
            return upstream.open_stream()  # "success" as soon as headers arrive
        except ConnectionError:
            if attempt == num_retries:
                raise
    raise AssertionError("unreachable")


def retry_until_first_event(upstream: ScriptedUpstream, num_retries: int = 2) -> Iterator[str]:
    """Fix: the commit point is the first event, so read it inside the retry loop."""
    for attempt in range(num_retries + 1):
        stream = upstream.open_stream()
        try:
            first = next(stream)  # nothing has reached the caller yet: safe to retry
        except StopIteration:
            return iter(())
        except ConnectionError:
            if attempt == num_retries:
                raise
            continue
        return _replay(first, stream)  # committed: later errors propagate, no retry
    raise AssertionError("unreachable")


def _replay(first: str, rest: Iterator[str]) -> Iterator[str]:
    yield first
    yield from rest


def consume(stream: Iterator[str]) -> str:
    return "".join(stream)
