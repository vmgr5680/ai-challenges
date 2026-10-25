import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isAffected, sharedShapes, installedVersion } from "../detect.mjs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("version check: 2.0.0 to 2.2.x affected, 2.3.0+ and 1.x not", () => {
  for (const v of ["2.0.0", "2.1.0", "2.2.0"]) assert.equal(isAffected(v), true, v);
  for (const v of ["2.3.0", "2.3.1", "1.26.0", undefined]) assert.equal(isAffected(v), false, String(v));
});

test("flags the old README shape", () => {
  const hits = sharedShapes(read("../examples/leaky/server.mjs"));
  assert.equal(hits.length, 1);
  assert.equal(hits[0].kind, "server built at module scope");
});

test("does not flag the per-request shape", () => {
  assert.deepEqual(sharedShapes(read("../examples/fixed/server.mjs")), []);
});

test("aliased installs in this repo are not mistaken for the real package name", () => {
  // This project installs the SDK under aliases, so the real name is not in node_modules.
  assert.equal(installedVersion(new URL("..", import.meta.url).pathname), undefined);
});
