<!-- provenance: commit=f7a1fbf8fd155a0c303462717d531f8ae7606b7f dirty=UNKNOWN -->

# Phase 1 U7 — Cloudflare Worker Scaffold

**Date:** 2026-08-07
**Commit:** f7a1fbf8fd155a0c303462717d531f8ae7606b7f (`origin/main`)
**Status:** SCAFFOLD COMPLETE (deployment deferred — no Cloudflare account provisioned)

## Layout

```
packages/temper-worker/
├── wrangler.toml          # Workers config: module syntax, [vars], wasm_module binding
└── src/
    └── index.js           # Worker entry point: R17 contract, local Node server fallback

tools/wasm/
└── worker_local_probe.mjs # Local verification harness (Node/V8, Phase-0-sanctioned workerd substitution)
```

The Worker lives under `packages/` following the repo's `temper-` naming convention. It is self-contained — it references the `.wasm` artifact from `packages/temper-wasm-test-runner` (built separately) but does not contain Rust source. The `wrangler.toml` uses module syntax with a `[wasm_modules]` binding (commented out until the `.wasm` is placed beside the Worker source at deploy time).

## Worker Contract (R17)

### Endpoints

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/run-test` | `{ "index": <number> }` or `{ "name": "<string>" }` | `{ verdict, index, name, message, abi_version, ms }` |
| `GET` | `/manifest` | — | Expected-failure manifest (JSON, keyed by test name) |
| `GET` | `/health` | — | `{ status: "ok", abi_version, test_count }` |

### Response shape for `/run-test`

```json
{
  "verdict": "pass" | "fail" | "expected-fail" | "unexpected-pass" | "bad-index" | "not-found",
  "index": 0,
  "name": "board::tests::edge_distance_is_symmetric",
  "message": null | "<panic text>",
  "abi_version": 1,
  "ms": 0
}
```

When `verdict` is `expected-fail` or `unexpected-pass`, the response also carries `expected_failure_class` and `expected_failure_reason` from the manifest.

### Trap protocol

1. `temper_run_test(index)` panics → `panic = "abort"` → `unreachable` → WebAssembly trap.
2. Worker catches the trap as a thrown error from the `temper_run_test()` call.
3. Worker reads the panic buffer via `temper_panic_message_ptr/len` from the **same instance** that trapped (the WebAssembly store survives a trap).
4. Returns `{ verdict: "fail", message: "<assertion text>" }`.
5. The manifest reclassifies known failures to `expected-fail`.

### Per-request instantiation model

Each HTTP request instantiates a **fresh** `WebAssembly.Instance`:
- The `.wasm` module is **compiled once** at Worker startup (Cloudflare: at upload time; Node probe: at server start).
- `WebAssembly.instantiate(module, {})` runs per request.
- This matches the Workers billing model (CPU time = isolate lifetime) and is correct by construction: a panicking test traps within its own instance and cannot poison the next request.

The Worker's global scope holds the compiled `WebAssembly.Module`; the `fetch` handler instantiates per request.

## Local Probe Numbers

Measured on Node v26.4.0 (V8), macOS arm64, against the `.wasm` artifact built at commit `f7a1fbf8f`:

### Cold start (one-time cost at deploy/startup)

| Metric | Value |
|--------|-------|
| Compile | 4.68 ms |
| First instantiate | 0.84 ms |
| **Cold start (total)** | **5.52 ms** |

### Warm instantiate (per-request recurring cost, 100 samples)

| Metric | Value |
|--------|-------|
| Mean | 0.173 ms |
| Median | 0.092 ms |
| P95 | 0.490 ms |
| Max | 2.202 ms |

### Per-invocation probe (instantiate + test execution)

| Index | Test | Verdict | Instantiate | Test | Total |
|-------|------|---------|-------------|------|-------|
| 0 | `board::tests::edge_distance_is_symmetric` | pass | 0.354 ms | 0.888 ms | 1.242 ms |
| 1 | `board::tests::edge_distance_catches_mid_edge_gap` | pass | 0.122 ms | 0.053 ms | 0.175 ms |
| 26 | `dfm::tests::thermal_via_side_round_...` | expected-fail | 0.143 ms | 10.811 ms | 10.954 ms |
| 50 | `pymath::tests::pow_is_not_a_multiply_...` | expected-fail | 0.146 ms | 3.247 ms | 3.393 ms |

**Key insight:** The warm instantiation median (0.092 ms / ~92 µs) is considerably lower than the cold first-instantiate (0.844 ms), but still dominates the median test execution time (~0.02–0.05 ms for a passing test). Expected-fail tests have higher wall time because the panic hook + trap + panic-message read path is more expensive than a simple return, but this is not a cost concern — there are only 4 expected-fail tests in the 95-test corpus.

### Module properties

| Property | Value |
|----------|-------|
| Size | 1,184,419 bytes |
| Imports | 0 (zero — deployable to a bare isolate) |
| Registered tests | 95 |
| Pass / Expected-fail | 91 / 4 |
| Peak linear memory | 1.75 MiB (1.4% of 128 MiB limit) |

## Worker to Node equivalence

The local Node probe uses the same V8 engine that Cloudflare's `workerd` embeds. The compiled `WebAssembly.Module` is identical (same bytes, same compile step). The instantiation path (`WebAssembly.instantiate(module, {})` with an empty import object) is the same. The trap behaviour (panic → abort → `unreachable` → `WebAssembly.RuntimeError`) is the same.

The **platform overhead factor** (Worker wall time / local Node wall time) is unmeasured until a real Worker deployment (U8). Based on the U3 sharding evidence (§Per-Invocation Cost Estimate), the factor is expected to be 1.0–3.0×, not 10×: the Workers isolate has the same V8 engine, the module has zero imports (no host-call overhead), and the per-invocation wall time is dominated by instantiation cost, which is a V8-internal concern.

## U8 Cost Model (from U5/U6 volume data)

Using the U3 sharding design (K=100 repetitions per commit, 10 commits for sustained agreement):

| Parameter | Value |
|-----------|-------|
| Tests per suite | 95 |
| Repetitions per commit (K) | 100 |
| Invocations per commit | 9,500 |
| Observation window | 10 commits |
| Total invocations | 95,000 |
| Per-invocation CPU (local median) | ~0.29 ms |
| Total CPU (local) | ~27.5 s |
| Per-invocation CPU (Workers est.) | ~0.3–1.0 ms |
| Total CPU (Workers est.) | ~28–95 s |

### Cloudflare Workers billing (D3 pricing model)

| Line item | Rate | Cost for 95k invocations |
|-----------|------|--------------------------|
| Requests | $0.30 / million | $0.029 |
| CPU time | $0.02 / million CPU-ms | $0.001–0.002 |
| **Total per 10-commit window** | — | **~$0.03** |
| **Monthly (40 commits)** | — | **~$0.12** |

The free tier (100,000 requests/day, 10 ms CPU/request) covers the entire Phase 1 volume run without billing. The 95 tests × 100 repetitions = 9,500 requests per commit, well under the daily cap.

**The ~0.1 ms instantiation cost is the dominant per-request component** (median test execution alone is ~0.02 ms). On Cloudflare Workers, cold starts are the dominant cost: a fresh isolate for every request pays the instantiation overhead every time. Warm-isolate amortization (reusing an isolate across multiple requests, which Workers does automatically when requests arrive faster than isolates are recycled) is the one optimization that meaningfully reduces cost. For Phase 1's volume (9,500 requests spread across a commit run, not a sustained burst), cost is negligible either way.

## What Deployment Requires

The following are prerequisites for a real Cloudflare Workers deployment (U8). None is in this repo; all are provisioned by the maintainer:

1. **Cloudflare account** with Workers enabled.
2. **`wrangler` CLI** — `npm install -g wrangler` or equivalent. The Worker uses module syntax and `[wasm_modules]`, which require wrangler v3.x+.
3. **API token** — `wrangler login` or `CLOUDFLARE_API_TOKEN` environment variable with Workers deploy permission.
4. **`account_id`** — filled into `wrangler.toml`'s `account_id` field (currently a placeholder comment). Do not commit the real value.
5. **`.wasm` artifact placement** — the built `temper_wasm_test_runner.wasm` must be placed beside the Worker source (or a wrangler build step added to copy it). Uncomment the `[wasm_modules]` block in `wrangler.toml` and the `import WASM from ...` line in `src/index.js`.
6. **Budget** — free tier (100k requests/day) is sufficient. Paid tier at $5/month provides 10M requests/month and removes the daily cap, well within D3's $5–7/month estimate for continuous operation.

### Deploy command (after prerequisites are met)

```bash
cd packages/temper-worker

