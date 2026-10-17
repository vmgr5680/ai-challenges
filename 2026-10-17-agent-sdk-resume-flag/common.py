"""Shared helpers: build the SDK's real CLI argv inside a pinned venv, and run the bundled CLI safely.

Nothing here talks to a model. `sdk_argv()` only calls the SDK's own
`SubprocessCLITransport._build_command()`, which builds the argument list
without starting a process. `run_bundled_cli()` runs the CLI that ships in the
venv's wheel with an empty HOME and an invalid API key, so it cannot reach an
account or read real sessions.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AFFECTED = "0.2.120"  # last release before the fix (2026-07-15)
FIXED = "0.2.121"  # first fixed release (2026-07-17)

# A harmless flag, the same one the maintainers used in PR #1123.
INJECTED = "--version"

_PROBE = r"""
import json, sys
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
opts = ClaudeAgentOptions(resume=sys.argv[1], cli_path="claude")
cmd = SubprocessCLITransport(prompt="hi", options=opts)._build_command()
print(json.dumps(cmd))
"""


def venv(version: str) -> Path:
    return HERE / f".venv-{version}"


def have_venv(version: str) -> bool:
    return (venv(version) / "bin" / "python").exists()


def sdk_argv(version: str, resume: str) -> list[str]:
    """The argv the real SDK release would pass to the CLI for this resume value."""
    py = venv(version) / "bin" / "python"
    out = subprocess.run([str(py), "-c", _PROBE, resume], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def resume_tokens(argv: list[str]) -> list[str]:
    """Just the tokens that came from the resume option (for printing)."""
    for i, tok in enumerate(argv):
        if tok == "--resume":
            return argv[i : i + 2]
        if tok.startswith("--resume="):
            return [tok]
    return []


def bundled_cli(version: str) -> Path:
    return venv(version) / "lib" / "python3.12" / "site-packages" / "claude_agent_sdk" / "_bundled" / "claude"


def run_bundled_cli(version: str, args: list[str]) -> tuple[int, str]:
    """Run the venv's bundled CLI in a throwaway HOME with no real credentials."""
    with tempfile.TemporaryDirectory() as home:
        env = {"PATH": "/usr/bin:/bin", "HOME": home, "ANTHROPIC_API_KEY": "sk-invalid"}
        p = subprocess.run(
            [str(bundled_cli(version)), *args],
            capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=60,
        )
    return p.returncode, (p.stdout + p.stderr).strip()
