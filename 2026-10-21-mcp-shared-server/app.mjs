// A tiny MCP server over Streamable HTTP, wired two ways.
//
//   startServer(sdk, "shared")      one McpServer at module scope, a new stateless
//                                   transport per request: the shape the
//                                   @modelcontextprotocol/node README showed until
//                                   the 2 Oct 2026 releases.
//   startServer(sdk, "shared-transport") one McpServer and one stateless transport
//                                   created at startup and reused for every request.
//   startServer(sdk, "per-request") a new McpServer and transport inside every
//                                   request: the shape the fixed README shows.
//
// `sdk` is the real @modelcontextprotocol/server module (affected or fixed release).
// The only tool, get_account_note, logs a progress line that names the caller's
// fake note halfway through a short "database" delay, then returns the note.
// Nothing leaves 127.0.0.1.

import { createServer } from "node:http";
import { z } from "zod";

export const NOTES = {
  alice: "alice: invoice #A-1001, card ending 1111",
  bob: "bob: invoice #B-2002, card ending 2222",
};

function buildServer(sdk) {
  const server = new sdk.McpServer({ name: "notes", version: "1.0.0" }, { capabilities: { logging: {} } });
  server.registerTool(
    "get_account_note",
    { description: "Return the caller's account note", inputSchema: z.object({ user: z.string(), delayMs: z.number() }) },
    async ({ user, delayMs }, ctx) => {
      await new Promise((r) => setTimeout(r, delayMs / 2));
      await ctx.mcpReq.notify({ method: "notifications/message", params: { level: "info", data: `loaded ${NOTES[user]}` } });
      await new Promise((r) => setTimeout(r, delayMs / 2));
      return { content: [{ type: "text", text: NOTES[user] ?? "unknown user" }] };
    },
  );
  return server;
}

async function toWebRequest(req, port) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const headers = new Headers();
  for (const [k, v] of Object.entries(req.headers)) if (typeof v === "string") headers.set(k, v);
  const init = { method: req.method, headers };
  if (req.method !== "GET" && req.method !== "HEAD") init.body = Buffer.concat(chunks);
  return new Request(`http://127.0.0.1:${port}${req.url}`, init);
}

async function sendWebResponse(res, response) {
  res.writeHead(response.status, Object.fromEntries(response.headers));
  if (response.body) for await (const chunk of response.body) res.write(chunk);
  res.end();
}

export function startServer(sdk, mode) {
  const errors = [];
  const shared = mode === "per-request" ? null : buildServer(sdk);
  let sharedTransport = null;
  const http = createServer(async (req, res) => {
    try {
      const server = shared ?? buildServer(sdk);
      let transport = sharedTransport;
      if (!transport) {
        transport = new sdk.WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined });
        await server.connect(transport);
        if (mode === "shared-transport") sharedTransport = transport;
      }
      const response = await transport.handleRequest(await toWebRequest(req, http.address().port));
      await sendWebResponse(res, response);
    } catch (err) {
      errors.push(`${err.code ?? err.name}: ${err.message}`);
      if (!res.headersSent) res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ jsonrpc: "2.0", id: null, error: { code: -32603, message: String(err.message) } }));
    }
  });
  return new Promise((resolve) =>
    http.listen(0, "127.0.0.1", () => resolve({ http, port: http.address().port, errors })),
  );
}
