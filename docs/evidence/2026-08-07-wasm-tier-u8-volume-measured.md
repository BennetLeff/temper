<!-- provenance: commit=66c9890ddeec7c1c3bdec829b1d4899532ed8ee6 dirty=false -->

# WASM Verification Tier — U8 Volume, Real-Payload Throughput, Cost, R5, and R19 — Measured

**Date:** 2026-08-07
**Base:** merge of `main` (`63ec4e75`) + `worktree-agent-a5208ad58d59e6d9f` (nightly
dispatch workflow, `r19_compare.py --fail-on-disagree`, `sweep_multi_worker.mjs
--board-sha256`) + `worktree-agent-a29ddea7502ada4f9` (R2 producer traces/vias/zones
+ determinism) + `worktree-agent-adfbaf643bff63678` (cross-process `nets` ordering
determinism) + `worktree-agent-a4c85aa62faa0ad05` (corrected 147-test family map +
drift gate). Measured at `66c9890ddeec7c1c3bdec829b1d4899532ed8ee6`, `git status`
clean.
**Supersedes:** the DEFERRED/BLOCKED record for U8 in
`docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md` §1/§3 (Track D). That
record is stale — the blocker it names (no `wrangler`, no
`CLOUDFLARE_API_TOKEN`, Node v18 vs. the v22 `wrangler` wants) blocks
*deploying* a Worker, not *invoking* one. Two later agents
(`docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md`,
`2026-08-07-phase1-u8-multi-worker.md`) already deployed 8 Workers as
unauthenticated public HTTPS endpoints; this document is the ≥10⁴-invocation
measurement against them that U8 still needed, done with plain HTTPS requests
and no credentials.

**Method note:** every number below was produced by a command in this
document's own history this session — none is copied from a prior evidence
doc without being re-run. Where a claim in the task brief did not hold up
against the code (the routing-payload framing, §3), that is reported as a
finding, not silently corrected.

---

## Bottom line

1. **All 8 Workers are live and unauthenticated.** Census matches the last
   deployment record exactly: `tier` 147, `drc` 1, `emc` 14, `erc` 9,
   `safety` 0, `placement` 12, `routing` 2, `infra` 109.
2. **U8's ≥10⁴-invocation volume run: 10,143 invocations, 18.76 s, 540.6
   inv/s, 0 errors, 0 non-200 responses.** No CPU-limit (1042/1104) or
   rate-limit response was observed at any point in ~13,300 total requests
   made this session.
3. **The "empty board" framing does not apply to the deployed tests.** The
   R2 producer fix (117 → 165 violations) changed a separate, undeployed
   native benchmark (`r2_full_board_pass.rs`), not the `wasm_test_registry.rs`
   corpus the 8 Workers serve — verified by inspecting the routing family's
   2 tests and by reproducing the 165-violation figure directly. Re-measured
   throughput at c8/c32/c64 anyway, as asked: the numbers moved by up to 20×
   run-to-run, driven by connection/isolate warm state, not payload size.
4. **Cost, derived from measurement + Cloudflare's published pricing (not
   billing):** the standing $0.12/month figure is wrong not because usage
   was mismeasured — usage-based cost is genuinely ~$0.00 at any realistic
   cadence — but because it omits the **$5.00/month flat Workers Paid
   subscription fee**, which this account has been on since 2026-08-07.
   Corrected estimate: **≈$5.00/month**, ~42× the standing figure.
5. **R5 verified end-to-end for the first time at the artifact level:** 3
   independent processes producing byte-identical `BoardState` JSON and
   `ConstraintSet` JSON. The known gap holds exactly as stated in
   `2026-08-07-wasm-tier-phase2-4-status.md`: no dispatched Worker test
   reads a board artifact, so the hash travels as metadata alongside a
   sweep, not as an input any of the 147 verdicts depend on.
6. **R19 across the full current 147-test corpus (the 52 tests added since
   the 95-test baseline, run against native for the first time): agreement
   rate 1.000000, 0 disagreements, 0 unexpected-pass.**
