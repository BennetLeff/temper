#!/usr/bin/env node
/**
 * Local smoke-test server for the per-family multi-module Worker.
 *
 * Loads all WASM modules from disk (matching the wrangler-bundled
 * module name convention) and starts an HTTP server on PORT (default 8797).
 *
 * Usage:
 *   PORT=8797 node tools/wasm/local_family_server.mjs
 */

import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const WORKER_SRC = join(REPO_ROOT, "packages", "temper-worker", "src");

function loadModule(name) {
  const buf = readFileSync(join(WORKER_SRC, name));
  return new WebAssembly.Module(buf);
}

// Mirrors packages/temper-worker/src/index.js — the temper-wasm-tier Worker —
// and so deliberately does NOT include `geometry`. temper-geometry is its own
// tier and its own Worker (packages/temper-worker/families/geometry), carrying
// its own expected-failure manifest; folding it in here would model a Worker
// that does not exist and would judge geometry's tests against temper-drc-rs's
// manifest. Serve it with `tools/wasm/worker_local_server.mjs` against
// temper_wasm_test_runner_geometry.wasm instead. See
// tools/wasm/wasm_tier_topology.json.
const FAMILY_ORDER = ["drc", "emc", "erc", "safety", "placement", "routing", "infra"];
const modules = {
  default: loadModule("temper_wasm_test_runner.wasm"),
};
for (const fam of FAMILY_ORDER) {
  modules[fam] = loadModule(`temper_wasm_test_runner_${fam}.wasm`);
}

// Dynamic import because worker_core.js is ESM and uses exports
const { createMultiFamilyWorker } = await import(join(WORKER_SRC, "worker_core.js"));

const worker = createMultiFamilyWorker(modules);
const PORT = parseInt(process.env.PORT || "8797", 10);

const server = createServer(async (req, res) => {
  // Build a minimal Request-like object for the worker
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const headers = new Headers();
  for (const [k, v] of Object.entries(req.headers)) {
    if (v) headers.set(k, Array.isArray(v) ? v.join(", ") : v);
  }
  const body = req.method === "POST" || req.method === "PUT"
    ? await readBody(req) : undefined;
  
  const request = new Request(url, { method: req.method, headers, body });
  
  const response = await worker.fetch(request, { ABI_VERSION: "1" });
  
  res.writeHead(response.status, Object.fromEntries(response.headers));
  const respBody = await response.text();
  res.end(respBody);
});

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", chunk => data += chunk);
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

server.listen(PORT, () => {
  console.log(`Multi-family worker listening on http://localhost:${PORT}`);
  console.log(`  Families: ${Object.keys(modules).join(", ")}`);
  console.log(`  Try: curl http://localhost:${PORT}/families`);
});
