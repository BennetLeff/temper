<!-- provenance: commit=d1b330b90a149f5effd09c7e63b87deeebdb0261 dirty=false -->

# WASM verification tier — real cost and headroom at current scale (U3)

**Date:** 2026-08-11
**Task:** Unit U3 of
`docs/plans/2026-08-11-001-feat-wasm-tier-phase2-plan.md` ("The tier's real
cost ceiling, measured at current scale").
**Snapshot:** `origin/main` `d1b330b90a149f5effd09c7e63b87deeebdb0261`, `git
status` clean. The plan document itself was authored against `12b9e205` and
records 2,788 tests / 6 tiers / 13 Workers in its own §1 — **that table is
already stale**, superseded first by `tools/wasm/wasm_tier_topology.json`'s
own header comment (3,057 tests / 8 tiers / 15 Workers, dated 2026-08-11) and
now by this document's live measurement (**4,567 tests**, same 8 tiers, same
15 Workers — `temper-geometry` alone grew from the topology comment's stated
722 to a live-measured **2,232**, confirmed against the topology file's own
`_comment` block at commit time). Three different corpus sizes have now been
"current" within this one plan's lifetime. Nothing below assumes the number
holds past this measurement.

---

## Bottom line

1. **Requests are measured, real, and currently the tighter constraint** —
   not CPU-ms. One HTTP request per test (R17), confirmed directly from
   `packages/temper-worker/src/worker_core.js`'s `/run-test` handler. A full
   sweep of the current corpus is **4,567 requests**, measured twice, live,
   this session (`tools/wasm/sweep_multi_worker.mjs`, no `--tier` filter).
