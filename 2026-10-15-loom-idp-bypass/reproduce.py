"""BEFORE: the missing-IdP branch, before the fix and after the first fix.

Every request comes from 203.0.113.9 (a documentation address standing in for
any remote client) and carries NO Authorization header. Runs in-process; no
sockets, no AWS, no real Loom deployment.
"""

from loom_model import Deployment, auth_before, auth_loopback_fix, make_app, send, show

REMOTE = "203.0.113.9"
LOAD_BALANCER = "10.0.0.5"
SPOOF = {"X-Forwarded-For": "127.0.0.1"}


def scenarios():
    fresh = Deployment()  # IdP not set up yet, uvicorn defaults
    yield "1. before the fix, fresh deployment", send(make_app(auth_before, fresh), REMOTE)

    yield "2. first fix, opt-in unset", send(make_app(auth_loopback_fix, fresh), REMOTE)

    stale = Deployment(local_dev_opt_in=True)  # opt-in left in the task definition
    app = make_app(auth_loopback_fix, stale)
    yield "3. first fix, opt-in left on, default proxy trust", send(app, REMOTE)
    yield "4.   same, plus X-Forwarded-For: 127.0.0.1", send(app, REMOTE, SPOOF)

    widened = Deployment(local_dev_opt_in=True, forwarded_allow_ips="*")
    app = make_app(auth_loopback_fix, widened)
    yield "5. first fix, opt-in on, FORWARDED_ALLOW_IPS='*'", send(app, REMOTE)
    yield "6.   same, plus X-Forwarded-For: 127.0.0.1", send(app, REMOTE, SPOOF)
    yield "7.   same, via load balancer that appends real IP", send(
        app, LOAD_BALANCER, {"X-Forwarded-For": f"127.0.0.1, {REMOTE}"}
    )


if __name__ == "__main__":
    print("BEFORE  (remote client, no credentials, GET /api/settings)")
    for label, r in scenarios():
        print(show(label, r))
