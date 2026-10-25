# MCP TypeScript server SDK v2: one shared server or transport sent one client's messages to another

**CVE-2026-111770 · GHSA-jm63-cq47-j5jp · High (CVSS 7.7) · CWE-362**

When an MCP server reached over Streamable HTTP shared one `McpServer`/`Server` instance, or one stateless transport, across clients, the v2 server SDK matched responses and notifications to a connection only by JSON-RPC `id`. SDK clients number requests from 0, so ids collide in normal use, and one client can receive another client's tool results or in-progress notifications. The `@modelcontextprotocol/node`, `express`, `hono` and `fastify` READMEs showed the shared-server shape (one `McpServer` at module scope, `connect()` on a new transport per request) until the 2 Oct 2026 releases.

The v1 package `@modelcontextprotocol/sdk` fixed the same class of bug in 1.26.0 (CVE-2026-25536, GHSA-345p-7cg4-v4c7, 4 Feb 2026). The v2 split packages shipped without that guard. The fix (PR #2918, merged 2 Oct 2026) makes a second `connect()` throw `ALREADY_CONNECTED` and makes a stateless transport refuse its second request, so **upgrading alone breaks a server built the old way**: change the wiring too.

## Versions

| Package | Affected | Fixed |
|---|---|---|
| `@modelcontextprotocol/server` | `>=2.0.0 <2.3.0` (2.0.0 on 27 Jul 2026, 2.1.0 on 23 Sep, 2.2.0 on 28 Sep) | 2.3.0 (2 Oct 2026); latest 2.3.1 (5 Oct) |
| `@modelcontextprotocol/sdk` (v1) | 1.10.0 – 1.25.3 (separate advisory) | 1.26.0 |
| `@modelcontextprotocol/node` | README only | 2.1.1 (2 Oct) shows per-request wiring |

Not affected: stdio servers; `createMcpHandler()` given a factory that builds a new server per call; servers that create the `McpServer` and transport per request, or per session with `sessionIdGenerator`. Prereleases (`2.0.0-alpha.*`, `-beta.*`) were not tested here; the advisory range does not name them.

Timeline: fix merged 2 Oct 2026 → 2.3.0 published 2 Oct → repository advisory 15 Oct → reviewed into the GitHub Advisory Database 20 Oct (Dependabot alerts from here).

## Run

```bash
npm install          # pins 2.2.0 (affected) and 2.3.0 (fixed) side by side under aliases
npm run reproduce    # BEFORE
npm run fix          # AFTER
node detect.mjs /path/to/your/project
npm test             # 10 tests
```

Everything runs on 127.0.0.1 with fake notes (`card ending 1111`); no API keys, no external services.

## Files

- `app.mjs`: `startServer(sdk, mode)`, one tiny MCP server wired three ways: `shared` (old README), `shared-transport`, `per-request` (fixed README). The tool `get_account_note` logs one line naming the caller's note halfway through, then returns it.
- `scenario.mjs`: `runScenario()`, two real `@modelcontextprotocol/client` clients (Alice, Bob) call the tool 100 ms apart; a recording `fetch` keeps every JSON-RPC message each one received.
- `reproduce.mjs`, `fix.mjs`: BEFORE/AFTER. Real output in `OUTPUTS.txt`.
- `detect.mjs`: installed release check + a text heuristic for an `McpServer`/`Server` or stateless transport built at module scope in a file that serves HTTP. It reads source, it does not run it; review every hit.
- `examples/leaky`, `examples/fixed`: the README shapes before and after 2 Oct 2026.
- `tests/`: 10 tests (bug on the affected release in both shapes, refusal on the fixed release, clean per-request on both, detector).

## Why notifications leak even when responses do not

In the affected core, a request's response is sent on the transport captured when the request arrived, but `ctx.mcpReq.notify()` and other notifications go to `this._transport`, the transport connected most recently. A stateless transport routes a related message by request id, so Alice's log line (id 1) lands on Bob's open stream (also id 1). With one shared transport, the response itself is routed by id and Bob gets Alice's tool result while Alice times out.

## Links

- Advisory: https://github.com/modelcontextprotocol/typescript-sdk/security/advisories/GHSA-jm63-cq47-j5jp
- Global DB: https://github.com/advisories/GHSA-jm63-cq47-j5jp
- Fix: https://github.com/modelcontextprotocol/typescript-sdk/pull/2918
- v1 advisory: https://github.com/advisories/GHSA-345p-7cg4-v4c7
