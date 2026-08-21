<!-- provenance: commit=6e81c1d97b0c570e4ef712798017624f7949bf88 dirty=false -->

# SPIKE: pulling Python PBT/metamorphic/differential CI work onto the WASM tier

**Date:** 2026-08-12
**Branch:** `spike/ci-offload-workers`
**Scope:** a mapping + offload plan only. No workflow or crate changes were
made (this is a spike; the metamorphic-mirror work is owned by a parallel
agent). The one file this spike touches is this note.

**Question.** `python-tests.yml` still runs Python-side hypothesis PBT,
metamorphic and differential suites on GitHub Actions runners, while the
wasm tier (`wasm_test_registry.rs` in 11 crates, `temper-worker/families/*`,
`tools/wasm/*.mjs`) already runs Rust unit tests + deterministic proptest
mirrors on Cloudflare Workers. Which of the Python groups could move, and
what mechanism would gate the move so a stale Worker cannot silently skip
CI coverage?

---

## Part 1 — the CI survey

### 1.1 The Python-side PBT/differential surface (`python-tests.yml`)

The PR-merge anti-vacuity gates live in the `test` ("Core Tests") job. Each
step runs a fixed file list under `scripts/pytest_guard.py --min-tests N`
so a silently-shrunk collection fails. Measured step durations from a real
push run (`gh api .../runs/31660781252/jobs`, 2026-08-13T02:25:31Z):

| Step (`python-tests.yml` `test` job) | Floor | Files (differential / PBT) | PBT files' hypothesis load | Measured |
|---|---|---|---|---|
| Run validation DRC differentials | 176 | 12 diff + 5 PBT (`grid_utils`, `via_placement`, `slot_generation`, `zone_geometry`, `zone_assignment`) | 40 tests @ max_examples 80–300 | **36 s** |
| Run Phase-5 report/explainability/clearance differentials | 131 | 10 diff + 3 PBT (`report`, `explainability`, `clearance_validator`) | 33 tests @ default | 2 s |
| Run Phase-5 cli differentials | 63 | 2 diff + 2 PBT (`timing`, `trace_commands`) | 31 tests @ 100–120 | 7 s |
| Run Phase-5 workflow differentials | 32 | 1 diff + 1 PBT (`route_and_measure`) | 13 tests @ default | 1 s |
| Run Wave-4 round-2 differentials | 1092 | 8 diff + 8 PBT (`heuristics`, `spatial_drc_cluster`, `constraint_model`, `channel_mapping`, `geometry`, `core_graph_cluster`, `bus_cohort`, `aesthetic`) | ~161 tests @ 50–200 | **33 s** |
| Run Wave-4 tail-tooling differentials | 76 | 3 diff + 0 PBT | — | 4 s |

Trunk-only (not PR-blocking, most masked or already narrowed 2026-08-11 per
`docs/evidence/2026-08-11-python-ci-load-inventory.md`): `invariant-rest`
(one hard-gate step sweeping `tests/validation/` incl.
`test_validation_kernels_pbt.py`), `invariant-router-v6-1/2`,
`extended-cpsat`, `closure`.

The prior inventory's headline still holds: **the differential files are
retained oracles** — the wasm tier proves the Rust side is internally
consistent; only the differentials pin the migrated Rust kernels
bit-exactly against the verbatim Python oracles. They are CPython-bound
(they import compiled pyo3 extensions) and are *not* offload candidates.
The offload surface is the **PBT files inside those same steps**.

### 1.2 The wasm tier

- 11 crates carry `wasm_test_registry.rs`; registered (executable) counts at
  this commit: `temper-constraint-compiler` 1900, `temper-geometry` 8280,
  `temper-io-types` 6638, `temper-rust-router-core` 3438, `temper-drc-rs`
  3281, `temper-thermal` 2697, `temper-quality-oracle` 2602,
  `temper-orchestration` 999, `temper-design-bundle` 33,
  `temper-rust-router` 20, `temper-pcl-ir` 2. **≈31,890 registered tests**
  (topology comment quotes 4,701 *deployed* — a subset, family shards etc.).
- `proptest!` bodies cannot be registered (dev-dependency, absent from the
  non-test build); the established fix is **deterministic campaigns**
  (`property_campaigns.rs` in 8 crates + `wasm_campaign_prng.rs`):
  fixed-seed `SplitMix64` corpora, each case its own `#[test]`, e.g. 20
  seeds × 10 properties = 200 registered tests in `timing.rs` alone.
