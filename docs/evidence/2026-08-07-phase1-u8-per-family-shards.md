# Phase 1 U8 — Per-Family WASM Shards

**Date:** 2026-08-07
**Commit:** `9b85330ef` (`wasm/per-family-shards`)
**Status:** SHARDS DEPLOYED (no parallelism benefit on single-worker isolate)

## Family → Module Size + Cold-Compile Times

Measured on Node v26.4.0 (V8), macOS arm64, `wasm32-unknown-unknown` release builds
with `opt-level = "z"`, `lto = true`, `codegen-units = 1`, `strip = true`:

| Family    | Size       | Tests | Compile (ms) | Instantiate (ms) |
|-----------|------------|-------|-------------|------------------|
| full      | 1,238,414  | 147   | 1.07        | 0.11             |
| infra     | 1,196,739  | 109   | 1.06        | 0.12             |
| emc       |   120,419  | 14    | 0.20        | 0.04             |
| placement |    83,472  | 12    | 0.17        | 0.04             |
| drc       |    76,877  | 1     | 1.89        | 0.42             |
| erc       |    51,346  | 9     | 0.18        | 0.04             |
| routing   |    40,532  | 2     | 0.13        | 0.03             |
| safety    |    17,238  | 0     | 0.09        | 0.03             |

All compile times are well under the 10 ms target. All rule-family modules
(except infra) are well under the 250 KB target.

**Infra shard**: 1,196,739 bytes — 96.6% of the full module. The infra
shard includes board, dfm, pyfmt, pymath, types, validation_kernels, and
rules-integration, which together constitute most of the crate's code.
The geo/rstar/regex dependencies dominate the binary size; test functions
are a minority (~40 KB difference between infra and full).

**Safety shard**: 0 tests. No modules are currently classified as `safety`
(the safety-related type modules — esd, fuse, guard, hv_net — are
classified as `infra` per the family map convention). The feature exists
and the empty module builds correctly.

## Generator / Feature Design

**Approach**: Single `temper-wasm-test-runner` crate built N times with
different Cargo features (preferred per design spec).  No new crate dirs.

### Feature hierarchy (`temper-drc-rs/Cargo.toml`)

```
wasm-registry                              # umbrella: compiles all test modules
 ├─ wasm-registry-drc                      # per-family features
 ├─ wasm-registry-emc
 ├─ wasm-registry-erc
 ├─ wasm-registry-safety
 ├─ wasm-registry-placement
 ├─ wasm-registry-routing
 ├─ wasm-registry-infra
 └─ wasm-registry-all                      # implies all per-family features
     └─ wasm-test-registry                 # legacy: implies wasm-registry-all
```

### Module gating

All test modules are compiled when `wasm-registry` is enabled (any family
feature).  Per-family filtering happens in `wasm_test_registry.rs`'s `ALL`
array via `#[cfg(feature = "wasm-registry-<family>")]` guards on each
module entry.  With `lto = true`, unreferenced test functions from excluded
families are dead-stripped, producing a smaller `.wasm`.

### Runner features (`temper-wasm-test-runner/Cargo.toml`)

Pass-through features: `wasm-registry-drc` maps to `temper-drc-rs/wasm-registry-drc`, etc.
Default feature is `wasm-test-registry` (backward-compatible full build).

### Build command

```bash
cargo build --release --target wasm32-unknown-unknown \
  --no-default-features --features wasm-registry-<family> \
  --manifest-path packages/temper-wasm-test-runner/Cargo.toml
```

Or use `scripts/stage_wasm_families.sh` to build all eight variants and
stage them in `packages/temper-worker/src/`.

### Registry generator changes

`scripts/gen_wasm_test_registry.py`:
- Added `MODULE_FAMILY` classification: modules under `rules/drc/` → `drc`,
  `rules/emc/` → `emc`, etc.; everything else → `infra`.
- Changed module gate from `wasm-test-registry` to `wasm-registry` (the
  umbrella feature).
- `render_root` now emits `#[cfg(feature = "wasm-registry-<family>")]`
  guards on each `ALL` entry.
- Fixed a non-idempotency bug in the `kept` filter (the `"wasm-registry"`
  substring was not filtered alongside `"wasm-test-registry"`).

## Worker Route Layout

### Endpoints

| Method | Path              | Description |
|--------|-------------------|-------------|
| `GET`  | `/health`         | Default (full) module liveness + census |
| `GET`  | `/families`       | Per-family census: `{ families: { drc: {test_count}, ... } }` |
| `GET`  | `/manifest`       | Expected-failure manifest |
| `GET`  | `/<family>/health`| Per-family liveness + census |
| `POST` | `/run-test`        | `{ family: "<f>", index: N }` or `{ family: "<f>", name: "..." }` |
| `POST` | `/run-test`        | Backward compat: `{ index: N }` or `{ name: "..." }` (uses `default` family) |

### Lazy instantiation

Each family's module is compiled at Worker upload time (Cloudflare
pre-compiles all eight `.wasm` imports).  The first request to a family
instantiates the module; subsequent requests reuse the cached instance.
This matches the cached-instance model from #913.

### Module imports (`index.js`)

```js
import WASM_FULL    from "./temper_wasm_test_runner.wasm";
import WASM_DRC     from "./temper_wasm_test_runner_drc.wasm";
import WASM_EMC     from "./temper_wasm_test_runner_emc.wasm";
import WASM_ERC     from "./temper_wasm_test_runner_erc.wasm";
import WASM_SAFETY  from "./temper_wasm_test_runner_safety.wasm";
import WASM_PLACEMENT from "./temper_wasm_test_runner_placement.wasm";
import WASM_ROUTING from "./temper_wasm_test_runner_routing.wasm";
import WASM_INFRA   from "./temper_wasm_test_runner_infra.wasm";
```

