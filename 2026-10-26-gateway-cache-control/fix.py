"""AFTER: the same session through the fixed gateway and the passthrough gateway.

Run:  python3 fix.py
"""

from __future__ import annotations

import gateway
import session
from roundtrip_guard import lost_fields


def main() -> None:
    fixed = session.run(gateway.translate_preserving)
    session.print_rows("THROUGH the preserving gateway (AFTER)", fixed)
    passed = session.run(gateway.passthrough)
    print(f"passthrough gateway total cost: {sum(r['cost'] for r in passed):,.0f} units")

    body = session.request_for_turn([], "Question 1")
    body["cache_control"] = {"type": "ephemeral"}  # automatic caching, top level
    for name in ("translate_typed", "translate_preserving", "passthrough"):
        lost = lost_fields(body, getattr(gateway, name)(body))
        print(f"round-trip guard, {name:<21}: {'PASS' if not lost else 'FAIL, lost ' + ', '.join(lost)}")


if __name__ == "__main__":
    main()
