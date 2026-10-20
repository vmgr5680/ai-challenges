"""Download and unpack the real Langflow wheels this folder inspects (no install, nothing executed).

The wheels go to `.wheels/` next to this file. Each download is checked against the
SHA-256 that PyPI publishes. Run once: `python3 wheels.py`.

Releases:
  lfx 1.10.2 / langflow-base 0.10.2   last affected (published 7 Jul 2026, with langflow 1.10.2)
  lfx 1.10.3 / langflow-base 0.10.3   first fixed   (published 23 Jul 2026, with langflow 1.10.3)
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".wheels"

AFFECTED = {"lfx": "1.10.2", "langflow-base": "0.10.2"}
FIXED = {"lfx": "1.10.3", "langflow-base": "0.10.3"}


def wheel_dir(package: str, version: str) -> Path:
    return CACHE / f"{package}-{version}"


def have_wheels() -> bool:
    return all(wheel_dir(p, v).is_dir() for rel in (AFFECTED, FIXED) for p, v in rel.items())


def fetch(package: str, version: str) -> Path:
    target = wheel_dir(package, version)
    if target.is_dir():
        return target
    with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/{version}/json", timeout=60) as r:
        meta = json.load(r)
    whl = next(u for u in meta["urls"] if u["filename"].endswith(".whl"))
    CACHE.mkdir(exist_ok=True)
    path = CACHE / whl["filename"]
    with urllib.request.urlopen(whl["url"], timeout=300) as r:
        data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != whl["digests"]["sha256"]:
        sys.exit(f"hash mismatch for {whl['filename']}")
    path.write_bytes(data)
    with zipfile.ZipFile(path) as z:
        z.extractall(target)
    print(f"  {package} {version}: {whl['filename']} sha256 {digest[:12]}... ok")
    return target


if __name__ == "__main__":
    for rel in (AFFECTED, FIXED):
        for package, version in rel.items():
            fetch(package, version)
    print("wheels ready in", CACHE)