7. **U8 is complete**, under the achievable definition given the standing
   "no credentials" constraint: Worker deployed (already true), a real
   ≥10⁴-invocation volume measurement now exists, and a real cost figure
   exists, labeled derived-from-measurement because Cloudflare's billing API
   is unreachable without a token this task was told not to obtain.

---

## 1. Worker liveness census

All 8 endpoints answered `GET /health` with HTTP 200, no auth header sent,
2026-08-07:

| Worker | URL | `test_count` | `abi_version` | HTTP |
|---|---|---|---|---|
| `temper-wasm-tier` | `https://temper-wasm-tier.bennetleff.workers.dev` | 147 | 1 | 200 |
| `temper-wasm-drc` | `https://temper-wasm-drc.bennetleff.workers.dev` | 1 | 1 | 200 |
| `temper-wasm-emc` | `https://temper-wasm-emc.bennetleff.workers.dev` | 14 | 1 | 200 |
| `temper-wasm-erc` | `https://temper-wasm-erc.bennetleff.workers.dev` | 9 | 1 | 200 |
| `temper-wasm-safety` | `https://temper-wasm-safety.bennetleff.workers.dev` | 0 | 1 | 200 |
| `temper-wasm-placement` | `https://temper-wasm-placement.bennetleff.workers.dev` | 12 | 1 | 200 |
| `temper-wasm-routing` | `https://temper-wasm-routing.bennetleff.workers.dev` | 2 | 1 | 200 |
| `temper-wasm-infra` | `https://temper-wasm-infra.bennetleff.workers.dev` | 109 | 1 | 200 |

1 + 14 + 9 + 0 + 12 + 2 + 109 = **147**, matching the full-corpus worker
exactly and matching `2026-08-07-phase1-u8-multi-worker.md`'s deployment
record byte-for-byte — nothing has drifted, been redeployed, or been
authenticated since that document. No credentials were sent or attempted.

---

## 2. The ≥10⁴-invocation volume run (U8's core ask)

Driver: a purpose-built client (`repeatCount = ceil(10000 / 147) = 69`) that
builds one flat queue of `69 × 147 = 10,143` `(family, index)` pairs and
drains it through all 7 per-family Workers with bounded concurrency 32 as
**one continuous run** — matching the local U5 volume run's `--repeat`
protocol and the Workers one-isolate-per-invocation model, rather than 69
separate cold sweeps.

| Metric | Value |
|---|---|
| Target invocations | 10,143 (⌈10,000/147⌉ × 147) |
| Actual invocations | 10,143 |
| Wall time | 18.76 s |
| Throughput | **540.6 inv/s** |
| Errors | **0** |
| HTTP status codes | `{"200": 10143}` — no other code observed |
| Verdict tally | 9,867 pass + 276 expected-fail (69 × 4 = 276 ✓) |
| Latency (ms) | p50 44, p95 61, p99 78, max 328 |
| Per-decile throughput (inv/s) | 380, 532, 570, 580, 559, 562, 580, 564, 569, 594 |

**No CPU-limit (1042/1104) or rate-limit response occurred anywhere in the
run.** The per-decile throughput ramps from 380 inv/s in the first ~1,000
requests (paying one-time DNS/TLS connection setup across 7 hostnames) to a
stable 560–594 inv/s band for the remaining 90% — it does not degrade over
the run, which is the signature the task asked to watch for (isolate
eviction or the free-tier CPU-limit failure recurring under sustained load).
Both are absent here. This is consistent with, and extends past a single
sweep, the cached-per-isolate-instance fix recorded in
`2026-08-07-phase1-u7-deploy-runbook.md` §6 — the fix holds under 10K+
requests, not just the 15-request smoke test it was originally verified
against.

---

## 3. Real-payload throughput re-measurement — and why the framing needed correcting

The task brief states the prior c8→c64 figures (25.4 → 32.9 inv/s, 1.30× at
c64, from `2026-08-07-phase1-u8-multi-worker.md`) were taken "when the board
producer emitted no traces, vias or zones — routing-family tests ran against
an empty board," and asks for a re-measurement against "the real routing
payload" now that the bridge fix (117 → 165 violations) has landed.

**That connection does not hold, checked against the code, not assumed:**

