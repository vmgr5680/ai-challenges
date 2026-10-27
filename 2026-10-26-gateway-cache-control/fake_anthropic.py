"""A fake Anthropic Messages endpoint that does prompt-cache accounting.

SIMULATED. It copies the documented rules of Anthropic prompt caching closely
enough to show the bug, not the real service:

  * the prompt is read in order tools -> system -> messages;
  * a block carrying "cache_control" is a breakpoint; a top-level
    "cache_control" puts one breakpoint on the last block ("automatic caching");
  * each breakpoint checks up to 20 earlier blocks for a prefix cached by an
    earlier request (so last turn's breakpoint is reused this turn);
  * a breakpoint whose prefix is shorter than MIN_CACHEABLE tokens is not cached,
    and no error is returned;
  * usage reports cache_read_input_tokens, cache_creation_input_tokens and
    input_tokens (tokens after the last breakpoint).

Tokens are counted as whitespace-separated words of the JSON. Real tokenizers
differ; the shape of the result does not.
Docs: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
"""

from __future__ import annotations

import copy
import hashlib
import json

MIN_CACHEABLE = 1024  # tokens; the real minimum depends on the model (512-4096)
LOOKBACK = 20  # blocks checked before each breakpoint for an earlier cache entry


def _tokens(block: dict) -> int:
    return len(json.dumps(block, sort_keys=True).split())


def _strip_marker(block: dict) -> dict:
    b = copy.deepcopy(block)
    b.pop("cache_control", None)
    return b


def flatten(body: dict) -> list[dict]:
    """Return the prompt as an ordered list of blocks (tools, system, messages)."""
    blocks: list[dict] = []
    for tool in body.get("tools", []):
        blocks.append(tool)
    system = body.get("system", [])
    if isinstance(system, str):
        system = [{"type": "text", "text": system}]
    blocks.extend(system)
    for msg in body.get("messages", []):
        content = msg["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for part in content:
            blocks.append({"role": msg["role"], **part})
    return blocks


class FakeAnthropic:
    def __init__(self) -> None:
        self.cache: set[str] = set()
        self.last_request: dict | None = None

    def messages(self, body: dict) -> dict:
        self.last_request = copy.deepcopy(body)
        blocks = flatten(body)
        breakpoints = [i for i, b in enumerate(blocks) if "cache_control" in b]
        if "cache_control" in body and blocks:
            breakpoints.append(len(blocks) - 1)
        breakpoints = sorted(set(breakpoints))

        sizes = [_tokens(_strip_marker(b)) for b in blocks]
        total = sum(sizes)

        def key(i: int) -> str:
            prefix = [_strip_marker(b) for b in blocks[: i + 1]]
            return hashlib.sha256(json.dumps(prefix, sort_keys=True).encode()).hexdigest()

        def upto(i: int) -> int:
            return sum(sizes[: i + 1])

        cacheable = [i for i in breakpoints if upto(i) >= MIN_CACHEABLE]
        # each breakpoint also checks up to LOOKBACK earlier blocks for a cached prefix
        candidates = sorted({j for i in cacheable for j in range(i, max(-1, i - LOOKBACK), -1)}, reverse=True)
        read_end = next((j for j in candidates if key(j) in self.cache), -1)
        last = cacheable[-1] if cacheable else -1

        read = upto(read_end) if read_end >= 0 else 0
        created = (upto(last) - read) if last > read_end else 0
        for i in cacheable:
            self.cache.add(key(i))

        return {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {
                "input_tokens": total - read - created,
                "cache_creation_input_tokens": created,
                "cache_read_input_tokens": read,
                "output_tokens": 1,
            },
        }
