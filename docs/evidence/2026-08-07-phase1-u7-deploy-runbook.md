<!-- provenance: commit=00ec5f94a dirty=false -->

# Phase 1 U7 — Cloudflare Worker Deploy Runbook

**Date:** 2026-08-07
**Branch:** `wasm/cf-deploy`
**Base:** `origin/main` @ `00ec5f94a`
**Status:** DEPLOY-READY. Everything below is prepared and locally verified; the
only blocker is a human with Cloudflare credentials.

This runbook is the operational counterpart of
`docs/evidence/2026-08-07-phase1-u7-worker-scaffold.md`. The scaffold recorded
the Worker design and the local probe numbers; this document records how to get
the same Worker onto Cloudflare in one command, how to verify it, how to roll
back, and what cost the operation is allowed to accrue.

## 0. Preflight state (verified 2026-08-07)

| Item | State |
|------|-------|
| `wrangler` binary | NOT installed globally. `npx wrangler` works (v4.120.0 via npm cache). |
| `node` / `npm` | v26.4.0 / 11.17.0 |
| `CLOUDFLARE_API_TOKEN` | NOT set |
| `CLOUDFLARE_ACCOUNT_ID` | NOT set |
| Cloudflare account | NOT provisioned — no account reference exists anywhere in the repo (only the placeholder comments in `wrangler.toml` and the `<subdomain>` placeholder in the scaffold doc). |

Every step below that needs credentials is a **human** step. This repo contains
no Cloudflare credentials and must not.

## 1. One-time account provisioning (human)

```bash
# 1. Install the CLI (or rely on `npx wrangler` for every command below).
npm install -g wrangler

# 2. Authenticate. Either interactive OAuth (preferred, nothing stored in repo):
npx wrangler login
#    ...or a scoped API token (Workers: Edit) in the environment for CI-style deploys:
#    export CLOUDFLARE_API_TOKEN=...

# 3. Confirm the account the deploy will land on:
npx wrangler whoami
#    You should see exactly one account. The Worker will live at
#    https://temper-wasm-tier.<account-subdomain>.workers.dev
```

Optional but recommended: pin the account in `packages/temper-worker/wrangler.toml`:

```toml
account_id = "<12-hex-account-id-from-wrangler whoami>"
```

Do NOT commit that value — it is a maintainer secret for the repo. If it is
pinned, this repo's CI (which has no token) still cannot deploy.

## 2. The one-command deploy

```bash
# From the repo root. Builds the .wasm, stages it beside the Worker source,
# then deploys:
make wasm-worker-deploy
```

Which expands to (also the manual, transparent version):

```bash
# 2a. Build the wasm32 artifact (incremental; shared cargo target dir)
cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --manifest-path packages/temper-wasm-test-runner/Cargo.toml

# 2b. Copy it beside the Worker source (gitignored — never committed)
cp target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm \
   packages/temper-worker/src/temper_wasm_test_runner.wasm

# 2c. Deploy (module-syntax Worker; the .wasm is bundled via the direct import
#     in src/index.js — a [wasm_modules] block is invalid for module workers)
cd packages/temper-worker
npx wrangler deploy
```

A successful deploy ends with the URL:
`https://temper-wasm-tier.<account-subdomain>.workers.dev`.

**Local check before deploying (no credentials needed):** run
`npx wrangler deploy --dry-run` in `packages/temper-worker`. It must exit 0 with
`Total Upload` ≈ **1179 KiB** (the .wasm bundled) and no `nodejs_compat`
warnings. A small upload (< 10 KiB) means the .wasm import was dropped — do not
deploy.

## 3. Local smoke test (before deploy, and to sanity-check the artifact)

The runbook's local smoke test runs the exact code that will be deployed
(`worker_core.js`) against the exact artifact that will be bundled:

```bash
# 3a. Full-corpus gate (runs all 112 tests, fails on any manifest drift):
node tools/wasm/run_wasm_tests.mjs \
  target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm
#     → passed 108 / expected-fail 4 / unexpected-pass 0, exit 0

# 3b. Timing probe (cold start + warm instantiate + per-invocation):
node tools/wasm/worker_local_probe.mjs
#     → see §Expected numbers

# 3c. HTTP smoke test of the deployed endpoints, locally:
PORT=8797 node tools/wasm/worker_local_server.mjs &
curl -s http://localhost:8797/health
curl -s -X POST http://localhost:8797/run-test \
  -H 'content-type: application/json' -d '{"index":0}'
curl -s -X POST http://localhost:8797/run-test \
  -H 'content-type: application/json' -d '{"index":26}'
curl -s -X POST http://localhost:8797/run-test \
  -H 'content-type: application/json' -d '{"name":"pymath::tests::pow_is_not_a_multiply_or_a_sqrt"}'
```

Expected responses:
- `/health` → `{"status":"ok","abi_version":1,"test_count":112}`
- `{"index":0}` → `{"verdict":"pass","name":"board::tests::edge_distance_is_symmetric",...}`
- `{"index":26}` → `{"verdict":"expected-fail",...,"expected_failure_class":"b7-pow-divergence-absent",...}` (panic message present)
- by-name → `{"verdict":"expected-fail","index":50,...}` (name→index resolution works)