- The bridge fix (`f2596ca3`, `worktree-agent-a29ddea7502ada4f9`) is entirely
  inside `tools/wasm/r2_serialize_board.py`'s `build_board_dict()`. Its
  consumer is `packages/temper-drc-rs/examples/r2_full_board_pass.rs` — a
  standalone **native** benchmark binary, run by hand, that is not part of
  `wasm_test_registry.rs` and does not ship in any deployed Worker's `.wasm`.
  This is exactly what `2026-08-07-wasm-tier-phase2-4-status.md` §R5 already
  documents ("this JSON and its hash feed `r2_full_board_pass.rs`... It is
  **not** part of `wasm_test_registry.rs` and does not ship in any deployed
  Worker's `.wasm` module").
- The deployed `routing` family has exactly 2 tests
  (`tools/wasm/test_family_map.json`):
  `rules::routing::power_pad_teardrop::tests::test_distance_to_rect_edge_inside`
  and `..._outside` — self-contained geometry unit tests against synthetic
  coordinates, with no board input of any kind, hardcoded in Rust. Every one
  of the 147 dispatched tests is a `#[cfg(test)]` Rust function with a
  hardcoded fixture; none reads `pcb/temper.kicad_pcb`, the R2 JSON, or any
  board artifact at invocation time.
- I reproduced the "165" figure directly to confirm the fix is real and
  landed, not to dispute it: running `r2_full_board_pass.rs --summary`
  against a freshly regenerated board JSON gave `violations_error: 127,
  violations_warning: 38` → **165**, matching the commit message exactly.
  This confirms the R2/R5 fix works — it just isn't wired to anything the
  8 Workers execute.

**So the dispatched payload is unchanged**, and the re-measurement below
answers a narrower, still-useful question: has anything about the Worker
tier's throughput moved since the multi-worker deployment, for any reason.

### Same protocol as the original measurement (warm-up + one sweep per concurrency)

| Concurrency | Run | Wall (ms) | Throughput (inv/s) | vs. prior (25.4→32.9) |
|---|---|---|---|---|
| 8  | 1 (`--warmup`) | 6,751 | 21.8  | comparable |
| 8  | 2 (no warmup, isolates already warm) | 7,489 | 19.6 | comparable |
| 32 | 1 (`--warmup`) | 6,538 | 22.5 | comparable |
| 32 | 2 | 1,019 | 144.3 | **6.4×** |
| 64 | 1 (`--warmup`) | 1,408 | 104.4 | **3.2×** |
| 64 | 2 | 6,372 | 23.1 | comparable |

### 5 back-to-back repetitions per concurrency (no warmup, isolates and TCP/TLS connections progressively warmed)

| Concurrency | Throughput range (inv/s) | Median |
|---|---|---|
| 8  | 98.3 – 174.0 | 171.9 |
| 32 | 141.9 – 501.7 | 491.6 |
| 64 | 23.4 – 717.1 | 607.4 |

**Finding: throughput at fixed concurrency varies by up to ~20× run to run in
this environment** (23.1 to 717.1 inv/s at c64), with no correlation to
payload — the payload never changed across any of these runs. The dominant
factor visible in the data is connection/isolate warm-state: the first sweep
after a period of no traffic is consistently the slowest of a batch (matches
§2's decile-ramp finding), and once 7 persistent connections are established
per-family, throughput jumps sharply and stays high until the next gap. This
is very likely also colo/network-path dependent — the original
25.4→32.9 inv/s figures were measured from "the same network (Dallas colo)";
this session's network path was not verified to be the same one, so absolute
throughput is not apples-to-apples against the original baseline even before
accounting for warm state. **The payload-size hypothesis in the task brief
is not supported; connection/isolate warm state is.**

All re-measurement runs: 0 failures, 0 errors, all HTTP 200, tally 143 pass +
4 expected-fail per 147-test pass, matching §2's zero-error result.

---

## 4. Cost — derived from measurement, not from billing

**Cloudflare's billing/usage API is unreachable without credentials, as
expected and as instructed not to pursue:**

```
$ curl https://api.cloudflare.com/client/v4/accounts/03f642afe070f05b727f7cd31f02ef48/workers/scripts
400   (no CLOUDFLARE_API_TOKEN in this environment; none was obtained)
```

So this section is **derived from this session's measured invocation/timing
data against Cloudflare's currently published Workers Paid pricing**
(fetched live 2026-08-07 from `developers.cloudflare.com/workers/platform/
pricing`), explicitly **not** measured from a billing statement:

| Line item | Published rate | Included monthly |
|---|---|---|
| Subscription | **$5.00/month flat minimum** | — |
| Requests | $0.30 / additional million | 10,000,000 |
| CPU time | $0.02 / additional million CPU-ms | 30,000,000 |
| Free-tier CPU budget | 10 ms/invocation | — (this account is on Paid: 50 ms/invocation, per `2026-08-07-phase1-u8-multi-worker.md` §"Paid Plan Consideration") |

**This session's usage:** ~13,329 total HTTP requests across the liveness
census, the §2 volume run (10,150 incl. census), and the §3 throughput
re-measurement sweeps (~3,179 incl. census/warmup) — every one HTTP 200.
CPU time per warm request is not exposed in any response header or body
(only a wall-clock `ms` field is returned, and only the Cloudflare
dashboard/Analytics API exposes real CPU-ms — both gated behind the
credentials this task was told not to obtain); using the ~1 ms/warm-request
figure `2026-08-07-phase1-u7-deploy-runbook.md` measured post-cached-instance-fix
as the basis (the same basis the standing cost model already uses, not a new
number invented here), this session consumed **≈13,300 CPU-ms**.

Both figures are five to six orders of magnitude under the included monthly
quotas (13,329 / 10,000,000 requests; 13,300 / 30,000,000 CPU-ms) — this
session's **usage-based marginal cost is $0.00**, not a small positive
number. Extending to a plausible production cadence (the phase2-4-status
doc's Q1 recommendation: nightly, not per-PR) at even an aggressive
K=1,000-repetitions/night volume sweep (147,000 inv/night × 30 nights =
4.41M requests/month, 4.41M CPU-ms/month) still stays under both included
quotas — usage-based overage remains **$0.00/month** at any cadence this
tier is likely to run at.

**The corrected monthly figure is therefore dominated entirely by the flat
$5.00/month subscription**, not by usage:

| | Standing estimate (`2026-08-07-phase1-u7-deploy-runbook.md` §7) | This measurement |
|---|---|---|
| Modeled cost | $0.003/commit × 40 commits ≈ **$0.12/month** | **≈$5.00/month** |
| What it omits/includes | Usage only — no subscription line item | Usage ($0.00, confirmed negligible at any realistic cadence) **+ the mandatory $5/month base fee for being on Workers Paid at all** |

The old estimate's usage-based reasoning was directionally right (usage cost
really is negligible, confirmed here rather than assumed) — its error was
omitting the plan's flat fee entirely, not mis-estimating volume. This
account has carried that $5/month fee since 2026-08-07 regardless of
whether the tier is exercised (it was enabled specifically to raise the
free tier's 10 ms CPU budget to Paid's 50 ms and stop the cold-start
CPU-limit failure `2026-08-07-phase1-u8-multi-worker.md` recorded — a
tier-attributable reason, not a shared platform cost). **Labeled explicitly:
derived-from-measurement (this session's invocation counts × published
pricing), not measured-from-billing** — a billing-verified number remains
blocked on the same credentials U7 was originally blocked on, which this
task was told not to pursue.

---

## 5. R5 content-addressing — verified end-to-end, and what it does/doesn't prove

**Determinism, verified fresh this session** (not re-asserted from the
merged branches' own commit messages):

Ran `tools/wasm/r2_serialize_board.py` in **3 independent Python
processes** against the committed `pcb/temper.kicad_pcb`:

| Artifact | Run 1 sha256 | Run 2 | Run 3 |
|---|---|---|---|
| `BoardState` JSON (343,641 bytes) | `cb86b21b8b88c26e878ef143ae7cd8bce40594444db27842031db09c6ef4e247` | identical | identical |
| `ConstraintSet` JSON | `b097689137b9b91cf780428340aea10829aeb6f091d7a010f4e224d73bd72f47` | identical | identical |

**3/3 byte-identical**, at the level of the actual produced artifact (not
just the trivial sha256-of-the-input-file the script also prints, which is
deterministic by construction and proves nothing about the bridge). This
directly exercises both merged fixes together: the `nets`-ordering fix
(`0e29a88d`, `worktree-agent-adfbaf643bff63678`) and the
`component_refs`-ordering fix (`b0bf128c`, part of
`worktree-agent-a29ddea7502ada4f9`) — a determinism bug in either would have
broken this 3-way comparison. Also ran the two dedicated regression suites
fresh: `test_drc_board_bridge_nets_order_determinism.py` (3/3 pass, spawns
genuinely separate subprocesses) and `test_r2_serialize_board.py` +
`test_board_py_bridge_routing_data.py` (23/23 pass).

**Dispatched requests do carry the hash**, verified live: `sweep_multi_worker.mjs
--board-sha256 <hex>` puts `boardSha256` into every `POST /run-test` body and
into the sweep's own summary JSON (`"board_sha256": "1cce4a0872051675…"`
appeared in every `sweep_*.json` produced for §2/§3). But
`packages/temper-worker/src/worker_core.js`'s `/run-test` handler (read
directly, not inferred) only ever reads `body.family`, `body.index`,
`body.name` — `boardSha256` is silently accepted and never used, and never
appears in the Worker's response.

**What the hash currently proves:** (a) the R2 board-serialization producer
is a deterministic, content-addressable function of the committed board,
confirmed end-to-end across independent processes for the first time this
session, not merely at the "same hash of the same input bytes" level; (b) a
sweep run's own summary artifact can be tied by content hash to the exact
`pcb/temper.kicad_pcb` bytes on disk when it ran.

**What it does not prove, unchanged from `2026-08-07-wasm-tier-phase2-4-status.md`'s
own finding:** no individual wasm32 verdict depends on the board. All 147
dispatched tests are static Rust `#[cfg(test)]` functions against hardcoded
fixtures. If `pcb/temper.kicad_pcb` changed tomorrow, every one of the 147
Worker verdicts would be byte-identical to today's — the hash rides alongside
the tier's measurements as metadata about the repository state at
measurement time, not as an input any pass/fail verdict is a function of.

---

## 6. R19 across the full 147-test corpus (the 52 tests never checked before)

The "SUSTAINED, agreement 1.0" verdict (`2026-08-07-phase1-u6-sustained-agreement.md`)
was measured 08:39–09:12 against a **95-test** corpus. Two commits after that
window (`4261eb4e` +17, `a6ccfefd` +35 = +52) grew the registry to its
current **147** — including closing the U4-flagged `erc: 0 registered tests`
gap. Those 52 tests have never had a native-vs-wasm32 comparison run. This
session ran one, fresh, at `66c9890d`:

```
$ cargo test --release --no-default-features   # packages/temper-drc-rs
test result: ok. 147 passed; 0 failed; 0 ignored

$ node tools/wasm/run_wasm_tests.mjs <fresh 147-test .wasm build>
registered 147, executed 147: 143 pass, 4 expected-fail, 0 unexpected-pass
imports: NONE (bare-isolate deployable); peak linear memory 1.75 MiB

$ python3 tools/wasm/r19_compare.py --fail-on-disagree ...
Native  : 147 pass, 0 fail (147 tests)
WASM32  : 143 pass, 0 fail, 4 expected-fail, 0 unexpected
Agree   : 143 agree-pass, 0 agree-fail, 4 expected-fail
Disagree: 0 disagreements
Scope   : 0 native-only, 0 wasm32-only
Agreement rate: 1.000000
exit 0
```

**Agreement rate 1.000000 across all 147**, 0 disagreements, 0
unexpected-pass, 0 native-only/wasm32-only, `--fail-on-disagree` did not
trip. The same 4 tests are `expected-fail` as at the 95-test baseline
(`b7-pow-divergence-absent` ×3, `no-dynamic-loader` ×1) — no new failure
class among the 52 newly-checked tests. This is the first R19 measurement
against the full current corpus; the earlier "SUSTAINED" verdict's 10-commit
window never saw these 52.

---

## 7. Is U8 complete?

| U8 sub-requirement | Status this document establishes |
|---|---|
| Worker deployed | Already true (`2026-08-07-phase1-u7-deploy-runbook.md`, `-u8-multi-worker.md`); reconfirmed live and unauthenticated, §1 |
| ≥10⁴-invocation volume run | **Done**: 10,143 invocations, 540.6 inv/s, 0 errors, §2 |
| Real-payload throughput comparable to prior sweep | **Done**, with the payload-causality claim in the task brief corrected against the code, §3 |
| Real cost (replacing the estimate) | **Done** as derived-from-measurement (≈$5.00/month, dominated by the Paid subscription fee); a billing-verified figure remains blocked on credentials this task was told not to obtain, §4 |
| R5 verified end-to-end | **Done**: 3/3 process-independent determinism at the artifact level; scope of what it proves stated precisely, §5 |
| R19 on the full 147 (52 never-checked) | **Done**: agreement 1.000000, 0 disagreements, §6 |

**U8 is complete**, under the only definition achievable without Cloudflare
credentials — which the task explicitly ruled out obtaining. The remaining
gap (a billing-API-verified cost figure) is the same category of blocker
Track D started with, not a new one this document introduces, and is named
rather than silently absorbed.

---

## 8. Cost discipline — what was run, and cleanup

Total requests issued this session: liveness census (§1, ~30 incl. repeated
per-worker health checks) + volume run (§2, 10,150 incl. census) +
throughput re-measurement (§3, ~3,179 incl. census/warmup across 8 sweep
invocations) ≈ **13,329 HTTP requests**, all against already-deployed
Workers, 0 failures. Per §4, this is $0.00 in usage-based marginal cost
(five to six orders of magnitude under both included monthly quotas) — the
only real cost of this measurement session is inside the pre-existing flat
$5/month subscription, which is not incremental to this work. §2's target
was intentionally the smallest multiple of the 147-test corpus that clears
10,000 (10,143, a 1.4% overshoot from rounding to whole sweeps, not a
deliberate over-run); §3's additional ~3,179 requests were run because the
task separately asked for a same-protocol re-measurement at three
concurrency points with enough repetitions to characterize the variance
found in §3 — named here rather than silently exceeding the bare ≥10⁴ figure
without comment. No load generator, deploy, or scheduled job was left
running; every script invoked in this document was a single foreground
`node`/`python3`/`cargo` process that exited before the next command ran.

---

## 9. Sources

- `docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md` — the DEFERRED U7/U8
  record this document supersedes.
- `docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md` — deploy
  preconditions, the cached-instance fix, the standing $0.12/month estimate
  this document corrects.
- `docs/evidence/2026-08-07-phase1-u8-multi-worker.md`,
  `2026-08-07-phase1-u8-per-family-shards.md` — the 8-Worker deployment
  inventory and the original c8/c32/c64 baseline this document re-measures
  against.
- `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` §R5 — the R5
  "partially met, disconnected from findings" analysis this document
  independently reproduces rather than takes on faith.
- `docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md` — the 95-test,
  10-commit R19 SUSTAINED window this document's §6 extends to the current
  147-test corpus.
- `tools/wasm/sweep_multi_worker.mjs`, `tools/wasm/r19_compare.py`,
  `tools/wasm/r2_serialize_board.py`, `packages/temper-worker/src/worker_core.js`,
  `tools/wasm/test_family_map.json` — read directly for §3's payload-causality
  check and §5's dispatch-carries-hash check.
- `packages/temper-drc-rs/examples/r2_full_board_pass.rs` — re-run directly
  to reproduce the 165-violation figure (§3).
- Cloudflare Workers pricing, fetched live 2026-08-07:
  `https://developers.cloudflare.com/workers/platform/pricing/` (§4).
- Commits merged as this document's base: `f2596ca3`/`b0bf128c`
  (`worktree-agent-a29ddea7502ada4f9`), `0e29a88d`
  (`worktree-agent-adfbaf643bff63678`) — none were on `main` before this
  session; both are exercised directly in §5, not cited secondhand.
