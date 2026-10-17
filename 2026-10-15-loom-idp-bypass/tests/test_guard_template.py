"""Copy this guard into your own FastAPI/Starlette service.

It builds the worst plausible deployment (no identity provider, every proxy
trusted) and calls a protected route as a remote stranger who forges
X-Forwarded-For. Swap `build_app()` for your app factory and `PROTECTED` for a
real admin route.
"""

import asyncio
import sys
from pathlib import Path

import httpx
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loom_model import Deployment, auth_header_fix, make_app  # noqa: E402

PROTECTED = "/api/settings"


def build_app():
    # Your app, configured as a fresh deployment: identity provider not set up yet.
    return make_app(auth_header_fix, Deployment(local_dev_opt_in=True))


def call_as(peer, headers):
    app = ProxyHeadersMiddleware(build_app(), trusted_hosts="*")  # worst-case proxy trust

    async def go():
        transport = httpx.ASGITransport(app=app, client=(peer, 40000))
        async with httpx.AsyncClient(transport=transport, base_url="http://svc") as c:
            return await c.get(PROTECTED, headers=headers)

    return asyncio.run(go())


def test_missing_identity_config_never_grants_access():
    r = call_as("203.0.113.9", {"X-Forwarded-For": "127.0.0.1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "No identity provider configured"  # which 401, not any 401