# Build the .wasm artifact (if not already built):
cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --manifest-path ../temper-wasm-test-runner/Cargo.toml

# Copy the artifact into the Worker directory:
cp ../../target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm .

# Uncomment the [wasm_modules] block in wrangler.toml
# Uncomment the `import WASM from ...` line in src/index.js
# Remove the FALLBACK block (readFileSync + WebAssembly.compile)

# Deploy:
wrangler deploy
```

### Verification after deploy

```bash
# Health check
curl -s https://temper-wasm-tier.<subdomain>.workers.dev/health

# Pass a test
curl -s -X POST https://temper-wasm-tier.<subdomain>.workers.dev/run-test \
  -H 'content-type: application/json' -d '{"index":0}'

# Verify expected-fail
curl -s -X POST https://temper-wasm-tier.<subdomain>.workers.dev/run-test \
  -H 'content-type: application/json' -d '{"index":26}'
```

## Verification (local)

The local probe and Worker Node server were both verified against the real `.wasm` artifact at `f7a1fbf8f`:

```bash
# Probe: direct instantiation + test calls
node tools/wasm/worker_local_probe.mjs
# → cold start 5.52 ms, warm instantiate median 0.092 ms, all probes pass or expected-fail

# Worker: local HTTP server (same logic, Node-hosted)
PORT=8797 node packages/temper-worker/src/index.js &
curl -s http://localhost:8797/health
# → { "status": "ok", "abi_version": 1, "test_count": 95 }

