// AFTER: the same two clients against
//   1. the fixed release (published 2 Oct 2026) with the old shared wiring:
//      it refuses to run, so the upgrade alone breaks this server;
//   2. the per-request wiring the advisory recommends, on both releases:
//      each client sees only its own note.
//
// Run: npm run fix

import * as affected from "server-affected";
import * as fixed from "server-fixed";
import { runScenario } from "./scenario.mjs";
import { format } from "./reproduce.mjs";

console.log("AFTER\n");
console.log(format("1. fixed release, old shared wiring (A)", await runScenario(fixed, "shared")));
console.log();
console.log(format("2. fixed release, shared transport (B)", await runScenario(fixed, "shared-transport")));
console.log();
console.log(format("3. fixed release, new McpServer + transport per request", await runScenario(fixed, "per-request")));
console.log();
console.log(format("4. affected release, new McpServer + transport per request", await runScenario(affected, "per-request")));
