"""Why 'deserialize a cache descriptor' can mean 'run code' - a safe toy.

This does NOT attack LMCache or any network service. It is a self-contained,
in-process illustration of the *class* of bug behind CVE-2026-105192: a server
that unpickles bytes it received from a client is executing whatever that
client chose to send, before any handler logic runs.

The 'payload' here is benign on purpose: it writes a marker file into a temp
directory and nothing else. It stands in for the arbitrary command an attacker
would run. See the public advisory GHSA-w5f2-9q9c-ff4h for the real transport
details; we deliberately do not reproduce a working exploit.

Run:  python3 -I reproduce.py
"""

from __future__ import annotations

import os
import pickle
import tempfile


class CacheDescriptor:
    """What a legitimate client is *supposed* to send: a small record."""

    def __init__(self, slot: int, shape: tuple[int, ...]) -> None:
        self.slot = slot
        self.shape = shape


class MarkerDescriptor:
    """What a hostile client *can* send instead. __reduce__ decides what
    happens at unpickle time - here, dropping a harmless marker file."""

    def __init__(self, path: str) -> None:
        self.path = path

    def __reduce__(self):
        # os.system stands in for the attacker's command. Kept benign:
        # it only creates an empty file so the test can observe side effects.
        return (os.system, (f"touch {self.path}",))


def vulnerable_handler(raw: bytes) -> object:
    """The vulnerable pattern: unpickle first, validate later (too late)."""
    obj = pickle.loads(raw)  # side effects already happened by this line
    if not isinstance(obj, CacheDescriptor):
        raise TypeError("expected CacheDescriptor")  # runs AFTER the damage
    return obj


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="lmcache_toy_")
    marker = os.path.join(tmp, "pwned_marker")

    # A hostile client serialises a MarkerDescriptor as if it were a cache slot.
    hostile_bytes = pickle.dumps(MarkerDescriptor(marker))

    print("BEFORE: server calls pickle.loads() on client bytes")
    print(f"  marker exists before: {os.path.exists(marker)}")
    try:
        vulnerable_handler(hostile_bytes)
    except TypeError as e:
        print(f"  handler raised: {e}")
    print(f"  marker exists after : {os.path.exists(marker)}  <-- side effect ran")
    print("  the type check rejected the object, but the command already ran.")


if __name__ == "__main__":
    main()
