"""The bug reproduces, each remedy closes it, and the detector agrees with real upstream code."""

import secrets
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import detect  # noqa: E402
from loom_model import (  # noqa: E402
    Deployment,
    assert_bypass_not_deployed,
    auth_before,
    auth_bootstrap_token,
    auth_header_fix,
    auth_loopback_fix,
    make_app,
    send,
)

REMOTE = "203.0.113.9"
SPOOF = {"X-Forwarded-For": "127.0.0.1"}
VIA_LB = {"X-Forwarded-For": f"127.0.0.1, {REMOTE}"}
WIDENED = Deployment(local_dev_opt_in=True, forwarded_allow_ips="*")


# --- BEFORE: the bug reproduces -------------------------------------------

def test_before_fix_remote_caller_gets_super_admin_with_no_credentials():
    r = send(make_app(auth_before, Deployment()), REMOTE)
    assert r.status_code == 200
    assert "g-admins-super" in r.json()["groups"]


@pytest.mark.parametrize("peer,headers", [(REMOTE, SPOOF), ("10.0.0.5", VIA_LB)])
def test_first_fix_is_spoofable_when_proxy_trust_is_widened(peer, headers):
    r = send(make_app(auth_loopback_fix, WIDENED), peer, headers)
    assert r.status_code == 200
    assert r.json()["seen_client"] == "127.0.0.1"  # uvicorn rewrote request.client


def test_first_fix_holds_with_uvicorn_default_proxy_trust():
    dep = Deployment(local_dev_opt_in=True)  # FORWARDED_ALLOW_IPS default
    r = send(make_app(auth_loopback_fix, dep), REMOTE, SPOOF)
    assert r.status_code == 401


# --- AFTER: each remedy closes it -----------------------------------------
# Assert WHICH 401, not just 401: Loom's own guard tests once passed on the
# wrong rejection path (v1.8.1 release notes).

@pytest.mark.parametrize("peer,headers", [(REMOTE, SPOOF), ("10.0.0.5", VIA_LB), (REMOTE, {})])
def test_follow_up_fix_refuses_spoofed_and_proxied_requests(peer, headers):
    r = send(make_app(auth_header_fix, WIDENED), peer, headers)
    assert (r.status_code, r.json()["detail"]) == (401, "No identity provider configured")


def test_follow_up_fix_still_serves_a_real_loopback_developer():
    assert send(make_app(auth_header_fix, WIDENED), "127.0.0.1").status_code == 200


def test_startup_check_refuses_deployed_looking_environments():
    with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS"):
        assert_bypass_not_deployed(WIDENED)
    with pytest.raises(RuntimeError, match="container"):
        assert_bypass_not_deployed(Deployment(local_dev_opt_in=True, in_container=True))
    assert_bypass_not_deployed(Deployment(local_dev_opt_in=True))  # laptop: allowed


def test_trusting_only_the_load_balancer_range_defeats_the_spoof():
    dep = Deployment(local_dev_opt_in=True, forwarded_allow_ips="10.0.0.0/8")
    app = make_app(auth_loopback_fix, dep)
    assert send(app, REMOTE, SPOOF).status_code == 401
    assert send(app, "10.0.0.5", VIA_LB).status_code == 401


def test_setup_token_design_ignores_network_position():
    token = secrets.token_urlsafe(32)
    app = make_app(auth_bootstrap_token, Deployment(bootstrap_token=token, forwarded_allow_ips="*"))
    for peer, headers in [(REMOTE, SPOOF), ("127.0.0.1", {})]:
        r = send(app, peer, headers)
        assert (r.status_code, r.json()["detail"]) == (401, "Identity provider not configured; setup token required")
    op = {"Authorization": f"Bearer {token}"}
    assert send(app, REMOTE, op, method="POST", path="/api/setup/idp").status_code == 200
    assert send(app, REMOTE, op).status_code == 403  # setup token can't read settings
    assert send(app, REMOTE, {"Authorization": "Bearer wrong"}).status_code == 401


# --- Detector -------------------------------------------------------------

@pytest.mark.parametrize("tag,verdict", [("v1.6.0", "VULNERABLE"), ("v1.6.1", "PARTIAL"), ("v1.8.1", "PATCHED")])
def test_detector_classifies_real_upstream_releases(tag, verdict):
    assert detect.check_source(ROOT / "upstream" / f"auth_{tag}.py")[0] == verdict


def test_detector_env_flags_stale_opt_in_and_wildcard_trust(tmp_path):
    f = tmp_path / "task.json"
    f.write_text('{"containerDefinitions":[{"environment":[{"name":"LOOM_ALLOW_UNAUTHENTICATED_LOCAL_DEV","value":"true"},{"name":"FORWARDED_ALLOW_IPS","value":"*"}]}]}')
    findings = detect.check_env(detect.load_env(str(f)))
    assert sum(x.startswith("HIGH") for x in findings) == 2
    assert not [x for x in detect.check_env({"LOOM_COGNITO_USER_POOL_ID": "p", "FORWARDED_ALLOW_IPS": "10.0.0.0/8"})]


def _serve(asgi_app):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(asgi_app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    return server, f"http://127.0.0.1:{port}"


@pytest.mark.parametrize("auth,affected", [(auth_before, True), (auth_header_fix, False)])
def test_detector_probe_against_a_real_uvicorn_server(auth, affected):
    server, url = _serve(make_app(auth, Deployment()))
    try:
        lines = detect.probe(url)
    finally:
        server.should_exit = True
    assert all(l.startswith("200") == affected for l in lines)
