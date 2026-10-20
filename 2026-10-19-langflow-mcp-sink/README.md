# Langflow: MCP stdio command check at the door, not the sink (CVE-2026-105697)

Langflow can start MCP (Model Context Protocol) servers as local programs over the stdio transport, so an MCP stdio config is a command to run. From the MCP stdio component's arrival (1.1.2, January 2025), that command was not validated. Langflow 1.9.0 (14 April 2026; fix PR #12290) added a command allowlist to the REST request model `MCPServerConfig`, which stopped the "Add MCP Server" form and `/api/v2/mcp/servers` vector (GHSA-7w94-79vh-5mr2, CVE-2026-105740, published 10 Sep 2026, lists 1.9.0 as patched).

GHSA-w794-rj3p-xv45 (CVE-2026-105697, CVSS 9.9, published 28 Sep 2026, GitHub-reviewed 7 Oct 2026) says 1.9.0 to 1.10.2 stayed exploitable: configs that never pass through `MCPServerConfig` (an MCP Tools node embedded in a flow, or a value passed as a tweak) reached the launch function `MCPStdioClient._connect_to_server` unchecked. With the default `LANGFLOW_AUTO_LOGIN=true`, `/api/v1/auto_login` issues a token without credentials. 1.10.3 (PR #14036, merged 14 Jul, released 23 Jul 2026) moved the policy into `lfx.base.mcp.security.validate_mcp_stdio_config` and calls it at every entry point and inside the launcher.

## Affected and fixed

| Package | Affected | First fixed | Released |
|---|---|---|---|
| `langflow` | >= 1.1.2, < 1.10.3 | 1.10.3 (also 1.11.0, published the same day, earlier) | 2026-07-23 |
| `langflow-base` | >= 0.1.2, < 0.10.3 | 0.10.3 | 2026-07-23 |
| `lfx` | < 1.10.3 | 1.10.3 | 2026-07-23 |

Checked against the wheels: lfx 1.11.0 and 1.12.6 (latest on 2026-10-19, published 2026-10-13) also call the validator inside the launcher. `LANGFLOW_MCP_SERVER_ALLOWED_PACKAGES` (restrict which packages `npx`/`uvx` may run) exists from lfx 1.11.0; it is not in 1.10.3.

Note on the shell: the advisory says commands ran via `bash -c "exec ..."` before 1.10.3. In the lfx 1.10.2 wheel, `MCPStdioClient._connect_to_server` already tokenises with `shlex.split` and launches without a shell (and checks loader env vars), but does not validate the command. The missing piece in the last affected release is the command check at the sink.

## Run

```bash
python3 wheels.py          # download + verify the four real wheels into .wheels/ (nothing installed)
python3 reproduce.py       # BEFORE: toy model + real-release door/sink check
python3 fix.py             # AFTER: toy model with the sink check + the real 1.10.3 validator
python3 detect.py          # installed versions + settings;  --version X  /  --flows DIR
python3 -m unittest discover -s tests -v    # 10 tests (3 need the wheels, skipped without them)
```

Standard library only (Python 3.11+). See `OUTPUTS.txt` for a real run.

## Files

- `toy_app.py`: standard-library model, NOT Langflow. `api_add_server()` (door, validated), `run_flow()` (flow node config + tweaks), `launch_stdio()` (the sink), `policy_check()` (simplified copy of the real policy). Its only payload is `touch MARKER` in a temporary directory.
- `check_releases.py`: reads the real wheels with `ast`; door = `MCPServerConfig` has an allowlist, sink = `_connect_to_server` calls `validate_mcp_stdio_config` before `StdioServerParameters`.
- `real_validator.py`: loads `security.py` and `source_policy.py` from the lfx 1.10.3 wheel and calls the real validator. Nothing is launched.
- `detect.py`: version range check, `LANGFLOW_AUTO_LOGIN` and allowed-packages settings (reads the environment of the shell you run it in, so run it where the server runs), and a JSON scan for stdio configs outside the allowlist. It never connects to a server: on affected releases, listing MCP servers can start them.
- `examples/`: two illustrative, trimmed flow exports (clean and with a planted config).

## Links

- https://github.com/langflow-ai/langflow/security/advisories/GHSA-w794-rj3p-xv45
- https://github.com/langflow-ai/langflow/security/advisories/GHSA-7w94-79vh-5mr2
- https://github.com/langflow-ai/langflow/pull/12290 and https://github.com/langflow-ai/langflow/pull/14036
- https://github.com/advisories/GHSA-w794-rj3p-xv45 , https://osv.dev/vulnerability/GHSA-w794-rj3p-xv45
