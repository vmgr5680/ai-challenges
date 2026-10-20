"""Am I affected by CVE-2026-105697 (GHSA-w794-rj3p-xv45)? Standard library only.

  python3 detect.py                       # installed langflow / langflow-base / lfx + env settings
  python3 detect.py --version 1.10.2      # check a langflow version you run elsewhere
  python3 detect.py --flows ./exports     # scan exported flow / server-config JSON for stdio commands

Exit code 1 if anything is flagged. The flow scan only reads JSON; it never connects to
a server (listing MCP servers in the UI or API can start them on affected releases).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import metadata
from pathlib import Path

# (introduced, first fixed) per package, from the advisory
RANGES = {"langflow": ((1, 1, 2), (1, 10, 3)), "langflow-base": ((0, 1, 2), (0, 10, 3)), "lfx": ((0, 0, 0), (1, 10, 3))}
ALLOWED = {"node", "python", "python3", "npx", "uvx", "docker"}
WRAPPERS = {"sh", "bash", "cmd"}
INLINE = {"-c", "-e", "/c", "--eval"}


def parse(v: str) -> tuple[int, ...]:
    out = []
    for part in v.split(".")[:3]:
        lead = ""
        for ch in part:
            if not ch.isdigit():
                break
            lead += ch
        out.append(int(lead or 0))
        if lead != part:  # pre-release such as 1.10.3rc0 sorts before 1.10.3
            out[-1] -= 1
            break
    return tuple(out + [0] * (3 - len(out)))


def affected(package: str, version: str) -> bool:
    lo, hi = RANGES[package]
    return lo <= parse(version) < hi


def check_versions(explicit: str | None) -> list[str]:
    flags = []
    found = {"langflow": explicit} if explicit else {}
    if not explicit:
        for pkg in RANGES:
            try:
                found[pkg] = metadata.version(pkg)
            except metadata.PackageNotFoundError:
                pass
    if not found:
        print("versions : no langflow, langflow-base or lfx installed here (use --version)")
    for pkg, ver in found.items():
        bad = affected(pkg, ver)
        print(f"versions : {pkg} {ver} -> {'AFFECTED, upgrade to 1.10.3 or later' if bad else 'not in the affected range'}")
        if bad:
            flags.append(f"{pkg} {ver}")
    return flags


def check_env() -> list[str]:
    flags = []
    auto = os.environ.get("LANGFLOW_AUTO_LOGIN", "true (default)")
    if auto.lower().startswith("true"):
        print(f"env      : LANGFLOW_AUTO_LOGIN={auto} -> anyone who can reach the server gets a token")
        flags.append("auto-login on")
    else:
        print(f"env      : LANGFLOW_AUTO_LOGIN={auto}")
    if not os.environ.get("LANGFLOW_MCP_SERVER_ALLOWED_PACKAGES"):
        print("env      : LANGFLOW_MCP_SERVER_ALLOWED_PACKAGES unset -> npx/uvx may run any package (1.11.0+ can restrict)")
    return flags


def stdio_configs(obj, path="$"):
    """Yield (json_path, config) for every dict that looks like an MCP stdio config."""
    if isinstance(obj, dict):
        if isinstance(obj.get("command"), str) and ("args" in obj or "env" in obj):
            yield path, obj
        for k, v in obj.items():
            yield from stdio_configs(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from stdio_configs(v, f"{path}[{i}]")


def judge(config: dict) -> str | None:
    command = Path(config["command"].strip().split()[0] if config["command"].strip() else "").name
    args = [str(a) for a in config.get("args") or []]
    if command not in ALLOWED | WRAPPERS:
        return f"command {command!r} not on the allowlist"
    if command in WRAPPERS:
        return f"shell wrapper {command!r} (check what it runs)"
    if INLINE & set(args):
        return "inline code flag (-c/-e)"
    return None


def scan_flows(folder: Path) -> list[str]:
    flags = []
    files = sorted(folder.rglob("*.json"))
    print(f"flows    : scanning {len(files)} JSON file(s) under {folder}")
    for f in files:
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for where, cfg in stdio_configs(data):
            problem = judge(cfg)
            shown = " ".join([cfg["command"], *map(str, cfg.get("args") or [])])
            if problem:
                print(f"  FLAG {f.name}: {shown!r} -> {problem}\n       at {where}")
                flags.append(f"{f.name}: {shown}")
            else:
                print(f"  ok   {f.name}: {shown!r}")
    return flags


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="langflow version to check instead of the installed one")
    ap.add_argument("--flows", type=Path, help="folder of exported flow or MCP server JSON")
    a = ap.parse_args(argv)
    flags = check_versions(a.version) + check_env()
    if a.flows:
        flags += scan_flows(a.flows)
    print(f"result   : {len(flags)} finding(s)")
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