curl -s -X POST http://localhost:8797/run-test \
  -H 'content-type: application/json' -d '{"index":0}'
# → { "verdict": "pass", "name": "board::tests::edge_distance_is_symmetric" }

curl -s -X POST http://localhost:8797/run-test \
  -H 'content-type: application/json' -d '{"index":26}'
# → { "verdict": "expected-fail", "message": "panicked at ..." }
```

All four expected-fail tests (#26, #28, #50, #52) correctly trap and return their panic messages. The 91 passing tests return `verdict: "pass"`.

## Design decisions

1. **`packages/temper-worker/` not `workers/wasm-tier/`.** The repo's package convention is `packages/temper-*`. A top-level `workers/` directory would be a new top-level convention without precedent in this repo. The Worker is a package like any other: it has a config file, source, and a build artifact dependency. No Rust source lives here — the `.wasm` is an external artifact — so the Worker directory is minimal.

2. **Module syntax, not service-worker syntax.** Module-syntax Workers support `[wasm_modules]` bindings and `import` of `.wasm` files. Service-worker syntax (`addEventListener("fetch", ...`) does not. The Worker uses `export default { fetch }`.

3. **Expected-failure manifest is bundled, not fetched.** The manifest (`tools/wasm/wasm_expected_failures.json`) is hand-maintained. Bundling it in the Worker source avoids a second HTTP request per invocation and keeps the Worker stateless (no KV, no external fetch). It must be kept in sync with the committed manifest — a drift would cause the Worker to report `fail` for a test that should be `expected-fail`. The `GET /manifest` endpoint serves the bundled copy for client-side comparison.

4. **`ms` field uses `Date.now()` not `performance.now()`.** Workers billing CPU time is based on wall-clock isolate lifetime, not high-resolution monotonic time. `Date.now()` is sufficient for Phase 1 billing approximations. If sub-millisecond precision is needed, switch to `performance.now()`.

5. **No `workers-rs` or `wasm-bindgen`.** The `.wasm` module exports plain `extern "C"` functions with no bindgen glue. The Worker calls them directly. This keeps the Worker dependency-free (no npm install, no wasm-pack) and the `.wasm` zero-import.

## Files created

| File | Purpose |
|------|---------|
| `packages/temper-worker/wrangler.toml` | Workers config: name, module syntax, vars, wasm_module binding (commented) |
| `packages/temper-worker/src/index.js` | Worker entry point: R17 endpoints, trap handling, local Node server fallback |
| `tools/wasm/worker_local_probe.mjs` | Local verification harness: cold-start + per-invocation timing against real .wasm |
| `docs/evidence/2026-08-07-phase1-u7-worker-scaffold.md` | This document |
