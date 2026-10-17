"""AFTER: the same attacks against the follow-up fix and two other remedies.

  A. Loom's follow-up fix: forwarding headers disqualify the bypass, and the
     process refuses to start with the opt-in in a deployed-looking environment.
  B. Configuration-only workaround: trust forwarding headers from the load
     balancer's address range only, never '*'.
  C. Proposed design: a missing IdP never creates an identity; a one-time setup
     token is the only way in until one is registered.
"""

import secrets

from loom_model import (
    VALID_TOKEN,
    Deployment,
    assert_bypass_not_deployed,
    auth_bootstrap_token,
    auth_header_fix,
    auth_loopback_fix,
    make_app,
    send,
    show,
)

REMOTE = "203.0.113.9"
LOAD_BALANCER = "10.0.0.5"
SPOOF = {"X-Forwarded-For": "127.0.0.1"}
VIA_LB = {"X-Forwarded-For": f"127.0.0.1, {REMOTE}"}


def scenarios():
    widened = Deployment(local_dev_opt_in=True, forwarded_allow_ips="*")
    app = make_app(auth_header_fix, widened)
    yield "A1. follow-up fix, spoofed X-Forwarded-For", send(app, REMOTE, SPOOF)
    yield "A2. follow-up fix, via load balancer", send(app, LOAD_BALANCER, VIA_LB)
    yield "A3. follow-up fix, real developer on loopback", send(app, "127.0.0.1")

    scoped = Deployment(local_dev_opt_in=True, forwarded_allow_ips="10.0.0.0/8")
    app = make_app(auth_loopback_fix, scoped)  # note: the FIRST fix, only proxy trust changed
    yield "B1. first fix + trust LB range only, spoofed", send(app, REMOTE, SPOOF)
    yield "B2. first fix + trust LB range only, via LB", send(app, LOAD_BALANCER, VIA_LB)

    token = secrets.token_urlsafe(32)
    fresh = Deployment(bootstrap_token=token, forwarded_allow_ips="*")
    app = make_app(auth_bootstrap_token, fresh)
    yield "C1. setup token design, spoofed, no token", send(app, REMOTE, SPOOF)
    yield "C2. setup token design, loopback, no token", send(app, "127.0.0.1")
    operator = {"Authorization": f"Bearer {token}"}
    yield "C3. setup token, operator registers IdP (POST)", send(
        app, REMOTE, operator, method="POST", path="/api/setup/idp"
    )
    yield "C4. setup token, operator reads settings", send(app, REMOTE, operator)
    ready = Deployment(idp_configured=True, forwarded_allow_ips="*")
    app = make_app(auth_bootstrap_token, ready)
    yield "C5. IdP registered, valid user token", send(
        app, REMOTE, {"Authorization": f"Bearer {VALID_TOKEN}"}
    )


def startup_checks():
    for label, dep in [
        ("opt-in + FORWARDED_ALLOW_IPS='*'", Deployment(local_dev_opt_in=True, forwarded_allow_ips="*")),
        ("opt-in + container runtime", Deployment(local_dev_opt_in=True, in_container=True)),
        ("opt-in on a laptop, defaults", Deployment(local_dev_opt_in=True)),
    ]:
        try:
            assert_bypass_not_deployed(dep)
            yield f"{label:<54} -> starts"
        except RuntimeError as e:
            yield f"{label:<54} -> refuses to start ({str(e).split(': ', 1)[1]})"


if __name__ == "__main__":
    print("AFTER  (same remote client, GET /api/settings)")
    for label, r in scenarios():
        print(show(label, r))
    print("\nStartup check (follow-up fix)")
    for line in startup_checks():
        print(line)