- Jobs: `wasm-tier-nightly.yml` (04:40 UTC — `local-sweep-r19` builds every
  tier's wasm32 registry **from the commit under test** and runs it natively
  on Node; `worker-dispatch-r19` sweeps the *deployed* Workers, gated by
  R5.1 `tools/wasm/check_deployed_freshness.mjs`), `wasm-tier-pr.yml`
  (advisory, D5.4 — scoped to touched tiers, sweeps **deployed** Workers
  against the last green nightly census), `wasm-tier-deploy.yml` (push to
  `main` on corpus-affecting paths + schedule).

## Part 2 — overlap map: Python PBT groups vs wasm coverage

Per-PBT-file verdict, checked by grepping each crate's registry + campaign
files (this commit):

| Python PBT file | Kernels it drives (via pyo3 shims) | Registered in a wasm registry? | Deterministic campaign / proptest mirror? | Offload verdict |
|---|---|---|---|---|
| `cli/test_timing_pbt.py` (T1–T4, compare_stage) | `temper_orchestration::timing::compare_stage` | ✅ `timing::tests::WASM_TESTS` — **203 tests** (P1–P10 × 20 seeds + 3 unit) | ✅ **P7–P10 mirror T1–T4 exactly** (verdict consistency, floor monotonicity, monotone-in-current, zero-baseline guard) | **ALREADY MIRRORED — the one clean offload today** |
| `cli/test_timing_pbt.py` (T5, T7, p95) | `timing::p95` (CPython `decimal`) | ❌ structurally impossible (`Bound<PyAny>` → decimal) | ❌ | Cannot move |
| `cli/test_trace_commands_pbt.py` | `trace_filter.rs` | ❌ | ❌ | Mirror candidate |
| `validation/test_validation_kernels_pbt.py` (trunk-only `invariant-rest`) | drc-rs `validation_kernels` P1–P7 | ✅ | ✅ drc-rs `property_campaigns.rs` mirrors **validation_kernels P1–P7** (infer_package_type, tht_hole_collisions, min_hv_lv_trace_clearance, issue_fingerprint) | **Already mirrored**, but runs trunk-only already — low value |
| `deterministic/test_grid_utils_pbt.py`, `via_placement_pbt.py` | `temper_geometry::grid_utils`, `via_placement` | ✅ unit tests only (6 grid_utils) | ❌ no proptest/campaign | Mirror candidate |
| `deterministic/stages/test_slot_generation_pbt.py`, `zone_geometry_pbt.py`, `zone_assignment_pbt.py` | `temper-design-bundle::deterministic_stages` | ❌ (design-bundle registry has no `deterministic_stages` module) | ❌ | Mirror candidate |
| `report/test_report_pbt.py`, `explainability/test_explainability_pbt.py` | `temper-io-types` report/explain | ❌ structurally (`#[cfg(feature = "python")]` whole-pyo3 surfaces, no kernel underneath) | ❌ | **Cannot move** |
| `requirements/test_clearance_validator_pbt.py` | drc-rs `req_safe_01` (IEC-60335 compliance) | ❌ (only `rules::drc::clearance` registered) | ❌ (campaign covers edge_distance/ipc/pymath, not req_safe_01) | Mirror candidate |
| `heuristics`, `spatial_drc_cluster` (5 kernels), `channel_mapping`, `core_graph_cluster`, `bus_cohort`, `aesthetic` (Wave-4 round-2 PBTs) | geometry/drb/quality-oracle kernels | ✅ as **unit tests** (heuristics, resource_bound, power_plane, diff_pair_inference, trace_width_assignment, dense_package_detection, channel_mapping, core_graph_geometry, aesthetic — all in registries) | ❌ **zero proptest refs** in any of those kernel files; no campaigns | **Highest-value mirror candidates — the PBT halves of the 33 s step** |
| `router_v6/test_constraint_model_pbt.py` | `temper-design-bundle::constraint_model` | ❌ | ❌ | Mirror candidate |
| `requirements/validators/test_geometry_pbt.py` | `geometry_kernels.rs` | ❌ (`geometry_kernels` is python-gated) | ❌ | Cannot move (or kernel needs a portable split) |
| `workflow/test_route_and_measure_pbt.py` | workflow-level composite | ❌ (copper_length campaign exists but not this composite) | ❌ | Mirror candidate (low value, 1 s step) |

