// BEFORE: the affected release (published 28 Sep 2026), wired the way the
// @modelcontextprotocol/node README showed until 2 Oct 2026, and with one shared
// stateless transport. Two real SDK clients call the same tool at the same time.
//
// Run: npm run reproduce

import * as affected from "server-affected";
import { runScenario } from "./scenario.mjs";

export function format(label, r) {
  const lines = [label];
  for (const who of ["alice", "bob"]) {
    const other = who === "alice" ? "bob" : "alice";
    const leaked = r.seen[who].includes(other) ? `  <- received ${other}'s note` : "";
    lines.push(`  ${who.padEnd(5)} tool result: ${r.result[who]}`);
    lines.push(`  ${who.padEnd(5)} notes seen  : ${r.seen[who].join(", ") || "none"}${leaked}`);
  }
  for (const e of r.serverErrors) lines.push(`  server error: ${e}`);
  return lines.join("\n");
}

if (import.meta.url === `file://${process.argv[1]}`) {
  console.log("BEFORE: affected release, published 28 Sep 2026\n");
  console.log(format("A. one McpServer at module scope, new transport per request (old README)", await runScenario(affected, "shared")));
  console.log();
  console.log(format("B. one McpServer and one stateless transport for every request", await runScenario(affected, "shared-transport")));
}
