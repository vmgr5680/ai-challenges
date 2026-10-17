"""Am I affected by GHSA-qx49-fqc8-xw99? Standard library only.

    python3 detect.py                 # check the installed `mcp` package
    python3 detect.py path/to/code    # also scan Python files for the follow-up steps

Functions, in article order:
    is_affected_version()  the advisory's affected ranges
    installed_version()    the `mcp` version in this interpreter, if any
    scan_source()          OAuth providers that still need a code change after upgrading
"""

import ast
import re
import sys
from importlib import metadata
from pathlib import Path

ISSUER_REQUIRED = {"ClientCredentialsOAuthProvider", "PrivateKeyJWTOAuthProvider"}
MIGRATE = {"RFC7523OAuthClientProvider"}
CLEAR_STORAGE = {"OAuthClientProvider"}


def _parse(v: str) -> tuple[int, int, int, bool]:
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?(.*)", v)
    if not m:
        raise ValueError(f"unrecognised version {v!r}")
    major, minor, patch, rest = int(m[1]), int(m[2]), int(m[3] or 0), m[4]
    return major, minor, patch, bool(re.match(r"\.?(a|b|rc|dev)", rest))


def is_affected_version(v: str) -> bool:
    """Affected: 1.9.1 up to (not incl.) 1.30.0, and 2.0.0a1 up to (not incl.) 2.2.0."""
    major, minor, patch, _pre = _parse(v)
    if major == 1:
        return (1, 9, 1) <= (major, minor, patch) < (1, 30, 0)
    if major == 2:
        return (major, minor, patch) < (2, 2, 0)   # every 2.x pre-release counts as 2.0.0
    return False


def installed_version() -> str | None:
    try:
        return metadata.version("mcp")
    except metadata.PackageNotFoundError:
        return None


def scan_source(root: Path) -> list[str]:
    findings = []
    files = [root] if root.is_file() else sorted(root.rglob("*.py"))
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            kwargs = {k.arg for k in node.keywords}
            where = f"{f}:{node.lineno}"
            if name in ISSUER_REQUIRED and "issuer" not in kwargs:
                findings.append(f"{where}  {name} without issuer=  -> pass your authorization server's issuer URL")
            elif name in MIGRATE:
                findings.append(f"{where}  {name} has no issuer option  -> migrate to PrivateKeyJWTOAuthProvider(issuer=...)")
            elif name in CLEAR_STORAGE:
                findings.append(f"{where}  {name}  -> after upgrading, clear stored client info once so it re-registers")
    return findings


def main(argv: list[str]) -> int:
    v = installed_version()
    if v is None:
        print("mcp: not installed in this interpreter")
        affected = False
    else:
        affected = is_affected_version(v)
        print(f"mcp {v}: {'AFFECTED - upgrade' if affected else 'not in the affected range'}")
    findings = []
    for arg in argv:
        findings += scan_source(Path(arg))
    for line in findings:
        print(line)
    if argv and not findings:
        print("source: no OAuth providers needing follow-up found")
    return 1 if affected or findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