### The honest headline

- **Only `timing`'s compare_stage cluster is already wasm-mirrored** — 203
  registered wasm tests mirror the 4 Python T-properties, and it is the only
  clean "skip/reduce the Python step today" candidate. It is also the
  *smallest* step (7 s).
- **The expensive PBT runs (validation 36 s, Wave-4 round-2 33 s) are NOT
  mirrored yet.** Their kernels are registered as *unit* tests, but the
  property-level coverage (idempotence, symmetry, monotonicity, MRs) has no
  campaign. These are the highest-value *future* mirrors — and the parallel
  agent is already building the metamorphic (R1d) halves of exactly these
  files; the R1c PBT-property campaigns are the natural completion.
- **report/explainability/geometry-validators/p95 cannot ever move** —
  whole-pyo3 surfaces with no portable kernel, or CPython decimal/`PyAny`
  semantics. These stay on Actions permanently.

## Part 3 — the offload plan

| CI job step | What it runs | Wasm-tier status | Offloadable? | Mechanism |
|---|---|---|---|---|
| Run Phase-5 cli differentials (7 s) | timing diff + PBT, trace_commands diff + PBT | timing T1–T4 **mirrored** (203 registered); trace_commands not | **Partially — yes for T1–T4** | Mark the step `wasm-covered` for the mirrored cluster; keep p95 + differentials; skip or `max_examples`-reduce the mirrored tests |
| Run validation DRC differentials (36 s) | 12 diff + 5 PBT | PBT kernels unit-registered, **no campaign** | After mirroring | Mirror the 5 deterministic-stage PBT groups as campaigns, then reduce Python side |
| Run Wave-4 round-2 differentials (33 s) | 8 diff + 8 PBT | 7/8 kernels unit-registered, **no campaign** | After mirroring (parallel agent is doing the MR halves now) | Mirror R1c properties as campaigns (follow-on to the metamorphic work), then reduce Python side |
| Run Phase-5 report/explainability/clearance (2 s) | 10 diff + 3 PBT | report/explain structurally absent; clearance validator not registered | **No** (permanent) | None |
| Run Phase-5 workflow (1 s) | route_and_measure | not mirrored | Low value | Skip |
| Run Wave-4 tail-tooling (4 s) | 3 differentials, no PBT | — | No (differential = retained oracle) | None |

### Recommended first offload (the spike's concrete proposal)

**Reduce the `timing` PBT cluster inside "Run Phase-5 cli differentials".**
The 203 registered `timing::tests::p{7,8,9,10}_*_seed_*` wasm tests assert
the same compare_stage relations (zero-delta-at-parity, positive-delta,
effective>=floor, zero-margin-threshold) as Python T1–T4. The Python step
keeps: the two differential files (retained oracle), the p95 properties
(CPython-bound, cannot mirror), and trace_commands. The T1–T4 properties
are marked `wasm-covered` and either skipped via a marker or kept at a
token `max_examples` (e.g. 5) to preserve the pytest_guard floor count.

The exact workflow diff (sketch only — **not applied by this spike**):

```yaml
# in python-tests.yml, "Run Phase-5 cli differentials" step:
# wasm-covered: timing compare_stage T1-T4  <- orchestration::timing::tests
#   p7_compare_stage_zero_delta_at_parity_seed_000 .. _019 (20)
#   p8_compare_stage_positive_delta_pct_for_regression_seed_000 .. _019 (20)
#   p9_compare_stage_effective_baseline_at_least_floor_seed_000 .. _019 (20)
#   p10_compare_stage_zero_margin_exact_threshold_seed_000 .. _019 (20)
#   + compare_stage_guards_zero_baseline
# Coverage authority: registry at THIS commit (gen_wasm_test_registry.py
# --check, fast-gates job) + nightly local-sweep-r19 (built from the same
# commit, no deployed-Worker staleness possible). Do NOT key the skip off
# the deployed Workers' census: that is the advisory arm.
run: >
  uv run python ../../scripts/pytest_guard.py --min-tests 63 --
  tests/cli/test_timing_rust_differential.py
  tests/cli/test_trace_commands_rust_differential.py
  tests/cli/test_timing_pbt.py          # T1-T4 wasm-covered (reduced examples)
  tests/cli/test_trace_commands_pbt.py
  -v --tb=short -p no:cacheprovider --maxfail=10
```

### The freshness-gating mechanism (how a stale Worker cannot silently skip CI)