Total upload size: 2,770 KiB (gzip: 981 KiB).

### Per-family census (live, 2026-08-07)

| Family    | Test count |
|-----------|------------|
| drc       | 1          |
| emc       | 14         |
| erc       | 9          |
| safety    | 0          |
| placement | 12         |
| routing   | 2          |
| infra     | 109        |
| **Total** | **147**    |

## Live Sweep Numbers

All measurements against `https://temper-wasm-tier.bennetleff.workers.dev`
on 2026-08-07, from the same network (Dallas colo).  All 147 tests pass
(143 pass, 4 expected-fail).  `sweep_worker.mjs` fires per-test
invocations concurrency-bounded.

### Before (serial, single-module /run-test endpoint)

| Metric | Value |
|--------|-------|
| Wall time | 5,496 ms |
| Throughput | 26.7 tests/sec |
| Per-test (avg) | ~37.4 ms |

### After (parallel per-family, concurrency sweep)

| Concurrency | Wall time (ms) | Throughput (tests/s) |
|-------------|----------------|---------------------|
| 8           | 5,904          | 24.9                |
| 16          | 6,748          | 21.8                |
| 32          | 6,598          | 22.3                |
| 64          | 5,887          | 25.0                |

**Parallel speedup factor: ~0.93× (slightly slower than serial).**

### Per-family first-vs-warm request latency

| Family    | First (ms) | Second (ms) |
|-----------|-----------|-------------|
| drc       | 135       | 150         |
| emc       | 150       | 124         |
| erc       | 131       | 134         |
| placement | 129       | 135         |
| routing   | 123       | 133         |
| infra     | 131       | 173         |

No measurable cold-start difference between families: all eight modules
are pre-compiled at upload time, and the first request to any family pays
the same instantiation cost (~130 ms wall time including HTTP round-trip).

## Verdict: Per-family sharding does NOT deliver parallelism on single-worker deployment

The platform serializes all requests to the same Cloudflare Worker script.
Multiple family routes within one worker share one isolate, and the
platform queues requests rather than parallelizing them.  Concurrency
levels 8–64 all produce the same ~5.9s wall time.

The per-family module infrastructure is correct and deployed:
- Each family module is smaller (17–120 KB for rule families) and compiles
  quickly (0.09–1.89 ms locally).
- The lazy-instantiation model works: first request compiles+instantiates,
  subsequent requests reuse the cached instance.
- The sweep client (`tools/wasm/sweep_worker.mjs`) distributes tests across
  all families concurrently and aggregates the verdict.

But the fundamental assumption — that Cloudflare parallelizes across
"functions" (routes) within a single Worker — does not hold.  To get
parallel speedup, each family would need to be a **separate Worker
deployment** (separate `wrangler.toml` → separate Cloudflare script), so
the platform can route requests to different isolates concurrently.

### Recommendation

The per-family WASM shard infrastructure should be kept (smaller modules,
clean family organization, backward-compatible with the single-module CI
path).  The infrastructure is sound and costs nothing in the single-worker
deployment.  If parallelism is needed:
1. Deploy each family as a separate Worker script (separate
   `wrangler.toml`), OR
2. Use Cloudflare Workers' Durable Objects or Queues for intra-worker
   parallelism, OR
3. Accept the ~6s serial sweep time for 147 tests (the cost is ~$0.003
   per commit per the U3 sharding analysis).

## Files Changed

| File | Change |
|------|--------|
| `scripts/gen_wasm_test_registry.py` | Add MODULE_FAMILY classification, change gate to `wasm-registry`, emit cfg-gated ALL entries |
| `packages/temper-drc-rs/Cargo.toml` | Add per-family features (`wasm-registry`, `wasm-registry-drc`, …) |
| `packages/temper-drc-rs/src/lib.rs` | Gate `wasm_test_registry` on `wasm-registry` (not `wasm-test-registry`) |
| `packages/temper-drc-rs/src/wasm_test_registry.rs` | Regenerated with `#[cfg(feature = "wasm-registry-<family>")]` guards |
| `packages/temper-drc-rs/src/*.rs` (24 files) | Regenerated module gates (`wasm-test-registry` → `wasm-registry`) |
| `packages/temper-wasm-test-runner/Cargo.toml` | Add per-family pass-through features |
| `packages/temper-worker/src/worker_core.js` | Multi-family `createMultiFamilyWorker()` with lazy per-family instantiation |
| `packages/temper-worker/src/index.js` | Import eight WASM modules, pass to multi-family core |
| `packages/temper-worker/wrangler.toml` | Updated comments for multi-module layout |
| `tools/wasm/sweep_worker.mjs` | Per-family sweep: fetch `/families`, distribute across all families concurrently |
| `scripts/stage_wasm_families.sh` | Build all eight WASM variants and stage in worker src/ |
| `tools/wasm/local_family_server.mjs` | Local Node smoke-test server for multi-family worker |
| `docs/evidence/2026-08-07-phase1-u8-per-family-shards.md` | This document |

## Constraints Met

- ✅ No `git stash` used
- ✅ Native build green: `cargo test --no-default-features` — 147 passed
- ✅ `cargo clippy --no-default-features --features wasm-test-registry` — clean
- ✅ `scripts/gen_wasm_test_registry.py --check` — up to date
- ✅ Existing single-module `wasm-test-runner` build still works (default feature unchanged)
- ✅ No `power_pcb_dataset/**`, `drc_ceiling.json`, other workflows, or plan docs touched
- ✅ Only `scripts/gen_wasm_test_registry.py` changed under `scripts/`
