"""Three ways a gateway can forward an Anthropic Messages request.

A gateway that supports many providers usually parses each request into its own
typed model (an "internal representation") and writes a new provider request from
it. Anything the model has no field for is lost on the way through.

  translate_typed()      the bug: known fields only, unknown keys ignored
                         (what pydantic's default extra="ignore", a Go struct
                         without the field, or an IR without a cache field do)
  translate_preserving() the fix: same typed model, unknown keys carried along
  passthrough()          the alternative: same-format requests forwarded as-is
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field


# ---------- the typed internal model ----------

@dataclass
class TextPart:
    type: str
    text: str
    extras: dict = field(default_factory=dict)


@dataclass
class Message:
    role: str
    content: list[TextPart]
    extras: dict = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    extras: dict = field(default_factory=dict)


@dataclass
class Request:
    model: str
    max_tokens: int
    system: list[TextPart]
    messages: list[Message]
    tools: list[Tool]
    extras: dict = field(default_factory=dict)


KNOWN = {
    "part": {"type", "text"},
    "message": {"role", "content"},
    "tool": {"name", "description", "input_schema"},
    "request": {"model", "max_tokens", "system", "messages", "tools"},
}


def _unknown(d: dict, kind: str, keep: bool) -> dict:
    return {k: copy.deepcopy(v) for k, v in d.items() if k not in KNOWN[kind]} if keep else {}


def _parts(content, keep: bool) -> list[TextPart]:
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    return [TextPart(p["type"], p["text"], _unknown(p, "part", keep)) for p in content]


def parse(body: dict, keep_unknown: bool) -> Request:
    return Request(
        model=body["model"],
        max_tokens=body["max_tokens"],
        system=_parts(body.get("system", []), keep_unknown),
        messages=[
            Message(m["role"], _parts(m["content"], keep_unknown), _unknown(m, "message", keep_unknown))
            for m in body.get("messages", [])
        ],
        tools=[
            Tool(t["name"], t.get("description", ""), t["input_schema"], _unknown(t, "tool", keep_unknown))
            for t in body.get("tools", [])
        ],
        extras=_unknown(body, "request", keep_unknown),
    )


def render(req: Request) -> dict:
    """Write an Anthropic Messages body from the internal model."""
    part = lambda p: {"type": p.type, "text": p.text, **p.extras}  # noqa: E731
    body = {
        "model": req.model,
        "max_tokens": req.max_tokens,
        "system": [part(p) for p in req.system],
        "messages": [{"role": m.role, "content": [part(p) for p in m.content], **m.extras} for m in req.messages],
        **req.extras,
    }
    if req.tools:
        body["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema, **t.extras}
            for t in req.tools
        ]
    return body


# ---------- the three gateways ----------

def translate_typed(body: dict) -> dict:
    """BUG: round-trips through the typed model and drops every unknown key."""
    return render(parse(body, keep_unknown=False))


def translate_preserving(body: dict) -> dict:
    """FIX: same round trip, but unknown keys ride along on each object."""
    return render(parse(body, keep_unknown=True))


def passthrough(body: dict) -> dict:
    """ALTERNATIVE: Anthropic in, Anthropic out, so forward the body untouched."""
    return copy.deepcopy(body)
