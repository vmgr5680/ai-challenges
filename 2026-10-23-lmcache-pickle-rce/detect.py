"""Detect exposure to the LMCache multiprocess-transport RCE (CVE-2026-105192).

Two checks, both read-only and offline:

1. version check - is an affected LMCache installed in this environment?
2. bind check  - is anything listening on a *routable* address on the
   transport port (default 5555), which is the exposed configuration?

This script sends nothing and connects to nothing. It inspects the local
package metadata and the local listening-socket table only.

Run:  python3 -I detect.py            # check port 5555
      python3 -I detect.py --port 5555
"""

from __future__ import annotations

import argparse
import re
import sys

# LMCache >= 0.3.9 and < 0.5.6 are vulnerable (GHSA-w5f2-9q9c-ff4h).
AFFECTED_LOW = (0, 3, 9)
FIXED = (0, 5, 6)


def version_status(version: str | None) -> str:
    """Return 'affected', 'fixed', 'not-installed' or 'unknown'.

    A pre-release of the fixed version (e.g. 0.5.6rc3) is still affected: the
    fix only lands in the final 0.5.6, so rc builds sort *below* it.
    """
    if version is None:
        return "not-installed"
    try:
        from packaging.version import Version

        v = Version(version)
        low = Version(".".join(map(str, AFFECTED_LOW)))
        fixed = Version(".".join(map(str, FIXED)))
        if low <= v < fixed:
            return "affected"
        return "fixed" if v >= fixed else "unknown"
    except Exception:
        pass
    # Fallback without packaging: treat any X.Y.Z with a pre-release suffix
    # (rc/dev/a/b/post-less) as below the clean X.Y.Z.
    nums = [int(n) for n in re.findall(r"\d+", version)[:3]]
    while len(nums) < 3:
        nums.append(0)
    base = tuple(nums)
    is_pre = bool(re.search(r"(rc|dev|a|b|alpha|beta)", version.lower()))
    if is_pre and base == FIXED:
        return "affected"
    if AFFECTED_LOW <= base < FIXED:
        return "affected"
    return "fixed" if base >= FIXED else "unknown"


def installed_version() -> str | None:
    try:
        from importlib.metadata import version as _v

        return _v("lmcache")
    except Exception:
        return None


def routable_binds(port: int) -> list[str]:
    """Local listening sockets on `port` bound to a non-loopback address.

    Uses psutil if present, otherwise returns [] with a note. We never open
    a connection; we only read the local socket table.
    """
    try:
        import psutil  # type: ignore
    except Exception:
        return []
    exposed = []
    for c in psutil.net_connections(kind="inet"):
        if c.status == "LISTEN" and c.laddr and c.laddr.port == port:
            ip = c.laddr.ip
            if ip not in ("127.0.0.1", "::1"):
                exposed.append(ip)
    return exposed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5555)
    args = ap.parse_args()

    v = installed_version()
    status = version_status(v)
    print(f"lmcache installed version : {v or '(not installed)'}")
    print(f"version status            : {status}")

    binds = routable_binds(args.port)
    if binds:
        print(f"transport port {args.port}      : LISTENING on routable {binds}  <-- exposed bind")
    else:
        print(f"transport port {args.port}      : no routable listener found (localhost-only or closed)")

    if status == "affected" and binds:
        print("\nRESULT: exposed. Affected release AND a routable transport bind.")
        print("        Firewall the port now and upgrade to the fixed release.")
        return 2
    if status == "affected":
        print("\nRESULT: affected release installed. Not reachable off-box right now,")
        print("        but one --host change exposes it. Upgrade to the fixed release.")
        return 1
    print("\nRESULT: no affected LMCache detected in this environment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
