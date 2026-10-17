"""A small, faithful model of Loom's authentication dependency (CVE-2026-103956).

Loom's real `get_current_user` lives in `backend/app/dependencies/auth.py`
(snapshots of three releases are in `upstream/`). Loom needs AWS, Cognito and a
database to run, so this module copies only the decision logic, branch for
branch, into a FastAPI app. The client address is resolved by uvicorn's real
`ProxyHeadersMiddleware`, exactly as `uvicorn --proxy-headers` (the default) does.

Index, in article order:
  auth_before()                  releases before the fix: no IdP => super-admin for every request
  auth_loopback_fix()            first fix: needs an opt-in AND request.client on loopback
  auth_header_fix()              follow-up fix: also refuses requests that carry forwarding headers
  assert_bypass_not_deployed()   follow-up fix: refuse to start in a deployed-looking environment
  auth_bootstrap_token()         proposed alternative: no IdP => only a one-time setup token works
  make_app()                     the app, wrapped in uvicorn's ProxyHeadersMiddleware
  send()                         drive the app in-process as a client at any IP address
"""

from __future__ import annotations

import asyncio
import hmac
from dataclasses import dataclass, field
from typing import Callable

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

ALL_SCOPES = ["admin:read", "admin:write", "agent:invoke", "security:write", "mcp:write"]
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
FORWARDING_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip", "forwarded")
VALID_TOKEN = "valid-idp-token"  # stands in for a JWT the configured IdP would sign


@dataclass
class Deployment:
    """The settings that decide the outcome. Defaults = a fresh deployment, IdP not set up yet."""

    idp_configured: bool = False          # Cognito pool or an active external IdP
    local_dev_opt_in: bool = False        # LOOM_ALLOW_UNAUTHENTICATED_LOCAL_DEV
    forwarded_allow_ips: str = "127.0.0.1"  # uvicorn FORWARDED_ALLOW_IPS (its default)
    in_container: bool = False            # ECS_CONTAINER_METADATA_URI_V4 / AWS_EXECUTION_ENV present
    bootstrap_token: str = field(default="", repr=False)


@dataclass
class User:
    username: str
    groups: list[str]
    scopes: list[str]


SUPER_ADMIN = User("local-dev", ["t-admin", "g-admins-super"], ALL_SCOPES.copy())


def _validate_token(request: Request) -> User:
    """The normal path once an IdP exists: no token or a bad token is a 401."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "Missing authorization token")
    if token != VALID_TOKEN:
        raise HTTPException(401, "Invalid or expired token")
    return User("alice", ["g-admins-super"], ALL_SCOPES.copy())


def _is_loopback(request: Request) -> bool:
    return bool(request.client) and request.client.host in LOOPBACK_HOSTS


def auth_before(dep: Deployment, request: Request) -> User:
    """Releases before the fix: the missing-config branch returns an identity."""
    if not dep.idp_configured:
        return SUPER_ADMIN  # no Authorization header needed
    return _validate_token(request)


def auth_loopback_fix(dep: Deployment, request: Request) -> User:
    """First fix: the bypass needs the opt-in and a loopback client, else 401."""
    if not dep.idp_configured:
        if dep.local_dev_opt_in and _is_loopback(request):
            return SUPER_ADMIN
        raise HTTPException(401, "No identity provider configured")
    return _validate_token(request)


def auth_header_fix(dep: Deployment, request: Request) -> User:
    """Follow-up fix: a request with any forwarding header can't use the bypass."""
    if not dep.idp_configured:
        has_fwd = any(h in request.headers for h in FORWARDING_HEADERS)
        if dep.local_dev_opt_in and not has_fwd and _is_loopback(request):
            return SUPER_ADMIN
        raise HTTPException(401, "No identity provider configured")
    return _validate_token(request)


def assert_bypass_not_deployed(dep: Deployment) -> None:
    """Follow-up fix: fail at startup, not at request time."""
    if not dep.local_dev_opt_in:
        return
    reasons = []
    if dep.in_container:
        reasons.append("container runtime detected")
    if dep.forwarded_allow_ips.strip() not in {"", "127.0.0.1", "::1", "localhost", "127.0.0.1,::1"}:
        reasons.append(f"FORWARDED_ALLOW_IPS={dep.forwarded_allow_ips!r} trusts non-loopback proxies")
    if reasons:
        raise RuntimeError("local-dev auth bypass enabled in a deployed environment: " + "; ".join(reasons))


def auth_bootstrap_token(dep: Deployment, request: Request) -> User:
    """Proposed alternative: missing config never creates an identity.

    Until an IdP exists, the only way in is a one-time setup token generated at
    startup and readable only by the operator (secret store or local file).
    Network position (loopback or not) plays no part in the decision.
    """
    if not dep.idp_configured:
        auth = request.headers.get("authorization", "")
        presented = auth[7:] if auth.startswith("Bearer ") else ""
        if dep.bootstrap_token and presented and hmac.compare_digest(presented, dep.bootstrap_token):
            return User("bootstrap", ["setup"], ["admin:write"])  # enough to register an IdP
        raise HTTPException(401, "Identity provider not configured; setup token required")
    return _validate_token(request)


AuthFn = Callable[[Deployment, Request], User]


def make_app(auth: AuthFn, dep: Deployment):
    """A one-route admin API behind uvicorn's real proxy-header handling."""
    app = FastAPI()

    def current_user(request: Request) -> User:
        return auth(dep, request)

    @app.get("/api/settings")
    def settings(request: Request, user: User = Depends(current_user)):
        if "admin:read" not in user.scopes:
            raise HTTPException(403, "Forbidden")
        return {"as": user.username, "groups": user.groups, "seen_client": request.client.host}

    @app.get("/api/auth/me")  # same path as Loom's identity endpoint; detect.py probes it
    def me(user: User = Depends(current_user)):
        return {"username": user.username, "groups": user.groups}

    @app.post("/api/setup/idp")
    def register_idp(user: User = Depends(current_user)):
        if "admin:write" not in user.scopes:
            raise HTTPException(403, "Forbidden")
        return {"as": user.username, "groups": user.groups}

    return ProxyHeadersMiddleware(app, trusted_hosts=dep.forwarded_allow_ips)


def send(app, peer_ip: str, headers: dict | None = None, method: str = "GET",
         path: str = "/api/settings") -> httpx.Response:
    """Call the app as a TCP peer at `peer_ip`, without opening a socket."""

    async def _go():
        transport = httpx.ASGITransport(app=app, client=(peer_ip, 51515))
        async with httpx.AsyncClient(transport=transport, base_url="http://loom.internal") as c:
            return await c.request(method, path, headers=headers or {})

    return asyncio.run(_go())


def show(label: str, r: httpx.Response) -> str:
    body = r.json()
    detail = f"as {body['as']} {body['groups']}" if r.status_code == 200 else body.get("detail")
    return f"{label:<54} -> {r.status_code} {detail}"
