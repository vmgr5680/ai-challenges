"""BEFORE: the same session direct, then through a gateway that drops cache_control.

Run:  python3 reproduce.py
SIMULATED upstream (see fake_anthropic.py); the gateway bug matches the reports
in mlflow#26477, maximhq/bifrost#8712, BerriAI/litellm#33687, argo-proxy#140.
"""

from __future__ import annotations

import gateway
import session


def main() -> None:
    direct = session.run(gateway.passthrough)
    via = session.run(gateway.translate_typed)
    session.print_rows("DIRECT to the provider", direct)
    print()
    session.print_rows("THROUGH the typed gateway (BEFORE)", via)

    body = session.request_for_turn([], "Question 1")
    sent = gateway.translate_typed(body)
    print()
    print("client sent system block keys :", sorted(body["system"][0]))
    print("gateway sent system block keys:", sorted(sent["system"][0]))
    d, v = (sum(r["cost"] for r in rows) for rows in (direct, via))
    print(f"gateway session costs {v / d:.1f}x the direct session; no error was raised")


if __name__ == "__main__":
    main()
