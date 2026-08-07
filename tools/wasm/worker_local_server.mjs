/**
 * Local HTTP smoke-test harness for the temper Worker.
 *
 * Runs the Worker's real request-handling core (`createWorker` from
 * `packages/temper-worker/src/worker_core.js`) under Node's V8 — the Phase-0-
 * sanctioned workerd substitution (workerd embeds V8). This is the local
 * equivalent of what `wrangler dev` would run, without needing wrangler or a
 * Cloudflare account.
 *
 * The deployed Worker gets its `WebAssembly.Module` from the `[wasm_modules]`
 * binding in wrangler.toml; here we read the same staged .wasm file and
 * `WebAssembly.compile` it, producing the same module shape. The core logic
 * exercised is byte-for-byte the code deployed in src/.
 *
 * Usage:
 *   node tools/wasm/worker_local_server.mjs [path/to/module.wasm]
 *
 * If no path is given, the script uses the staged artifact next to the Worker
 * source (packages/temper-worker/src/temper_wasm_test_runner.wasm) — the file
 * `make wasm-worker-stage` produces and that `wrangler deploy` bundles.
 *
 * Environment:
 *   PORT        — listen port (default 8787)
 *   ABI_VERSION — expected ABI, mirrors wrangler.toml [vars] (default "1")
 */

import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";

import { createWorker } from "../../packages/temper-worker/src/worker_core.js";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const stagedWasm = join(
  repoRoot,
  "packages",
  "temper-worker",
  "src",
  "temper_wasm_test_runner.wasm",
);

const wasmPath = process.argv[2] || stagedWasm;

let bytes;
try {
  bytes = readFileSync(wasmPath);
} catch {
  console.error(`WASM module not found at: ${wasmPath}`);
  console.error("");
  console.error("Stage it first (builds the .wasm and copies it beside the Worker source):");
  console.error("  make wasm-worker-stage");
  process.exit(2);
}

const module = await WebAssembly.compile(bytes);
const worker = createWorker(module);
const env = { ABI_VERSION: process.env.ABI_VERSION || "1" };

const port = parseInt(process.env.PORT || "8787", 10);

const server = createServer(async (req, res) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = chunks.length > 0 ? Buffer.concat(chunks).toString() : null;

  const request = new Request(`http://localhost:${port}${req.url}`, {
    method: req.method,
    headers: req.headers,
    body: body || undefined,
  });

  const response = await worker.fetch(request, env);
  res.writeHead(response.status, Object.fromEntries(response.headers));
  res.end(await response.text());
});

server.listen(port, () => {
  console.error(
    `[worker-local-server] listening on http://localhost:${port} (wasm: ${bytes.length} bytes, ABI v${env.ABI_VERSION})`,
  );
});
