// detect.mjs: is this project exposed to GHSA-jm63-cq47-j5jp (CVE-2026-111770)?
//
//   node detect.mjs <project-dir>
//
// 1. Which @modelcontextprotocol/server release is installed (node_modules, then
//    package-lock.json)? Printed by publish date; affected = 2.0.0 up to 2.2.x.
// 2. Which source files build an McpServer / Server or a Streamable HTTP server
//    transport at module scope (not inside a function) in a file that serves HTTP?
//    That is the shared shape. It is a heuristic: it reads text, it does not run code.
//
// Exit code 1 if an affected release or a shared shape was found.

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, relative } from "node:path";

const RELEASES = {
  "2.0.0": "27 Jul 2026", "2.1.0": "23 Sep 2026", "2.2.0": "28 Sep 2026",
  "2.3.0": "2 Oct 2026", "2.3.1": "5 Oct 2026",
};

export function isAffected(version) {
  const m = /^2\.(\d+)\.\d+/.exec(version ?? "");
  return Boolean(m) && Number(m[1]) < 3;
}

export function installedVersion(dir) {
  const pkg = join(dir, "node_modules/@modelcontextprotocol/server/package.json");
  if (existsSync(pkg)) return JSON.parse(readFileSync(pkg, "utf8")).version;
  const lock = join(dir, "package-lock.json");
  if (existsSync(lock)) {
    const l = JSON.parse(readFileSync(lock, "utf8"));
    return l.packages?.["node_modules/@modelcontextprotocol/server"]?.version;
  }
  return undefined;
}

const SERVER_RE = /\bnew\s+(McpServer|Server)\s*\(/;
const TRANSPORT_RE = /\bnew\s+(WebStandardStreamableHTTPServerTransport|NodeStreamableHTTPServerTransport|StreamableHTTPServerTransport)\s*\(/;
const HTTP_RE = /StreamableHTTPServerTransport|createMcpHandler|createServer\s*\(|express\s*\(|createMcp\w*App\s*\(|new\s+Hono\s*\(|fastify\s*\(/;

// Lines at brace depth 0 are module scope. Strings and comments are stripped first,
// so braces inside them do not count.
export function sharedShapes(source) {
  const findings = [];
  if (!HTTP_RE.test(source)) return findings;
  const clean = source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/\/\/[^\n]*/g, "")
    .replace(/(["'`])(?:\\.|(?!\1)[^\\\n])*\1/g, '""');
  let depth = 0;
  clean.split("\n").forEach((line, i) => {
    if (depth === 0) {
      if (SERVER_RE.test(line)) findings.push({ line: i + 1, kind: "server built at module scope" });
      if (TRANSPORT_RE.test(line) && !/sessionIdGenerator\s*:\s*\(/.test(source))
        findings.push({ line: i + 1, kind: "stateless transport built at module scope" });
    }
    for (const ch of line) depth += ch === "{" ? 1 : ch === "}" ? -1 : 0;
    if (depth < 0) depth = 0;
  });
  return findings;
}

function* sourceFiles(dir) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith(".")) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* sourceFiles(p);
    else if (/\.(m|c)?[jt]sx?$/.test(name)) yield p;
  }
}

export function scan(dir) {
  const version = installedVersion(dir);
  const files = [];
  for (const f of sourceFiles(dir)) {
    const hits = sharedShapes(readFileSync(f, "utf8"));
    if (hits.length) files.push({ file: relative(dir, f), hits });
  }
  return { version, affected: isAffected(version), files };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const dir = process.argv[2] ?? ".";
  const { version, affected, files } = scan(dir);
  const when = version ? (RELEASES[version] ? `release of ${RELEASES[version]}` : `version ${version}`) : "not found";
  console.log(`@modelcontextprotocol/server installed: ${when} -> ${version ? (affected ? "AFFECTED, upgrade" : "fixed release") : "n/a"}`);
  if (!files.length) console.log("shared server/transport at module scope: none found");
  for (const { file, hits } of files) for (const h of hits) console.log(`SHARED  ${file}:${h.line}  ${h.kind}`);
  if (files.length) console.log("-> create the McpServer and transport per request, or per session with sessionIdGenerator");
  process.exitCode = affected || files.length ? 1 : 0;
}
