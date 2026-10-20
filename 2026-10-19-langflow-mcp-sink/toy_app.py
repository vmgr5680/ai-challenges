"""A toy, standard-library model of the bug's shape: one check at the door, three ways in.

This is NOT Langflow. It models the structure the advisory describes so the BEFORE and
AFTER can run offline in milliseconds:

  api_add_server()  the REST door: validates the config (like MCPServerConfig since 1.9.0)
  run_flow()        a flow whose MCP Tools node carries its own config, plus tweaks
                    merged in at run time; never passes through the door
  launch_stdio()    the sink: the one function that starts the server process

`launch_stdio` runs the command with no shell, inside a temporary working directory,
and the only "payload" used anywhere in this folder is `touch MARKER`, which creates an
empty file there. That file appearing is the proof that the command ran.

`policy_check` is a simplified copy of the real policy's main rules (command allowlist,
no -c/-e one-liners, no loader env vars). The real validator is exercised in
real_validator.py.
"""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

ALLOWED = {"node", "python", "python3", "npx", "uvx", "docker"}
BLOCKED_ARGS = {"-c", "-e", "/c"}
BLOCKED_ENV = {"LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS", "PYTHONPATH", "BASH_ENV"}
MARKER = "MARKER"


class PolicyError(ValueError):
    pass


def policy_check(config: dict) -> None:
    command = Path(config.get("command", "")).name
    if command not in ALLOWED:
        raise PolicyError(f"command {command!r} is not allowed")
    if BLOCKED_ARGS & set(config.get("args", [])):
        raise PolicyError("inline code flags (-c/-e) are not allowed")
    bad_env = BLOCKED_ENV & {k.upper() for k in config.get("env", {})}
    if bad_env:
        raise PolicyError(f"env var {sorted(bad_env)[0]} is not allowed")


class ToyApp:
    def __init__(self, workdir: Path, validate_at_sink: bool) -> None:
        self.workdir = workdir
        self.validate_at_sink = validate_at_sink
        self.servers: dict[str, dict] = {}
        self.launched: list[list[str]] = []

    # --- the sink -------------------------------------------------------------
    def launch_stdio(self, config: dict) -> str:
        if self.validate_at_sink:
            policy_check(config)
        argv = [config["command"], *config.get("args", [])]
        if argv[0] in ("python", "python3"):
            argv[0] = sys.executable
        self.launched.append(argv)
        subprocess.run(argv, cwd=self.workdir, check=False, capture_output=True, timeout=10)
        return "launched"

    # --- way in 1: the REST door ---------------------------------------------
    def api_add_server(self, name: str, config: dict) -> str:
        policy_check(config)  # the 1.9.0 fix lives here
        self.servers[name] = config
        return self.launch_stdio(config)  # listing/connecting starts it

    # --- ways in 2 and 3: a flow's own node config, and run-time tweaks --------
    def run_flow(self, flow: dict, tweaks: dict | None = None) -> str:
        node = copy.deepcopy(flow["nodes"]["MCPTools-1"])
        node.update((tweaks or {}).get("MCPTools-1", {}))
        return self.launch_stdio(node["mcp_server"]["config"])


def marker_written(workdir: Path) -> bool:
    return (workdir / MARKER).exists()


TOUCH = {"command": "touch", "args": [MARKER]}
GOOD = {"command": "python3", "args": ["fake_mcp_server.py"]}


def flow_with(config: dict) -> dict:
    return {"nodes": {"MCPTools-1": {"mcp_server": {"name": "notes", "config": config}}}}


def attempt(app: ToyApp, label: str, fn) -> str:
    try:
        result = fn()
    except PolicyError as e:
        result = f"rejected ({e})"
    ran = "yes" if marker_written(app.workdir) else "no"
    print(f"  {label:<38} -> {result:<48} MARKER on disk: {ran}")
    (app.workdir / MARKER).unlink(missing_ok=True)
    return result


def run_all(validate_at_sink: bool, workdir: Path) -> dict[str, str]:
    (workdir / "fake_mcp_server.py").write_text("print('fake MCP server started')\n")
    app = ToyApp(workdir, validate_at_sink)
    return {
        "api": attempt(app, "1. REST API: add server 'touch'", lambda: app.api_add_server("x", TOUCH)),
        "flow": attempt(app, "2. flow JSON with 'touch' in its node", lambda: app.run_flow(flow_with(TOUCH))),
        "tweak": attempt(
            app,
            "3. clean flow + run-time tweak",
            lambda: app.run_flow(
                flow_with(GOOD), {"MCPTools-1": {"mcp_server": {"name": "notes", "config": TOUCH}}}
            ),
        ),
        "good": attempt(app, "4. clean flow, allowed server", lambda: app.run_flow(flow_with(GOOD))),
    }
