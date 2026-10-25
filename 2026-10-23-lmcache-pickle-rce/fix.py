"""The fix pattern: typed, allowlisted decoding that never calls pickle.

This mirrors what the fixed LMCache release does on its transport: replace
pickle with versioned, typed MessagePack descriptors that are validated
against a fixed local allowlist before use, with no pickle fallback.

Here we show the shape with the standard library only (JSON stands in for the
typed MessagePack wire format). The point is structural, not the codec:

  - a fixed allowlist of descriptor kinds the server will build,
  - fields validated before any object is constructed,
  - no code path that turns bytes into an arbitrary object.

Run:  python3 -I fix.py
"""

from __future__ import annotations

import json

# Only these descriptor kinds exist. Anything else is refused.
ALLOWED_KINDS = {"cache_descriptor"}


class CacheDescriptor:
    def __init__(self, slot: int, shape: list[int]) -> None:
        self.slot = slot
        self.shape = shape


def safe_handler(raw: bytes) -> CacheDescriptor:
    """Decode a plain typed record. No callable is ever reconstructed."""
    msg = json.loads(raw)  # JSON builds only dict/list/str/int/float/bool/None
    if not isinstance(msg, dict):
        raise ValueError("malformed message")
    kind = msg.get("kind")
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"unknown descriptor kind: {kind!r}")
    slot = msg["slot"]
    shape = msg["shape"]
    if not isinstance(slot, int) or not (
        isinstance(shape, list) and all(isinstance(n, int) for n in shape)
    ):
        raise ValueError("bad fields")
    return CacheDescriptor(slot, shape)


def main() -> None:
    good = json.dumps({"kind": "cache_descriptor", "slot": 0, "shape": [2, 16]}).encode()
    d = safe_handler(good)
    print(f"AFTER: legitimate record decoded -> slot={d.slot} shape={d.shape}")

    # A hostile message cannot name a callable: there is no pickle, and the
    # kind is not on the allowlist. It is refused before anything is built.
    hostile = json.dumps({"kind": "os.system", "slot": 0, "shape": [1]}).encode()
    try:
        safe_handler(hostile)
    except ValueError as e:
        print(f"AFTER: hostile message refused -> {e}  <-- no code runs")


if __name__ == "__main__":
    main()