Three independent layers, all already deployed — the offload leans on them
rather than inventing new machinery:

1. **Registry-at-commit is the authority, not the deployed Worker.**
   `scripts/gen_wasm_test_registry.py --check` runs in the `fast-gates` job
   ("WASM test registry matches committed (drift + unregistered gate)") and
   fails if a `#[test]` added to a registered module is missing from the
   generated `WASM_TESTS` const, or a module that could register is on no
   list. A `wasm-covered:` annotation in a workflow step therefore resolves
   against the *current commit's* registry — the exact corpus the nightly
   local-sweep builds and runs. If the mirror is deleted/renamed, the
   annotation's names no longer exist in the registry, `--check`-style
   resolution fails, and the Python step must run in full (fail-closed,
   not silently-green).
2. **`tools/wasm/check_deployed_freshness.mjs` (R5.1) is the deployed-arm
   guard.** It asks every deployed Worker how many tests it carries and
   compares against per-tier built counts from the commit under test
   (count + content-hash since issue #945), failing loudly on mismatch.
   The 2026-08-07..10 incident (147 deployed vs 1,708 built, green the
   whole time) is exactly the failure this control exists for; the wasm
   tier's own PR verdict (`wasm-tier-pr.yml`) already refuses to score a
   sweep whose freshness check failed. The nightly *local* arm needs none
   of this — it builds from the commit, so staleness is impossible by
   construction; that is why the offload keys off the registry + local
   sweep rather than the deployed census.
3. **Deploy latency is bounded, not assumed.** `wasm-tier-deploy.yml`
   redeploys on push to `main` for corpus-affecting paths (each tier's
   crate dir + shared infra) and on a nightly schedule — so even the
   *deployed* Workers converge within ~24 h. The advisory PR verdict
   (D5.4) additionally re-checks deployed freshness per run against the
   last green nightly baseline.

**Rule for future offloads:** a Python PBT step may be reduced/skipped only
when (a) every skipped property names a live test in the current commit's
`wasm_test_registry.rs` (checked by an annotation-resolver in CI), and
(b) the nightly local sweep of a commit carrying that registry went green.
The deployed Workers' census is never the gate.

## Part 4 — cost/benefit of the recommended first offload

- Python side: "Run Phase-5 cli differentials" is 7 s/run; the timing PBT
  portion is a few seconds of that. Per the 2026-08-11 inventory's cadence
  (~159 executing pushes + ~132 PRs + ~1 nightly ≈ 292 runs/week), even a
  halving of that one step saves only ~15–20 runner-minutes/week. **The
  value of this first offload is not the minutes — it is proving the
  `wasm-covered` gating mechanism end-to-end on the one already-mirrored
  cluster**, so the 36 s + 33 s steps (≈ 20 runner-hours/week combined at
  that cadence, minus the differential halves) can follow the same path as
  their PBT campaigns land.
- Wasm tier cost of absorbing the mirrors: 20 seeds × N properties per
  campaign, ~31,890 tests already registered; the cost doc
  (`docs/evidence/2026-08-11-wasm-tier-cost-at-scale.md`) shows nightly
  cadence at 1.37% of the request quota and per-test CPU-ms far under
  budget — adding a few hundred campaign seeds is noise on the tier's
  existing volume.

## Part 5 — not done (by design)

- No `.github/workflows/*` change was made (spike; and the parallel agent
  owns the metamorphic-mirror crate work this plan depends on).
- No crate/registry edits (parallel agent owns the mirror implementation).
- The differential (retained-oracle) files are explicitly out of scope per
  `docs/evidence/2026-08-11-python-ci-load-inventory.md` — the wasm tier
  cannot replace bit-exact Python-oracle pinning.
- `report`/`explainability`/`geometry_kernels`/`p95` are structurally
  un-offloadable (whole-pyo3 surfaces, CPython `decimal`, python-gated
  modules) — flagged so no future agent wastes a cycle trying.

**Follow-ups filed as part of this spike's landing:** (1) implement the
`wasm-covered` annotation resolver (extend `gen_wasm_test_registry.py` or a
tiny `scripts/check_wasm_covered.py` in the `fast-gates` job); (2) apply
the timing reduction once (1) lands; (3) after the parallel agent's
metamorphic mirrors land, add R1c PBT-property campaigns for the
deterministic-stage and Wave-4 round-2 kernels, then reduce those two steps.
