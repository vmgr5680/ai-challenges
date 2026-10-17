"""A standard-library ASGI middleware that makes a localhost dev server refuse web pages.

Wrap any local ASGI app (an agent chat UI, an MCP server over HTTP, a FastAPI dev tool):

    app = LocalOnlyGuard(app)                       # localhost / IPs only
    app = LocalOnlyGuard(app, allowed_hosts=['ui.example.com'])

It applies the same two checks the Pydantic AI fix ships, in front of the app:

1. Host check, against DNS rebinding: answer only when the Host header is an IP
   literal, `localhost`, a `*.localhost` name, or a name you listed. Otherwise 421.
2. Content-type check, against cross-site "simple requests": a state-changing request
   (POST, PUT, PATCH, DELETE) must say `application/json`, which a browser cannot send
   cross-origin without a preflight. Otherwise 415. Never answer that preflight with
   `Access-Control-Allow-*` headers, or this check stops meaning anything.

It is a guard for development servers, not authentication. Anything reachable by other
people still needs real authentication in front of it.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def host_is_local(host_header: str, allowed: tuple[str, ...] = ()) -> bool:
    """True if the Host header names this machine, not somebody else's domain."""
    if not host_header or set('@/?#') & set(host_header):
        return False
    try:
        name = (urlsplit(f'//{host_header}').hostname or '').removesuffix('.')
    except ValueError:
        return False
    try:
        ipaddress.ip_address(name)
        return True  # an IP literal cannot be rebound; rebinding needs a name
    except ValueError:
        pass
    return name == 'localhost' or name.endswith('.localhost') or name in allowed


def content_type_is_json(content_type: str) -> bool:
    return content_type.split(';')[0].strip().lower() == 'application/json'


class LocalOnlyGuard:
    def __init__(self, app, allowed_hosts: list[str] | tuple[str, ...] = ()):
        self.app = app
        self.allowed = tuple(h.lower().removesuffix('.') for h in allowed_hosts)

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        headers = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope['headers']}
        if not host_is_local(headers.get('host', ''), self.allowed):
            return await _reply(scope, send, 421, b'misdirected request: unknown Host')
        if scope['type'] == 'http' and scope['method'] in UNSAFE_METHODS:
            if not content_type_is_json(headers.get('content-type', '')):
                return await _reply(scope, send, 415, b'expected Content-Type: application/json')
        return await self.app(scope, receive, send)


async def _reply(scope, send, status: int, body: bytes) -> None:
    if scope['type'] == 'websocket':
        await send({'type': 'websocket.close', 'code': 1008})
        return
    await send({'type': 'http.response.start', 'status': status,
                'headers': [(b'content-type', b'text/plain; charset=utf-8')]})
    await send({'type': 'http.response.body', 'body': body})
