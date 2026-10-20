"""Real-release evidence: where does each Langflow release check the MCP stdio command?

Reads the source inside the real wheels (see wheels.py) with `ast`; nothing is installed
or executed. For each release it answers two questions:

  door : does the REST model (`MCPServerConfig` in langflow-base) have a command allowlist?
  sink : does `MCPStdioClient._connect_to_server` in lfx, the function that starts the
         process, call `validate_mcp_stdio_config` before it builds the launch parameters?
"""

from __future__ import annotations

import ast
from pathlib import Path

from wheels import AFFECTED, FIXED, fetch


def door_has_allowlist(base_dir: Path) -> bool:
    src = (base_dir / "langflow/api/v2/schemas.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MCPServerConfig":
            body = ast.unparse(node)
            return "ALLOWED_MCP_COMMANDS" in body or "validate_mcp_stdio_config" in body
    return False


def sink_calls(lfx_dir: Path) -> list[str]:
    """Names of the functions `_connect_to_server` calls, in order."""
    tree = ast.parse((lfx_dir / "lfx/base/mcp/util.py").read_text())
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == "MCPStdioClient":
            for fn in cls.body:
                if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "_connect_to_server":
                    calls = []
                    for n in ast.walk(fn):
                        if isinstance(n, ast.Call):
                            f = n.func
                            calls.append(f.id if isinstance(f, ast.Name) else getattr(f, "attr", "?"))
                    return calls
    raise LookupError("MCPStdioClient._connect_to_server not found")


def sink_validates(lfx_dir: Path) -> bool:
    calls = sink_calls(lfx_dir)
    if "validate_mcp_stdio_config" not in calls:
        return False
    return calls.index("validate_mcp_stdio_config") < calls.index("StdioServerParameters")


def report() -> dict[str, tuple[bool, bool]]:
    results = {}
    for label, rel in (("last affected, published 7 Jul 2026", AFFECTED), ("first fixed, published 23 Jul 2026", FIXED)):
        door = door_has_allowlist(fetch("langflow-base", rel["langflow-base"]))
        sink = sink_validates(fetch("lfx", rel["lfx"]))
        results[rel["lfx"]] = (door, sink)
        print(label)
        print(f"  door  MCPServerConfig command allowlist   : {'yes' if door else 'NO'}")
        print(f"  sink  _connect_to_server validates command: {'yes' if sink else 'NO'}")
    return results


if __name__ == "__main__":
    report()