2. **Nightly cadence (the plan's own framing) is nowhere near a limit:**
   4,567 req/night × 30 = 137,010 req/month = **1.37% of the 10M/month
   included-request quota**. CPU-ms at nightly cadence is 2–3 orders of
   magnitude under the 30M/month quota under every proxy measured below.
3. **The PR-triggered sweep (`wasm-tier-pr.yml`, merged same day as this
   measurement, PR #951) is a materially different story and was not part of
   any prior cost model.** Its measured trigger rate over its entire
   lifetime so far — 12 runs in 2h20m, via the GitHub Actions API, not
   estimated — is **~5.2 runs/hour**. Sustained at that rate it would push
   monthly requests to **~15.3M, past the 10M included quota**, on its own,
   independent of anything Phase 2 adds. This is flagged explicitly as an
   observed burst during an 11-agent concurrent development window (stated
   in this task's own scope), not a claimed steady state — see §2.3.
4. **CPU-ms remains unmeasured at the billing level.** Cloudflare's
   Analytics API is unreachable without a token this task was told not to
   obtain (confirmed: `400` on both endpoints named in the task, §3.1). Four
   independent, non-billing measurements — the Worker's own `Date.now()`
   timer, a from-source local V8 run of the exact deployed bytes, a
   CI-runner network-inclusive average, and the native R2 baseline — all
   converge on **well under 1 CPU-ms per request**, most likely tens of
   microseconds. This is a bound, not a Cloudflare-billed figure, and is
   reported as such throughout.
5. **The memory ceiling (parent R2/Q7) is not close, at this scale, for any
   deployed module.** The largest peak linear memory of any of the 15
   deployed `.wasm` modules is **`temper-io-types` at 3.88 MiB (4,063,232
   bytes) — 3.03% of the 128 MiB isolate limit, ~33× headroom.** Cross-
   validated two independent ways (this session's own build, and an
   unmodified download of the latest green nightly's CI artifact) — both
   report the identical sha256, matching the live-deployed
   `module_sha256`. No module is within two orders of magnitude of the
   limit; the only path to the 2,400 MB wall R2 identified is occupancy-grid
   resolution, which D2.3 already excludes from Phase 2's first sweep.
6. **Phase 2 sizing (R2.7): under nightly-only cadence, N can grow to
   roughly the low thousands of envelope points before the *added* request
   volume becomes a double-digit fraction of the request quota** (§5). But
   this number is conditional on which cadence governs — see finding 3. If
   Phase 2's generated tests fold into `temper-drc-rs`'s registry (as D2.4
   specifies) and `temper-drc-rs` is swept on every PR-workflow run (it is,
   confirmed in `wasm-tier-pr.yml`), the PR-cadence finding above is the
   thing that actually binds, and it binds **before Phase 2 adds anything**.

---

## Method note — what was measured vs. estimated

| Claim | Status |
|---|---|
| 4,567 tests, 15 Workers, 1 req/test | **Measured** — live `/health` census + code read of `/run-test` |
| Full-sweep wall time/throughput (this session, this network) | **Measured** — two live runs |
| Full-sweep wall time/throughput (CI runner) | **Measured** — downloaded, unmodified nightly CI artifact |
| Module size, peak linear memory (8 tier-level modules) | **Measured** twice independently (this session's local build; CI artifact for commit `86c6a01f`) — sha256-identical to live-deployed modules |
| Module size, peak linear memory (7 `temper-drc-rs` family shards) | **Measured** — this session's local build only (no CI arm builds shards separately) |
| Nightly cadence | **Measured** — cron expression in the workflow file, cross-checked against GitHub Actions run history |
| PR-workflow trigger rate | **Measured** (GitHub Actions API, full run history — 12 runs, the workflow's entire lifetime) but explicitly flagged as **non-steady-state** |
| Commit/PR merge velocity (for a calmer PR-rate estimate) | **Measured** — `gh pr list`, `git log`, sampled directly |
| Per-request CPU-ms (Cloudflare-billed) | **Not measured.** Analytics API confirmed unreachable without credentials (§3.1) |
| Per-request CPU-ms (four local/CI proxies) | **Measured**, but explicitly not the billed figure — see §3.2 |
| Monthly request/CPU-ms totals under each cadence scenario | **Estimated** — arithmetic built on the measured figures above, never presented as billed |
| N at which Phase 2 stops being negligible | **Estimated** — arithmetic bound, depends on an R (relevant-rule-count) figure that is itself pre-U1 and not yet real |

---

## 1. What `/health` and `/run-test` actually do (read, not assumed)

From `packages/temper-worker/src/worker_core.js` (read directly):

- **`GET /health`**: instantiates (or reuses a cached instance of) the
  Worker's "default" family module, calls two WASM exports
  (`temper_wasm_abi_version()`, `temper_test_count()`), returns
  `{status, abi_version, test_count, module_sha256?}`. No test execution.
- **`POST /run-test`**: resolves `(family, index)` from the request body,
  gets-or-instantiates that family's cached `WebAssembly.Instance`
  (`instances[family]`, a closure-scoped cache — **not** a fresh instance
  per request, contrary to the file's own header comment, which describes
  the pre-cache-fix R17 model; the code was patched later and the comment
  was not), reads the test name via two more exports, calls
  `temper_run_test(index)`, and returns `{verdict, index, name, message,
  abi_version, ms, family}`. `ms` is `Date.now()`-based, measured inside the
  Worker.
- **Implication for CPU-ms:** because the instance is cached per family per
  isolate, cold-compile/instantiate cost (1.0–6.2 ms per module, measured
  §6) is paid once per warm isolate lifetime, not once per request. Under
  the sweep's concurrency-64 fan-out, Cloudflare very likely spins up a
  handful of concurrent isolates per family rather than one per request, so
  cold-start amortizes over hundreds-to-thousands of requests per family,
  not one. This is inferred from the code and the platform's documented
  isolate-reuse model, not directly observed (observing it would need the
  same Analytics API access this task avoids).

One request per test is a code-level fact (R17), not a policy that could
quietly change without a Worker rewrite — every request body carries at
most one `index`/`name`, and the ABI (`tools/wasm/gen_property_campaign.py`'s
own docstring, cited in the Phase 2 plan) has no way to pass more.

---

## 2. Requests

### 2.1 Corpus census — live, cross-validated

`GET /health` against all 15 deployed Workers, this session:

| Worker | Tests | Tier |
|---|---:|---|
| `temper-wasm-tier` (drc-rs full corpus) | 1,719 | temper-drc-rs |
| `temper-wasm-drc` (shard) | 1,510 | ″ |
| `temper-wasm-emc` (shard) | 15 | ″ |
| `temper-wasm-erc` (shard) | 12 | ″ |
| `temper-wasm-safety` (shard) | 25 | ″ |
| `temper-wasm-placement` (shard) | 18 | ″ |
| `temper-wasm-routing` (shard) | 18 | ″ |
| `temper-wasm-infra` (shard) | 121 | ″ |
| `temper-wasm-geometry` | **2,232** | temper-geometry |
| `temper-wasm-thermal` | 143 | temper-thermal |
| `temper-wasm-design-bundle` | 24 | temper-design-bundle |
| `temper-wasm-router-core` | 111 | temper-rust-router-core |
| `temper-wasm-constraint-compiler` | 69 | temper-constraint-compiler |
| `temper-wasm-quality-oracle` | 125 | temper-quality-oracle |
| `temper-wasm-io-types` | 144 | temper-io-types |

**Full-corpus total (8 tiers, deduplicating the drc-rs full-corpus module
against its own 7 shards): 1,719 + 2,232 + 143 + 24 + 111 + 69 + 125 + 144 =
4,567.** This matches the task brief's own stated figure exactly and matches
what `tools/wasm/sweep_multi_worker.mjs` (no `--tier` filter — every tier)
dispatches through the shard set, one request per test.

`temper-quality-oracle` and `temper-io-types`, which the Phase 2 plan's §1
table lists as "registered but undeployed," **are now deployed** — both
answer `/health` live with a Worker URL and a `module_sha256`. This is
itself new information relative to the plan document: the plan was correct
when written and is no longer current about this specific fact within its
own lifetime.

### 2.2 Full-sweep throughput — measured twice, this session, and cross-checked against CI

Ran `node tools/wasm/sweep_multi_worker.mjs --concurrency 64` (no `--tier`,
every deployed shard) twice, back to back:

| Run | Total | Wall | Throughput | Failures |
|---|---:|---:|---:|---:|
| 1 (no warmup) | 4,567 | 56,045 ms | 81.5 tests/s | 0 |
| 2 (`--warmup`) | 4,567 | 56,025 ms | 81.5 tests/s | 0 |

Reproducible, but **~10× slower than the 852.3 tests/s** the 2026-08-10
U4-closure document measured at 1,708 tests. Before concluding the platform
degraded, the same sweep was reproduced from a GitHub Actions runner by
downloading the latest green nightly's artifact
(`wasm-tier-nightly-worker-31455191432`, run at commit `86c6a01f0654...`,
2026-08-11T03:22:22Z — the entire 8-tier sweep, one `worker_sweep_<tier>.json`
per tier):

| Tier | Requests | Wall (ms) | Throughput |
|---|---:|---:|---:|
| drc-rs | 1,719 | 2,614 | 657.6/s |
| geometry | 2,232 | 2,506 | 890.7/s |
| thermal | 143 | 329 | 434.7/s |
| design-bundle | 24 | 154 | 155.8/s |
| router-core | 111 | 239 | 464.4/s |
| constraint-compiler | 69 | 261 | 264.4/s |
| quality-oracle | 125 | 258 | 484.5/s |
| io-types | 144 | 435 | 331.0/s |
| **sum** | **4,567** | **6,796 ms (sequential steps)** | **~672/s aggregate** |

**Finding: the 10× throughput gap is this session's network path, not the
platform.** Direct latency probes from this environment to a deployed Worker
show ~0.10–0.15 s just to TLS-handshake a fresh connection and ~0.29–0.35 s
total round-trip for a single `/run-test` call; at concurrency 64 that alone
implies ~64/0.3 s ≈ 213/s as a rough ceiling from this vantage point, in the
same order as the 81.5/s observed once queueing and 14 concurrent target
hosts are accounted for. The CI runner, on a better-peered path, reproduces
throughput close to the 2026-08-07/2026-08-10 baselines. **This is the
correct lesson for future measurements: throughput at fixed concurrency is
dominated by the measuring environment's network path (a finding the
2026-08-07 U8 document already made once, independently, at ±20× run-to-run
variance from the same account) — it is not a stable property of the tier
itself, and no cost conclusion in this document rests on it.** The CI
figures are used below wherever throughput/timing matters; wall-clock
throughput itself is not billed regardless.

### 2.3 Cadence — measured, not assumed

**Nightly** (`wasm-tier-nightly.yml`): `cron: '40 4 * * *'` — one full 8-tier
sweep/day, unconditionally, by design. → **4,567 requests/night = 137,010
requests/month** (30-night month).

**PR** (`wasm-tier-pr.yml`, `on: pull_request`, `paths:` filter on
`packages/**`, `tools/wasm/**`, `scripts/gen_wasm_test_registry.py`, the
workflow file itself): sweeps 3 tiers per run — `temper-drc-rs` (1,719) +
`temper-geometry` (2,232) + `temper-thermal` (143) = **4,094 requests per
PR-workflow run**. This workflow did not exist when any prior cost estimate
in this repo was written; it landed same-day as this measurement (`#951`,
commit `6ba8a45a`).

Its entire run history (GitHub Actions API,
`repos/:owner/:repo/actions/workflows/331555525/runs`) is **12 runs**, every
one `event: pull_request`, spanning `2026-08-11T02:11:27Z` to
`2026-08-11T04:31:01Z` — **2h20m for 12 runs, ~5.2 runs/hour.** This is a
measured fact about this session's window, not an extrapolation. Sustained
24/7 at that rate: `5.2 × 24 × 30 ≈ 3,744 runs/month × 4,094 req/run ≈
15.33M requests/month` from the PR path alone — **already past the 10M
included-request quota before nightly's 137,010 is even added.**

This number is explicitly **not** presented as a steady-state prediction.
The task's own scope note states "eleven other agents are running" during
this measurement — the observed 5.2 runs/hour reflects a concurrent
development burst, and 7 of the 12 runs recorded `conclusion: failure`
(consistent with a landing-day workflow still being shaken out, not with
sustained production traffic). A calmer, independently-measured basis:

- `gh pr list --state merged --limit 100`: 100 merged PRs span
  `2026-08-06T23:20:04Z` to `2026-08-11T04:38:18Z` = 4.22 days → **23.7
  merged PRs/day**.
- Of the last 300 commits (`git log -300 --name-only`), **194 (64.7%)**
  touch a path the PR workflow's `paths:` filter matches.
- Calmer estimate: `23.7 × 0.647 ≈ 15.3 triggering merges/day` (a floor —
  the workflow fires on every push to an open PR, not only at merge, so a
  PR pushed to multiple times triggers multiple times; this estimate counts
  each PR once). → `15.3 × 4,094 ≈ 62,638 req/day → 1,879,140 req/month`.

**Manual** (`workflow_dispatch`): 10 of the last 12 nightly-workflow runs in
this same window were manual dispatches, not scheduled ones — largely this
measurement session and the concurrent agent fleet exercising the tier.
Not modeled as a recurring monthly rate (it is testing activity, not
production cadence), but it is real, already-incurred request volume this
document's own §7 accounts for.

### 2.4 Monthly request totals, three cadence scenarios

| Scenario | Requests/month | % of 10M quota |
|---|---:|---:|
| Nightly only | 137,010 | 1.37% |
| Nightly + calm PR estimate (15.3 triggering merges/day) | 2,016,150 | 20.16% |
| Nightly + **observed-burst** PR rate, sustained | ~15,464,946 | **154.6% — crosses the included quota** |

Under the burst-sustained scenario, the overage is `~5.46M requests ×
$0.30/M ≈ $1.64/month` above the flat $5.00 — a real number, but small in
dollars; the significance is qualitative (usage-based billing turns on at
all, for the first time since the tier existed) rather than large in
absolute cost.

---

## 3. CPU-ms

### 3.1 The billing-verified figure is not obtainable here, confirmed directly

Per the task's constraint (a token exists, this task does not have it and
must not seek it), both endpoints named in the task brief were tried,
unauthenticated, and failed exactly as the 2026-08-07 U8 document recorded:

```
$ curl https://api.cloudflare.com/client/v4/accounts/03f642afe070f05b727f7cd31f02ef48/workers/scripts
HTTP 400
$ curl https://api.cloudflare.com/client/v4/graphql
HTTP 400
```

**What would answer O3, if credentials existed:** Cloudflare's GraphQL
Analytics API, `workersInvocationsAdaptive` dataset, one query per Worker
script:

```graphql
query {
  viewer {
    accounts(filter: { accountTag: "03f642afe070f05b727f7cd31f02ef48" }) {
      workersInvocationsAdaptive(
        filter: { scriptName: "temper-wasm-tier", datetime_geq: "<start>", datetime_leq: "<end>" }
        limit: 10000
      ) {
        sum { requests, errors, subrequests }
        quantiles { cpuTimeP50, cpuTimeP99 }
      }
    }
  }
}
```

This would return the actual billed CPU-time distribution (P50/P99, in
microseconds) per script over any window, and the exact request count
Cloudflare itself billed against — the authoritative version of everything
§2's arithmetic estimates. It requires an API token with Analytics:Read
scope. Not obtained, per instruction.

### 3.2 Four independent, non-billing bounds — all converge under 1 ms

**(a) The Worker's own `Date.now()` timer.** Six live `/run-test` calls
against `temper-wasm-drc`, `temper-wasm-geometry`, and
`temper-wasm-quality-oracle` at scattered indices (0, 1, 2, 100, 500, 1000,
1500) all returned `"ms": 0`. `Date.now()` inside a Worker resolves to
whole milliseconds; a value of 0 across every sample means the whole
request-handling path (lookup + `temper_run_test` + response construction)
rounds under 1 ms server-side, not just the kernel call itself.

**(b) Local V8 execution of the exact deployed bytes.** `node
tools/wasm/run_wasm_tests.mjs <module>` runs the entire registered corpus of
each module in one Node/V8 process (the same wasm32 engine `workerd`
embeds, per that tool's own header) and reports per-test timing via
`performance.now()`-precision. Run against all 8 tier-level modules this
session (own build) and cross-checked against the CI nightly artifact's
independent build of the identical bytes (same sha256):

| Module | Tests | Mean ms/test | Median ms/test | Total test-exec ms |
|---|---:|---:|---:|---:|
| temper-drc-rs (full) | 1,719 | 0.0686 | 0.0182 | 117.9 |
| temper-geometry | 2,232 | 0.0435 | 0.0089 | 97.2 |
| temper-thermal | 143 | 0.4482 | 0.0161 | 64.1 |
| temper-design-bundle | 24 | 0.4543 | 0.0733 | 10.9 |
| temper-rust-router-core | 111 | 0.1248 | 0.0378 | 13.9 |
| temper-constraint-compiler | 69 | 0.1045 | 0.0352 | 7.2 |
| temper-quality-oracle | 125 | 0.1446 | 0.0201 | 18.1 |
| temper-io-types | 144 | 1.311 | 0.039 | 188.8 |

(CI-measured figures shown; this session's own local build reproduced the
same order of magnitude for every module — e.g. drc-rs full corpus 0.0424
mean/0.012 median vs. CI's 0.0686/0.0182, both far under 1 ms.)

Weighted mean across the actual production dispatch set (family shards for
drc-rs, full corpus for the other 7 tiers, 4,567 tests, this session's own
build): **314.24 ms of total V8 execution time / 4,567 tests ≈ 0.069
ms/test.**

**(c) CI-runner end-to-end average (network + Worker CPU combined), from
§2.2's real sweep:** drc-rs 2,614 ms / 1,719 = 1.52 ms/request; geometry
2,506 ms / 2,232 = 1.12 ms/request. This is an *upper* bound on CPU-ms
(it includes network transit and TLS-amortized overhead at concurrency 64
from a well-connected host) and it is still only ~1.1–1.5 ms.

**(d) Native R2 baseline** (`docs/evidence/2026-08-05-r2-full-board-cost.md`):
whole-27-rule-family board pass costs 1.2–1.5 ms native wall time across all
rules combined; per-kernel median is nanoseconds to low microseconds. A
single test invocation exercises far less than a whole-board pass.

**All four measurements — none of them a Cloudflare bill — place per-request
CPU time well under 1 ms, most plausibly tens of microseconds**, consistent
with each other and with the parent plan's own R2 finding that CPU was never
the binding constraint at the kernel level. **None of this is the billed
figure.** Cloudflare's CPU-time accounting includes engine-level overhead
(isolate bookkeeping, V8 tick granularity under `workerd`'s own metering)
that this measurement cannot see from outside. The gap between "under 1 ms
measured here" and "the real billed number" is exactly O3, and it stays
open.

### 3.3 Monthly CPU-ms, same three scenarios, two bases (measured-proxy vs. deliberately conservative)

| Scenario | Requests/month | CPU-ms @ 0.069 ms/req (measured proxy) | % of 30M | CPU-ms @ 5 ms/req (conservative bound) | % of 30M |
|---|---:|---:|---:|---:|---:|
| Nightly only | 137,010 | 9,454 | 0.03% | 685,050 | 2.3% |
| Nightly + calm PR | 2,016,150 | 139,114 | 0.46% | 10,080,750 | 33.6% |
| Nightly + burst PR (sustained) | 15,464,946 | 1,067,081 | 3.6% | 77,324,730 | **258% — crosses** |

**Reading this table honestly:** under the measured-proxy basis (0.069
ms/request, from §3.2b), CPU-ms never approaches the quota in any scenario —
requests cross first, by a wide margin. Under a deliberately conservative
5 ms/request basis (chosen as a round number ~70× the measured proxy, to
bound the case where per-request overhead is far higher than anything
observed — e.g. isolate cold-start recurring far more often than the
code's caching model suggests), CPU-ms crosses the quota in the same
burst-PR scenario that already crosses the request quota. Either way, the
qualitative conclusion is the same: **the request count, not CPU-ms, is
what would first turn this tier's cost non-flat**, and it is the PR
cadence — not Phase 2 — that puts that within reach.

---

## 4. Where "stops being free" actually sits

The $5.00/month Workers Paid subscription is already a fixed, sunk cost
(active since 2026-08-07, for reasons unrelated to this tier's usage — it
raised the per-invocation CPU cap off the free tier's 10 ms ceiling). It
stops being *only* $5.00/month the first month either quota is exceeded:

- **10,000,000 requests/month.** At nightly-only cadence this tier uses
  1.37% of it. It is the calmer PR-cadence estimate (20.2%) that first makes
  this a real, non-negligible fraction of the quota, and the *observed*
  burst PR rate, if it were sustained, that would cross it outright (§2.4).
- **30,000,000 CPU-ms/month.** Never approached under the measured-proxy
  CPU-ms basis, at any cadence examined. Would be crossed only under the
  conservative 5 ms/request basis combined with the burst-sustained PR rate
  — i.e., only if both "PR cadence stays this high" and "per-request CPU
  cost is ~70× every direct measurement" are simultaneously true.
- **Per-invocation CPU cap** (Workers Paid default 30 s, configurable to 5
  min; confirmed live against `developers.cloudflare.com/workers/platform/
  limits/` and `/pricing/`, unchanged from the 2026-08-07 citation): no
  measured or estimated per-test cost here (µs to low ms) comes remotely
  close. Not a binding constraint at any scale this document considers.

**The honest headline: the current corpus, at its designed nightly cadence,
costs nothing beyond the flat $5/month, by a wide margin, on both quotas.
The thing that could change that first is not corpus size and not Phase 2 —
it is how often `wasm-tier-pr.yml` actually fires in steady-state operation,
a workflow that landed on the same day as this measurement and has no
settled cadence yet.**

---

## 5. Headroom for Phase 2 (R2.7)

Per the plan's own U3 framing, sized against **nightly cadence** and the
current corpus as the proxy:

- Budget before nightly-only sweeping alone would threaten the 10M/month
  request quota: `10,000,000 / 30 ≈ 333,333 requests/night`.
- Current nightly baseline: 4,567 requests/night → **~73× headroom** before
  nightly cadence alone is a request-quota risk.
- Treating "stops being negligible" as crossing 10% of the monthly request
  quota (a chosen, stated bar, not derived from anything in the plan):
  `1,000,000 req/month ÷ 30 ≈ 33,333 added requests/night`.
- Phase 2's mechanism (D2.4) generates one wrapper per (envelope-point,
  rule) pair. R2's own per-rule-family table
  (`docs/evidence/2026-08-05-r2-full-board-cost.md` §3) counts 8 `drc`
  rules, 6 `safety` rules, 3 `erc` rules — **R ≈ 17** candidate relevant
  rules before any are excluded as grid-rasterized-only (D2.3's exclusion,
  scoped later than this document). This R is **not yet real** — U1 (the
  `FabricationEnvelope` type) has not executed, so this is illustrative
  arithmetic against a placeholder, not a sized requirement.
  - `N_material ≈ 33,333 / 17 ≈ 1,960` envelope points before *nightly-only*
    added volume reaches 10% of the request quota.
  - `property_campaigns.rs`'s own precedent (300 seeds/property, 5
    properties = 1,500 total, per the Phase 2 plan §0.3) is **~6–8× smaller**
    than this threshold — a sweep sized at or somewhat above that precedent's
    order of magnitude stays in single-digit-percent territory of the
    nightly request quota.
- CPU-ms headroom is far larger under every proxy in §3.3 (2–3 orders of
  magnitude below quota at current scale) — **request count, not CPU-ms, is
  the binding axis for sizing N**, mirroring what R2/Q7 already established
  for memory (the isolate ceiling binds through grid resolution, not CPU).

**The qualifier that matters more than the arithmetic:** this N-threshold is
computed against nightly cadence, because that is the framing the plan text
asks for. If Phase 2's generated tests land in `temper-drc-rs` (D2.2 says
they do) and `temper-drc-rs` is one of the 3 tiers `wasm-tier-pr.yml`
already sweeps on every triggering push — which it is — then §2's PR-cadence
finding, not this section's nightly-only N, is what actually governs cost
risk. Under the calmer PR estimate alone (20.2% of quota with *zero* Phase-2
tests added), there is materially less than 5× headroom left before 10%
becomes 100%; under the observed burst rate, there is none. **Sizing Phase
2's N without first pinning down `wasm-tier-pr.yml`'s real steady-state
cadence is sizing against the wrong denominator.**

---

## 6. Memory ceiling — every deployed module, measured

All 15 modules, this session. The 8 tier-level modules were also measured
independently by the latest green nightly CI run (commit `86c6a01f`,
2026-08-11T03:22:22Z) — sha256-identical in both places, and identical to
the live-deployed `module_sha256` from each Worker's `/health` — so these
figures are the actual bytes serving production traffic right now, not a
stale or divergent local build. The 7 `temper-drc-rs` family shards were
built and measured locally only (no separate CI arm builds them).

| Module (Worker) | Tests | Size (bytes) | Peak linear memory | % of 128 MiB | Source |
|---|---:|---:|---:|---:|---|
| `temper-wasm-tier` (drc-rs full corpus) | 1,719 | 1,468,888 | 1.88 MiB | 1.47% | CI + local |
| `temper-wasm-geometry` | 2,232 | 826,363 | 1.75 MiB | 1.37% | CI + local |
| `temper-wasm-thermal` | 143 | 190,775 | 1.13 MiB | 0.88% | CI + local |
| `temper-wasm-design-bundle` | 24 | 256,462 | 1.19 MiB | 0.93% | CI + local |
| `temper-wasm-router-core` | 111 | 302,697 | 1.13 MiB | 0.88% | CI + local |
| `temper-wasm-constraint-compiler` | 69 | 161,064 | 1.13 MiB | 0.88% | CI + local |
| `temper-wasm-quality-oracle` | 125 | 208,099 | 1.13 MiB | 0.88% | CI + local |
| **`temper-wasm-io-types`** | 144 | 1,182,509 | **3.88 MiB** | **3.03%** | CI + local — **largest peak memory** |
| `temper-wasm-drc` (shard) | 1,510 | 265,427 | 1.25 MiB | 0.98% | local only |
| `temper-wasm-emc` (shard) | 15 | 114,962 | 1.13 MiB | 0.88% | local only |
| `temper-wasm-erc` (shard) | 12 | 69,389 | 1.13 MiB | 0.88% | local only |
| `temper-wasm-safety` (shard) | 25 | 114,275 | 1.13 MiB | 0.88% | local only |
| `temper-wasm-placement` (shard) | 18 | 99,111 | 1.13 MiB | 0.88% | local only |
| `temper-wasm-routing` (shard) | 18 | 111,432 | 1.13 MiB | 0.88% | local only |
| `temper-wasm-infra` (shard) | 121 | 1,207,391 | 1.75 MiB | 1.37% | local only |

**The largest deployed module by peak linear memory is `temper-io-types` at
3.88 MiB — 3.03% of the 128 MiB isolate limit, roughly 33× headroom before
this module alone would approach it.** It carries the fewest tests (144) of
any tier-level module but the largest per-invocation working set —
consistent with it being a flat set of KiCad/DSN serializers and parser
fixtures (per the topology file's own `_comment`) rather than many small
independent kernel cases. **The largest module by raw file size is the
`temper-drc-rs` full corpus at ~1.47 MB** — unremarkable; Cloudflare Workers
has no meaningful per-script size constraint at this scale.

No module is within two orders of magnitude of the 128 MiB limit, and none
is within an order of magnitude of the 64 MiB (50%-of-limit) warning
threshold the parent plan's R2 established. This reconfirms, at 4,567 tests
across 8 tiers, the same verdict R2 reached at 147: **no memory strategy is
required for the kernels as they exist today.** The only path back to the
2,400 MB wall is occupancy-grid resolution (24 MB @ 0.1 mm → 2,400 MB @
0.01 mm, unchanged since R2), which D2.3 already keeps out of Phase 2's
first sweep by construction, not by margin.

---

## 7. Cost discipline — what this measurement itself consumed

Two full unfiltered sweeps (§2.2) at 4,567 requests each = 9,134 requests,
plus ~20 individual `/run-test`/`/health` probes for §3.2's timing samples
and §2.1's census ≈ **~9,160 requests total this session**, all HTTP 200,
$0.00 marginal cost under any interpretation in this document (0.09% of a
single night's own nightly-cadence budget). No Worker, deploy, or schedule
was modified; `scripts/stage_wasm_families.sh` was run to produce the local
`.wasm` builds §3.2/§6 measure — all output is gitignored
(`packages/temper-worker/src/*.wasm*`) and `git status` remains clean.

---

## 8. Sources

- `docs/plans/2026-08-11-001-feat-wasm-tier-phase2-plan.md` — the task,
  §1 (stale corpus table), U3 (this unit's own text), O3.
- `docs/evidence/2026-08-10-wasm-tier-u4-closure-deployed-full-corpus.md` —
  the 1,708-test/852.3 tests/s baseline this document re-measures at 4,567.
- `docs/evidence/2026-08-07-wasm-tier-u8-volume-measured.md` — the
  $5.00/month cost basis, the ±20× run-to-run throughput-variance finding
  this document reproduces independently, and the prior "Analytics API
  unreachable without credentials" confirmation this document repeats.
- `docs/evidence/2026-08-05-r2-full-board-cost.md` — the 128 MiB isolate
  ceiling, the 24 MB/2,400 MB occupancy-grid projection, and the per-rule-
  family counts (drc 8, safety 6, erc 3) used in §5's N-threshold arithmetic.
- `tools/wasm/wasm_tier_topology.json` — the 15-Worker/8-tier inventory;
  its own `_comment` block's stated `temper-geometry: 722` is the stale
  figure this document's live measurement (2,232) corrects.
- `packages/temper-worker/src/worker_core.js` — read directly for §1
  (`/health`, `/run-test` semantics, the instance-caching model).
- `.github/workflows/wasm-tier-nightly.yml`, `.github/workflows/
  wasm-tier-pr.yml` — cadence, trigger paths, sweep scope, read directly
  (not assumed from commit messages).
- GitHub Actions API (`gh api repos/:owner/:repo/actions/workflows/*/runs`)
  — the measured PR-workflow and nightly-workflow run histories, §2.3.
- `gh run download 31455191432` — the unmodified nightly CI artifact
  (`worker_sweep_*.json`, `wasm_local_*.json`) used for §2.2's CI-throughput
  cross-check and §3.2/§6's CI-measured module figures.
- `developers.cloudflare.com/workers/platform/pricing/`,
  `.../workers/platform/limits/` — fetched live this session; unchanged
  from the 2026-08-07 citation ($5/mo flat, 10M req/30M CPU-ms included,
  $0.30/M and $0.02/M overage; 30 s default / 5 min max CPU-time-per-
  invocation on Paid).
- `tools/wasm/run_wasm_tests.mjs`, `scripts/stage_wasm_families.sh`,
  `tools/wasm/sweep_multi_worker.mjs` — the measurement tools this document
  runs, unmodified.
