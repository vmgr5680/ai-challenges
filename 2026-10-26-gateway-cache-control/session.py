"""A ten-turn agent session that marks its stable prefix for caching.

The client does what the prompt-caching docs recommend: one breakpoint on the
end of the system prompt (tools + system are the same every turn) and one on the
newest user message, so each turn can reuse everything before it.

Cost is in "base input token units": an uncached input token costs 1, a cache
write 1.25 (5-minute TTL) and a cache read 0.1, the documented default
multipliers. Output tokens are left out because caching does not change them.
"""

from __future__ import annotations

import copy

from fake_anthropic import FakeAnthropic

WRITE, READ = 1.25, 0.1
TURNS = 10

SYSTEM = " ".join(f"Policy rule {i}: answer only from the attached account record." for i in range(400))
TOOLS = [
    {"name": "lookup_account", "description": "Fetch an account record by id. " * 40,
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}}},
    {"name": "open_ticket", "description": "Open a support ticket. " * 40,
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}},
]


def request_for_turn(history: list[dict], question: str) -> dict:
    messages = copy.deepcopy(history)
    messages.append({"role": "user", "content": [
        {"type": "text", "text": question, "cache_control": {"type": "ephemeral"}},
    ]})
    return {
        "model": "claude-example",
        "max_tokens": 256,
        "tools": TOOLS,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
    }


def cost(usage: dict) -> float:
    return (usage["input_tokens"]
            + WRITE * usage["cache_creation_input_tokens"]
            + READ * usage["cache_read_input_tokens"])


def run(gateway, turns: int = TURNS) -> list[dict]:
    """Send a session through `gateway` (a body -> body function) to a fresh fake upstream."""
    upstream = FakeAnthropic()
    history: list[dict] = []
    rows = []
    for t in range(1, turns + 1):
        body = request_for_turn(history, f"Question {t}: what is the status of account A-{t:03d}?")
        usage = upstream.messages(gateway(body))["usage"]
        rows.append({"turn": t, **usage, "cost": cost(usage)})
        # the client keeps history without the per-turn marker, as SDKs do
        q = copy.deepcopy(body["messages"][-1])
        q["content"][0].pop("cache_control", None)
        history += [q, {"role": "assistant", "content": [{"type": "text", "text": f"Account A-{t:03d} is active."}]}]
    return rows


def print_rows(label: str, rows: list[dict]) -> None:
    print(label)
    print(f"{'turn':>4} {'input':>6} {'cache_write':>11} {'cache_read':>10} {'cost':>8}")
    for r in rows:
        print(f"{r['turn']:>4} {r['input_tokens']:>6} {r['cache_creation_input_tokens']:>11}"
              f" {r['cache_read_input_tokens']:>10} {r['cost']:>8.0f}")
    print(f"total cost: {sum(r['cost'] for r in rows):,.0f} units")
