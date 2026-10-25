// Two real SDK clients, Alice and Bob, each ask the same server for their own note.
// Alice's call starts first (600 ms tool, logs at 300 ms); Bob's starts 100 ms later
// (600 ms tool, logs at 400 ms). Each client numbers its requests from 0, so both
// tool calls carry the same JSON-RPC id. runScenario() records every JSON-RPC
// message each client actually received over HTTP, then reports who saw whose note.

import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import { startServer, NOTES } from "./app.mjs";

function recordingFetch(log) {
  return async (url, init) => {
    const res = await fetch(url, init);
    const text = await res.clone().text();
    for (const line of text.split("\n")) {
      const body = line.startsWith("data:") ? line.slice(5).trim() : line.trim();
      if (!body.startsWith("{")) continue;
      try { log.push(JSON.parse(body)); } catch { /* not JSON */ }
    }
    return res;
  };
}

async function connectClient(name, port, log) {
  const client = new Client({ name, version: "1.0.0" });
  const transport = new StreamableHTTPClientTransport(new URL(`http://127.0.0.1:${port}/mcp`), { fetch: recordingFetch(log) });
  await client.connect(transport);
  return client;
}

async function call(client, user, delayMs, timeoutMs) {
  try {
    const r = await client.callTool({ name: "get_account_note", arguments: { user, delayMs } }, { timeout: timeoutMs });
    return r.content?.[0]?.text ?? JSON.stringify(r);
  } catch (err) {
    return `ERROR ${err.code ?? ""} ${String(err.message).split("\n")[0]}`.replace(/\s+/g, " ").trim();
  }
}

// Which users' notes appear anywhere in the messages a client received?
export function notesSeen(messages) {
  const text = JSON.stringify(messages);
  return Object.entries(NOTES).filter(([, note]) => text.includes(note)).map(([user]) => user);
}

export async function runScenario(sdk, mode, { timeoutMs = 2000 } = {}) {
  const { http, port, errors } = await startServer(sdk, mode);
  const logs = { alice: [], bob: [] };
  try {
    let alice, bob;
    try {
      alice = await connectClient("alice", port, logs.alice);
      bob = await connectClient("bob", port, logs.bob);
    } catch {
      return { mode, result: { alice: "ERROR could not connect", bob: "ERROR could not connect" },
               seen: { alice: [], bob: [] }, serverErrors: [...new Set(errors)] };
    }
    const aliceP = call(alice, "alice", 600, timeoutMs);
    await new Promise((r) => setTimeout(r, 100));
    const bobP = call(bob, "bob", 600, timeoutMs);
    const [a, b] = await Promise.all([aliceP, bobP]);
    await Promise.allSettled([alice.close(), bob.close()]);
    return { mode, result: { alice: a, bob: b },
             seen: { alice: notesSeen(logs.alice), bob: notesSeen(logs.bob) },
             messages: logs, serverErrors: [...new Set(errors)] };
  } finally {
    http.closeAllConnections?.();
    await new Promise((r) => http.close(r));
  }
}
