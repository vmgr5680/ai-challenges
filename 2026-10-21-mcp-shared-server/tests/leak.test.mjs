// Bug and fix, against the real affected (28 Sep 2026) and fixed (2 Oct 2026) releases.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as affected from "server-affected";
import * as fixed from "server-fixed";
import { runScenario } from "../scenario.mjs";

test("affected release, shared McpServer (old README): Bob receives Alice's log line", async () => {
  const r = await runScenario(affected, "shared");
  assert.deepEqual(r.seen.bob.sort(), ["alice", "bob"]);
  assert.match(r.result.alice, /^alice:/);
});

test("affected release, shared transport: Bob's tool result is Alice's note", async () => {
  const r = await runScenario(affected, "shared-transport");
  assert.match(r.result.bob, /^alice:/);
  assert.match(r.result.alice, /ERROR/);
});

test("fixed release refuses a second connect on a shared McpServer", async () => {
  const r = await runScenario(fixed, "shared");
  assert.ok(r.serverErrors.some((e) => e.startsWith("ALREADY_CONNECTED")));
  assert.deepEqual(r.seen, { alice: [], bob: [] });
});

test("fixed release refuses to reuse a stateless transport", async () => {
  const r = await runScenario(fixed, "shared-transport");
  assert.ok(r.serverErrors.some((e) => e.includes("Stateless transport cannot be reused")));
});

for (const [name, sdk] of [["fixed", fixed], ["affected", affected]]) {
  test(`${name} release, per-request wiring: each client sees only its own note`, async () => {
    const r = await runScenario(sdk, "per-request");
    assert.deepEqual(r.seen, { alice: ["alice"], bob: ["bob"] });
    assert.match(r.result.alice, /^alice:/);
    assert.match(r.result.bob, /^bob:/);
  });
}
