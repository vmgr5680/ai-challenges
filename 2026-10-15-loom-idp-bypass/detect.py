"""Am I affected? Three checks for Loom deployments and forks (CVE-2026-103956).

  python detect.py --source PATH     classify a checkout/fork's auth.py (offline)
  python detect.py --env [FILE]      check this process's env, or a KEY=VALUE / ECS task-def JSON file
  python detect.py --url BASE_URL    probe YOUR OWN deployment: GET /api/auth/me with no credentials

The --url probe sends two read-only requests to an identity endpoint that
returns only "who the server thinks you are". Run it only against systems you
operate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

TRUTHY = {"1", "true", "yes"}


def classify_source(text: str) -> tuple[str, str]:
    """Classify Loom's get_current_user by the guards present around the no-IdP branch."""
    if "not user_pool_id and not active_idp" not in text:
        return "UNKNOWN", "no-IdP branch not found; not Loom's auth.py or heavily changed"
    if "LOOM_ALLOW_UNAUTHENTICATED_LOCAL_DEV" not in text:
        return "VULNERABLE", "no IdP => super-admin for every request (pre-fix code)"
    if "_has_forwarding_headers" not in text or "assert_local_dev_bypass_not_deployed" not in text:
        return "PARTIAL", "opt-in + loopback check only; spoofable if the opt-in is set and proxy trust is widened"
    return "PATCHED", "opt-in, loopback, forwarding-header refusal and startup check present"


def check_source(path: Path) -> tuple[str, str]:
    if path.is_dir():
        path = path / "backend" / "app" / "dependencies" / "auth.py"
    return classify_source(path.read_text())


def load_env(file: str | None) -> dict[str, str]:
    if not file:
        return dict(os.environ)
    raw = Path(file).read_text()
    try:  # ECS task definition JSON
        doc = json.loads(raw)
        env = {}
        for c in doc.get("containerDefinitions", []):
            env.update({e["name"]: e["value"] for e in c.get("environment", [])})
        return env
    except json.JSONDecodeError:
        pairs = (line.split("=", 1) for line in raw.splitlines() if "=" in line and not line.startswith("#"))
        return {k.strip(): v.strip().strip("'\"") for k, v in pairs}


def check_env(env: dict[str, str]) -> list[str]:
    findings = []
    opt_in = env.get("LOOM_ALLOW_UNAUTHENTICATED_LOCAL_DEV", "").strip().lower() in TRUTHY
    fwd = env.get("FORWARDED_ALLOW_IPS", "").replace(" ", "")
    if opt_in:
        findings.append("HIGH  LOOM_ALLOW_UNAUTHENTICATED_LOCAL_DEV is set: remove it from any deployed environment")
    if "*" in fwd.split(",") or "0.0.0.0/0" in fwd:
        findings.append(f"HIGH  FORWARDED_ALLOW_IPS={fwd!r} trusts X-Forwarded-For from anyone: set your load balancer's range")
    if not env.get("LOOM_COGNITO_USER_POOL_ID"):
        findings.append("CHECK LOOM_COGNITO_USER_POOL_ID unset: confirm an external IdP is active before exposing the backend")
    return findings


def _get(url: str, headers: dict) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(300).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode(errors="replace")


def probe(base_url: str) -> list[str]:
    url = base_url.rstrip("/") + "/api/auth/me"
    results = []
    for label, headers in [("no credentials", {}), ("no credentials + X-Forwarded-For: 127.0.0.1", {"X-Forwarded-For": "127.0.0.1"})]:
        status, body = _get(url, headers)
        verdict = "AFFECTED: identity granted without credentials" if status == 200 else "ok"
        results.append(f"{status}  {label:<46} {verdict}  {body[:80]!r}")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--env", nargs="?", const="", default=None)
    ap.add_argument("--url")
    a = ap.parse_args(argv)
    bad = False
    if a.source:
        verdict, why = check_source(a.source)
        print(f"source  {verdict:<10} {why}")
        bad |= verdict in {"VULNERABLE", "PARTIAL"}
    if a.env is not None:
        findings = check_env(load_env(a.env or None))
        for f in findings or ["ok    no risky auth/proxy settings found"]:
            print(f"env     {f}")
        bad |= any(f.startswith("HIGH") for f in findings)
    if a.url:
        for line in probe(a.url):
            print(f"probe   {line}")
            bad |= line.startswith("200")
    if not (a.source or a.env is not None or a.url):
        ap.print_help()
        return 2
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
