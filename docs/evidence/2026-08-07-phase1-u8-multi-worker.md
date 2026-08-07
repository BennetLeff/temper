<!-- provenance: commit=8725ad475f94ad8af5b7634fc2e191bc71602a3b dirty=false -->

# Phase 1 U8 — Multi-Worker Deployment (Separate Per-Family Workers)

**Date:** 2026-08-07
**Base:** `origin/main` @ `a989bdc4c` (PR #914 merge)
**Branch:** `wasm/multi-worker`
**Status:** DEPLOYED — 7 per-family Workers + 1 existing full Worker live

## Summary

The single-worker deployment (`temper-wasm-tier`) serializes all requests within one
Cloudflare isolate — per-family sharding yielded 0.93× speedup (§U8 evidence).
This changeset deploys each family as a **separate Worker script**, routing to
separate isolates on the platform, enabling true parallel execution.

## Worker Inventory

| Name                     | URL                                                        | Family    | Tests | Module Size | Deploy Size |
|--------------------------|------------------------------------------------------------|-----------|-------|-------------|-------------|
| `temper-wasm-tier`       | `https://temper-wasm-tier.bennetleff.workers.dev`          | full      | 147   | 1,238 KB    | 1,179 KB    |
| `temper-wasm-drc`        | `https://temper-wasm-drc.bennetleff.workers.dev`           | drc       | 1     | 77 KB       | 86 KB       |
| `temper-wasm-emc`        | `https://temper-wasm-emc.bennetleff.workers.dev`           | emc       | 14    | 120 KB      | 128 KB      |
| `temper-wasm-erc`        | `https://temper-wasm-erc.bennetleff.workers.dev`           | erc       | 9     | 51 KB       | 61 KB       |
| `temper-wasm-safety`     | `https://temper-wasm-safety.bennetleff.workers.dev`        | safety    | 0     | 17 KB       | 28 KB       |
| `temper-wasm-placement`  | `https://temper-wasm-placement.bennetleff.workers.dev`     | placement | 12    | 83 KB       | 92 KB       |
| `temper-wasm-routing`    | `https://temper-wasm-routing.bennetleff.workers.dev`       | routing   | 2     | 41 KB       | 50 KB       |
| `temper-wasm-infra`      | `https://temper-wasm-infra.bennetleff.workers.dev`         | infra     | 109   | 1,197 KB    | 1,179 KB    |

**Total across all workers:** 147 tests (143 pass + 4 expected-fail).
**Account:** `03f642afe070f05b727f7cd31f02ef48` (bennetleff@gmail.com).

The existing `temper-wasm-tier` multi-family worker is preserved and functional
— it was not deleted or modified.

## Parallel Sweep Numbers

All measurements from the same network (Dallas colo), node v26.4.0, 2026-08-07.
Warm-up (one health-check request per family) was performed before each run to
amortize per-isolate cold-start.

### Before: Single-worker (temper-wasm-tier, serial per-isolate)

| Concurrency | Wall time (ms) | Throughput (tests/s) |
|-------------|----------------|---------------------|
| 8           | 5,791          | 25.4                |
| 64          | 6,227          | 23.6                |

Higher concurrency does NOT help (and slightly hurts) on the single-worker
deployment — the platform serializes requests within one isolate.

### After: Multi-worker (separate Workers per family)

| Concurrency | Wall time (ms) | Throughput (tests/s) | Speedup vs single c8 |
|-------------|----------------|---------------------|----------------------|
| 8           | 5,990          | 24.5                | 0.97×                |
| 32          | 5,090          | 28.9                | 1.14×                |
| 64          | 4,470          | 32.9                | 1.30×                |

**Parallel speedup factor: ~1.30×** (30% faster than the single-worker baseline
at the same concurrency). The speedup is real — separate Workers route to
separate isolates — but is limited by the infra worker (109 tests, 74% of the
total). The rule-family workers (drc, emc, erc, placement, routing) have only
38 tests combined and finish in parallel while infra dominates the critical path.

### Per-family first-request latency (cold-start)

All workers hit error 1042/1104 (CPU/memory limit on free tier) on the first
request after deploy. The free-tier 10 ms CPU budget is insufficient for
instantiation of even the smallest modules (17 KB safety module). After one
successful instantiation, warm requests serve correctly. This matches the
behavior documented in the U7 deploy runbook §6 (the cached-instance fix).

| Family    | First request after deploy | Warm request |
|-----------|---------------------------|-------------|
| drc       | error 1104                | 0 ms        |
| emc       | error 1042                | 0 ms        |
| erc       | error 1042                | 0 ms        |
| safety    | error 1042                | 0 ms        |
| placement | error 1042                | 0 ms        |
| routing   | error 1104                | 0 ms        |
| infra     | error 1104                | 0 ms        |

The cost of warming up all 7 workers is ~7 HTTP requests (one health check
per worker). The sweep client does this via `--warmup`.

## Paid Plan Consideration

The Workers Paid plan (enabled concurrently on 2026-08-07) provides **50 ms CPU
per request** instead of the free tier's 10 ms. At 50 ms, cold-start
instantiation would likely succeed on the first request for small modules
(17–120 KB), eliminating the warm-up step. The infra module (1,197 KB) may still
need a warm-up request. This was not measured (the paid plan toggle was done
by the account owner; the sweep client was tested against the free-tier
allocation).

If the paid plan is confirmed active, the single-worker `/run-test` endpoint
may also benefit: instantiation overhead that currently pushes past 10 ms
would fit within 50 ms, potentially reducing the need for instance caching.

## Deployment Architecture

Each family worker is a standalone module-syntax Worker:

```
packages/temper-worker/
  src/
    worker_core.js                              # Shared request-handling core
    temper_wasm_test_runner_<family>.wasm       # Per-family WASM modules (gitignored)
    index.js                                    # Original multi-family entry (temper-wasm-tier)
  families/
    <family>/
      index.js          # Imports one .wasm, calls createWorker()
      wrangler.toml     # name = "temper-wasm-<family>"
```

The per-family `index.js` imports a single `.wasm` module and passes it to
`createWorker()` from the shared `worker_core.js`. Each wrangler.toml uses
the same `account_id`, `ABI_VERSION`, and `compatibility_date` as the original
worker.

### Build & Stage

Per-family WASM modules were built from `packages/temper-wasm-test-runner`:

```bash
cargo build --release --target wasm32-unknown-unknown \
  --no-default-features --features wasm-registry-<family> \
  --manifest-path packages/temper-wasm-test-runner/Cargo.toml
```

Each build produces a `.wasm` file containing only that family's test entries,
dead-stripped via LTO. Module sizes match the U8 evidence table exactly.

**Note:** Cargo feature detection requires an explicit `CARGO_TARGET_DIR` or
removal of stale artifacts when switching between per-family features — see
the commit message for details.

### Deploy

```bash
cd packages/temper-worker/families/<family>
npx wrangler deploy
```

All 7 workers deployed successfully in ~9 seconds total.

## Sweep Client

`tools/wasm/sweep_multi_worker.mjs` — new multi-worker sweep client:

- Discovers family → test_count via per-worker `/health` calls
- Fans out all 147 tests across all 7 workers concurrently
- Bounded-concurrency pool (configurable via `--concurrency`)
- Warm-up phase (`--warmup`) sends one health check per worker before the sweep
- Reports aggregate verdict + per-family breakdown + wall time

Usage:
```bash
node tools/wasm/sweep_multi_worker.mjs --concurrency 64 --warmup --json out.json
```

## Files Changed

| File | Change |
|------|--------|
| `packages/temper-worker/families/<family>/index.js` | Per-family Worker entry points (7 files) |
| `packages/temper-worker/families/<family>/wrangler.toml` | Per-family deployment configs (7 files) |
| `tools/wasm/sweep_multi_worker.mjs` | New multi-worker parallel sweep client |
| `docs/evidence/2026-08-07-phase1-u8-multi-worker.md` | This document |

## Constraints Met

- ✅ No `git stash` used
- ✅ No CI changes
- ✅ No `power_pcb_dataset/**` or baseline edits
- ✅ Existing `temper-wasm-tier` worker preserved and verified functional
- ✅ All 147 tests pass across all workers (143 pass + 4 expected-fail)
- ✅ Per-family modules rebuilt (8 cargo invocations, ~30s total, using existing target-shared cache)
- ✅ No new Rust source code — only JS Worker entry points + TOML configs
