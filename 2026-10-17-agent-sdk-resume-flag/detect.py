"""Check a project for CVE-2026-96620 / GHSA-h4mw-j7qp-8mwm exposure. Standard library only.

Usage:  python3 detect.py [PROJECT_DIR ...]

It reports three things:
  1. Python installs of claude-agent-sdk older than 0.2.121 (any *.dist-info under the dir,
     so venvs inside the project are covered). Older than 0.2.124 also gets a note:
     that release bound dash-leading `extra_args` values the same way.
  2. npm installs of @anthropic-ai/claude-agent-sdk older than 0.3.208, the TypeScript
     release with the same fix. It has no advisory, so scanners stay silent about it.
  3. Code that passes a non-literal value to resume=, session_id= or extra_args=
     (Python) or resume:, sessionId:, extraArgs: (TypeScript). These are the lines
     to review: where does that value come from?
Exit code 1 if anything in 1 or 2 is found, else 0.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

PY_FIXED, PY_EXTRA_ARGS_FIXED = (0, 2, 121), (0, 2, 124)
TS_FIXED = (0, 3, 208)
SKIP = {".git", "__pycache__"}
PY_KEYS = {"resume", "session_id", "extra_args"}
TS_RE = re.compile(r"\b(resume|sessionId|extraArgs)\s*:\s*(?!['\"`]|undefined\b|null\b|string\b|Record\b)([A-Za-z_$][\w$.\[\]'\"]*)")


def vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def py_installs(root: Path):
    for d in root.rglob("claude_agent_sdk-*.dist-info"):
        yield d.parent, d.name.removesuffix(".dist-info").split("-")[1]


def npm_installs(root: Path):
    for pj in root.rglob("node_modules/@anthropic-ai/claude-agent-sdk/package.json"):
        yield pj.parent, json.loads(pj.read_text())["version"]


def py_call_sites(root: Path):
    for f in root.rglob("*.py"):
        if any(p in SKIP or p.startswith(".venv") or p == "site-packages" for p in f.parts):
            continue
        try:
            tree = ast.parse(f.read_text(), str(f))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in PY_KEYS and not isinstance(kw.value, ast.Constant):
                        yield f, kw.value.lineno, kw.arg, ast.unparse(kw.value)


def ts_call_sites(root: Path):
    for f in root.rglob("*.[tj]s"):
        if "node_modules" in f.parts or any(p in SKIP for p in f.parts):
            continue
        for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            for m in TS_RE.finditer(line):
                yield f, n, m.group(1), m.group(2)


def short(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def scan(root: Path) -> int:
    found = 0
    for where, v in py_installs(root):
        if vtuple(v) < PY_FIXED:
            found += 1
            print(f"AFFECTED  claude-agent-sdk {v} (Python) in {short(where, root)}  -> upgrade")
        elif vtuple(v) < PY_EXTRA_ARGS_FIXED:
            print(f"NOTE      claude-agent-sdk {v} (Python) in {short(where, root)}  -> fixed for resume; extra_args binding fixed in 0.2.124")
        else:
            print(f"ok        claude-agent-sdk {v} (Python) in {short(where, root)}")
    for where, v in npm_installs(root):
        if vtuple(v) < TS_FIXED:
            found += 1
            print(f"AFFECTED  @anthropic-ai/claude-agent-sdk {v} (npm) in {short(where, root)}  -> upgrade (no advisory exists for npm)")
        else:
            print(f"ok        @anthropic-ai/claude-agent-sdk {v} (npm) in {short(where, root)}")
    for f, line, key, expr in [*py_call_sites(root), *ts_call_sites(root)]:
        print(f"REVIEW    {f.relative_to(root)}:{line}  {key} = {expr}  (where does this value come from?)")
    return found


if __name__ == "__main__":
    roots = [Path(p).resolve() for p in sys.argv[1:]] or [Path.cwd()]
    sys.exit(1 if sum(scan(r) for r in roots) else 0)
