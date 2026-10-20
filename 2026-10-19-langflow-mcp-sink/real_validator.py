"""Run the real sink validator from the first fixed release on a few configs.

Loads `lfx/base/mcp/security.py` and `source_policy.py` (standard library only) straight
from the lfx 1.10.3 wheel, without installing lfx, and calls `validate_mcp_stdio_config`.
Nothing is launched: the validator only accepts or raises.
"""

from __future__ import annotations

import importlib.util
import sys
import types

from wheels import FIXED, fetch

CASES = [
    ("touch", ["/tmp/marker"], None),                      # the advisory's proof-of-concept shape
    ("bash", ["-c", "touch /tmp/marker"], None),           # shell wrapper around it
    ("python3", ["-c", "print('hi')"], None),              # interpreter one-liner
    ("node", ["server.js"], {"NODE_OPTIONS": "--require ./x.js"}),  # loader env var
    ("npx", ["@modelcontextprotocol/server-everything"], None),     # ordinary server
    ("uvx", ["some-unknown-package"], None),               # any package name passes by default
]


def load_validator():
    root = fetch("lfx", FIXED["lfx"])
    for name in ("lfx", "lfx.base", "lfx.base.mcp"):
        sys.modules.setdefault(name, types.ModuleType(name))
    mods = {}
    for name in ("source_policy", "security"):
        full = f"lfx.base.mcp.{name}"
        spec = importlib.util.spec_from_file_location(full, root / f"lfx/base/mcp/{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods["security"]


def run() -> list[tuple[str, str]]:
    security = load_validator()
    results = []
    print(f"lfx {FIXED['lfx']} validate_mcp_stdio_config (no env overrides set)")
    for command, args, env in CASES:
        shown = " ".join([command, *args]) + (f"  env={env}" if env else "")
        try:
            security.validate_mcp_stdio_config(command, args, env)
            verdict = "allowed"
        except security.MCPStdioSecurityError as e:
            verdict = "REJECTED: " + str(e).split(". ")[0].split(" for security")[0]
        results.append((shown, verdict))
        print(f"  {shown:<46} {verdict}")
    return results


if __name__ == "__main__":
    run()
