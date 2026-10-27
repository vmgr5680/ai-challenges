"""A test you can put in your gateway's CI: nothing the client sent may vanish.

lost_fields(sent, forwarded) lists every key path in the client request that is
missing from the request the gateway forwards. Paths are compared positionally
(system.0.cache_control), so translate the request, then call it.
"""

from __future__ import annotations


def paths(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from paths(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from paths(v, f"{prefix}{i}.")
    else:
        yield prefix.rstrip(".")


def lost_fields(sent: dict, forwarded: dict) -> list[str]:
    return sorted(set(paths(sent)) - set(paths(forwarded)))