## 4. Deployed smoke test

```bash
URL=https://temper-wasm-tier.<account-subdomain>.workers.dev

curl -s "$URL/health"
# → {"status":"ok","abi_version":1,"test_count":112}

curl -s -X POST "$URL/run-test" -H 'content-type: application/json' -d '{"index":0}'
# → {"verdict":"pass","index":0,"name":"board::tests::edge_distance_is_symmetric",...}

curl -s -X POST "$URL/run-test" -H 'content-type: application/json' -d '{"index":26}'
# → {"verdict":"expected-fail",...,"expected_failure_class":"b7-pow-divergence-absent",...}

curl -s -X POST "$URL/run-test" -H 'content-type: application/json' -d '{"name":"pymath::tests::pow_is_not_a_multiply_or_a_sqrt"}'
# → {"verdict":"expected-fail","index":50,...}

curl -s "$URL/manifest" | head -c 120
# → {"_comment":[...],"expected_failures":{...}}
```

The verdicts must match §3 exactly. If a test that is `expected-fail` locally
reports `fail` or `unexpected-pass` on the Worker, the bundled manifest drifted
from `tools/wasm/wasm_expected_failures.json` — fix `EXPECTED_FAILURES` in
`packages/temper-worker/src/worker_core.js` and redeploy.

## 5. Expected numbers (verify against the local probe)

Measured 2026-08-07 at `00ec5f94a` against the fresh 112-test artifact
(1,200,116 bytes, **0 imports** — bare-isolate deployable):

| Metric | Local probe | Worker to expect |
|--------|-------------|------------------|
| Cold start (compile + first instantiate) | ~2.1 ms | one-time, at first request after deploy |
| Warm instantiate median | ~0.09 ms | ~0.09–0.27 ms |
| Warm instantiate p95 | ~0.29 ms | ~0.3–0.9 ms |
| `/run-test` #0 (pass) total | ~0.65 ms | 1.0–3.0× local |
| `/run-test` #1 (pass) total | ~0.22 ms | 1.0–3.0× local |
| `/run-test` #26 (expected-fail) total | ~3.6 ms | 1.0–3.0× local |
| `/run-test` #50 (expected-fail) total | ~3.3 ms | 1.0–3.0× local |
| Peak linear memory | 1.75 MiB | 1.4% of the 128 MiB isolate limit |

The platform overhead factor (Worker / local Node) is **unmeasured** until the
first real deploy; the U3 sharding evidence expects 1.0–3.0×, not 10× (same V8
engine, zero-import module, per-invocation time dominated by V8-internal
instantiation). Do not be surprised by a *lower* Worker wall time (fresh
isolates can JIT the hot path differently). **Investigate only if a request
exceeds ~10 s or returns 500** — that is a compile-per-request regression (the
module must be compiled once at upload), not a cost concern.

## 6. Rollback

Every deploy creates a versioned deployment. Two-step rollback:

```bash
# What is live, and its versions:
npx wrangler versions list
npx wrangler deployments list

# Instant rollback to the previous deployment (most common case):
npx wrangler rollback

# Or pin to a specific previous version:
npx wrangler versions upload   # rebuild from a clean state, then:
npx wrangler deploy --version-id <version-id>
```

The `.wasm` artifact is reproducible (cargo build of a pinned commit), so a
"previous version" is always re-derivable: `git checkout <old-sha> && make
wasm-worker-deploy` is a valid rollback for source-level regressions. The
deployed Worker is stateless (no KV/R2/D1/Durable Objects), so rollback carries
no data-migration risk — it is a pure code revert.

## 7. Release cadence and cost ceiling

From the U8 cost model (U5/U6 volume data), now with the 112-test corpus
(112 × K=100 repetitions = **11,200 invocations per commit**):

| Line item | Rate | Cost |
|-----------|------|------|
| Requests | $0.30 / million | $0.003 per commit |
| CPU time | $0.02 / million CPU-ms | negligible |
| **Monthly (40 commits)** | — | **~$0.12** |
| Free tier | 100k requests/day, 10 ms CPU/request | covers a daily full run (~11.2k requests) |

Budget envelope: **this Worker must stay under $1/month.** That allows roughly
80k requests/day paid overage — far more than Phase 1's 11.2k/commit — or, on
the free tier, unlimited Phase 1 runs with no billing at all. The one cost
dimension to watch is CPU time: the Workers billing model charges isolate
lifetime, and cold starts pay the instantiation overhead per request. At Phase 1
volume (requests spread across a commit run, not a sustained burst) this is
negligible; if a future phase ever runs sustained high-rate bursts, warm-isolate
amortization (automatic when requests arrive faster than isolates recycle)
already covers it. A genuine cost alarm is > $1/month sustained — stop and
measure before ratcheting.

## 8. What this runbook does NOT cover

- Provisioning the Cloudflare account or the `temper-wasm-tier` subdomain
  (maintainer action; §1).
- Automating deploys from CI (no token in this repo; if a token is ever added,
  deploy becomes a `make wasm-worker-deploy` step — but token handling is
  someone else's change).
- `wrangler dev` parity: the local harness (`worker_local_server.mjs`) runs the
  same core against the same artifact and is the sanctioned Phase-0 substitution
  for a local workerd.
