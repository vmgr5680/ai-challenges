"""A toy model of the bug class behind GHSA-qx49-fqc8-xw99: a check that only runs
when an optional value happens to be present.

This is NOT the MCP SDK and talks to no network. "Discovery" is a dict lookup and the
result is a decision record, so nothing is ever sent anywhere. It exists to make the
pattern visible and testable in a few lines.

Functions, in article order:
    choose_issuer_conditional()  the pre-fix shape: compare only if an expected value exists
    choose_issuer_fail_closed()  the fixed shape: always compute an expected value, then compare
    run_scenarios()              the two discovery outcomes, run through one chooser
"""

from dataclasses import dataclass


@dataclass
class Decision:
    scenario: str
    expected: str | None
    claimed: str
    check: str          # "ran" or "skipped"
    outcome: str        # "accepted" or "rejected"


def choose_issuer_conditional(expected: str | None, claimed: str) -> tuple[str, str]:
    """Pre-fix shape. `expected` is only known when the first discovery step succeeded."""
    if expected is not None:
        if claimed != expected:
            return "ran", "rejected"
        return "ran", "accepted"
    return "skipped", "accepted"


def choose_issuer_fail_closed(expected: str | None, claimed: str, fallback: str) -> tuple[str, str]:
    """Fixed shape. When discovery gives no expected value, derive one before looking at the claim."""
    expected = expected or fallback
    if claimed != expected:
        return "ran", "rejected"
    return "ran", "accepted"


# Two discovery outcomes for a client connecting to https://tools.example.test.
# In both, the metadata the client receives claims an issuer it was never pointed at.
SERVER_ORIGIN = "https://tools.example.test"
SCENARIOS = {
    "discovery names an auth server": {"expected": "https://login.example.test", "claimed": "https://other.example.test"},
    "discovery returns nothing":      {"expected": None,                         "claimed": "https://other.example.test"},
}


def run_scenarios(fixed: bool) -> list[Decision]:
    out = []
    for name, s in SCENARIOS.items():
        if fixed:
            check, outcome = choose_issuer_fail_closed(s["expected"], s["claimed"], SERVER_ORIGIN)
            expected = s["expected"] or SERVER_ORIGIN
        else:
            check, outcome = choose_issuer_conditional(s["expected"], s["claimed"])
            expected = s["expected"]
        out.append(Decision(name, expected, s["claimed"], check, outcome))
    return out


def report(decisions: list[Decision]) -> str:
    lines = [f"{'scenario':32} {'expected issuer':28} {'check':8} outcome"]
    for d in decisions:
        lines.append(f"{d.scenario:32} {str(d.expected):28} {d.check:8} {d.outcome}")
    return "\n".join(lines)
