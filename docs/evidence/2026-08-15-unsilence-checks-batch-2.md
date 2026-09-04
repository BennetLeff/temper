---
title: "Un-silencing batch 2 — three silenced check mechanisms made live (xfail_strict, dead Stage stubs, creepage/clearance drift gate)"
date: "2026-08-15"
category: evidence
module: ci_infrastructure
problem_type: evidence
component: development_workflow
severity: high
applies_when:
  - "auditing the 16-mechanism silent-check census (census/silent-check-mechanisms-2026-08-14)"
  - "deciding whether a check that 'exists' actually gates anything"
tags:
  - xfail-strict
  - dead-stage
  - drift-gate
  - un-silencing
  - honest-red
---

<!-- provenance: commit=3510300b79ba536b9f1c52171680c389ff7098f0 (persistent main commit for PR #1237 carrying this evidence; every verification run cited below was executed against the working tree at the merged change) dirty=false (record written after all three mechanism changes landed on ci/unsilence-checks-batch-2) -->

# Un-silencing batch 2 — three silenced check mechanisms made live

This is the batch-2 record for the silent-check census
(`census/silent-check-mechanisms-2026-08-14`, summarized in
`docs/HANDOFF-2026-08-15.md` §5). Batch 1 (agent 31, `ci/unsilence-checks-batch-1`)
handles: continue-on-error masks (4 in the required job), dormant Rust test
CI wiring, router_v6 collection, drift-gate tier fix. `cargo test --doc` was
wired by #1217 and the rotation-sign lint exemption was reverted by #1202 —
both before this batch.

The census document itself is not on `origin` (the branch exists locally but
the doc was never committed); §5 of the handoff plus the task's own
mechanism list are the working enumeration. Each mechanism below was handled
serially, one commit each, and the resulting state verified.

## Mechanism 1 — 22 non-strict `xfail`s (no `xfail_strict` ini)

**What it was**: pytest's default is that a test marked `@pytest.mark.xfail`
which *unexpectedly passes* (XPASS) is reported green. An xfail whose reason
is stale — the underlying defect closed — silently stops xfailing and turns
green, which is exactly the "correct check someone silenced" failure mode.
No pytest config in the repo set `xfail_strict`.

**What was done** (commit `52fc0aea8`):
- Added `xfail_strict = true` to all three pytest configs: root
  `pyproject.toml`, `packages/temper-placer/pyproject.toml` (the *effective*
  config for the router_v6 / requirements suites — CI runs them with
  `working-directory: packages/temper-placer`), and
  `packages/temper-workflow/pyproject.toml`.
- Verified all 4 `@pytest.mark.xfail` decorators in the repo already carry
  `strict=True` (they were strict from their originating commits
  `884e11b99` / `89c3fe415`), so no XPASS exists today; the setting
  future-proofs any xfail added later.

**Stale in-body xfails found and fixed** (`test_scale_resolution.py`): 5 of
the 7 in-body `pytest.xfail()` calls were *dead scaffolding* — the Inf/NaN
parametrizations they characterize had been dropped from the parametrize
lists. Measured against the current tree:

| xfail | parametrized? | measured behavior | disposition |
|---|---|---|---|
| Inf trace width crashes `copper_balance` | no | **no crash** — bug fixed | Inf restored to parametrize; xfail scaffold removed → passes loudly |
| Inf via diameter crashes `copper_balance` | no | **no crash** — bug fixed | Inf restored; scaffold removed |
| NaN/Inf coords crash `_segment_to_segment_dist` | no (`COORD_EXTREME` only) | **no crash** — bug fixed | parametrize widened to `COORD_BOUNDARY` (adds NaN/Inf); scaffold removed |
| Inf `min_clearance` "crashes" `verify_clearance` | no | `ValueError` from the module's finite-value guard (deliberate) | Inf restored; xfail kept with honest reason |
| Inf `default_creepage` "crashes" `verify_creepage` | no | `ValueError` guard | Inf restored; xfail kept with honest reason |

A future regression in the three fixed cases now **fails loudly** instead of
silently xfailing — the un-silencing. The two guard cases xfail with an
accurate reason.

**Verification**: `test_scale_resolution.py` 55 passed / 2 xfailed;
`test_clearance_boundary.py` + `test_empty_data_edge_cases.py` 190 passed /
18 xfailed (live crash-characterization xfails, confirmed reachable);
`test_geometric_degeneracy.py` + `test_thermal_relief_boundary.py` 126 passed
(live xfail confirmed); `test_copper_balance_properties.py` /
`test_creepage_properties.py` 12 passed / 5 xfailed (all decorator xfails
genuinely fail, no XPASS). The 2 failures in `test_finepitch_production_board.py`
are environmental (need `KICAD7_FOOTPRINT_DIR`), unrelated to this change.

## Mechanism 2 — 5 `Stage<BoardState>` impls with no execution path

**What it was**: `packages/temper-orchestration/src/clearance.rs` (Phase E
batch E3 of draft plan `2026-08-09-001`) defines five `Stage<BoardState>`
impls that no production pipeline registers:
`deterministic_pipeline.rs` / `router_pipeline.rs` never `add_stage` them;
only `tests/e3_stages_runner.rs` exercises them, with `None` payloads
(identity runs — the test's own header admits it proves "the SEQUENCING and
the Stage<BoardState> contract", not functionality). Two of the five are
literal no-op stubs: `IsolationBarrierStage` and `DomainClearanceStage` are
`stage_guard(name, || Ok(state))` — **nothing computed**, no payload field,
no kernel call.

The kernels they were meant to wrap are **live** via the Python side:
`router_v6/clearance_check.py` and `creepage_check.py` call the
`temper_orchestration` pyfunctions (`run_clearance_check`,
`run_creepage_check_impl`, `get_clearance_impl`) directly, and
`placer/cp_sat/isolation_barrier.py` / `domain_clearance.py` run the
isolation/domain compute in the cp_sat placer. So the two stubs only
manufactured the appearance of orchestration-engine checks.

**What was done** (commit `d824a80b2`):
- **Removed** `IsolationBarrierStage` and `DomainClearanceStage` (structs,
  impls, `lib.rs` exports, e3-test references). No behavior lost — they
  computed nothing.
- **Kept** the three compute wrappers (`ClearanceEngineStage`,
  `ClearanceCheckStage`, `CreepageCheckStage`) — they wrap the live kernels
  and carry payload marshalling, and are the draft plan's E3 scaffolding.
  Their unregistered status is now documented in the module header so nobody
  mistakes them for wired checks.
- `tests/e3_stages_runner.rs` updated to the three remaining stages with an
  honest header.

**Verification**: `cargo test --features python` — 1155 lib tests plus all
integration runners pass (e3 4/4); `cargo clippy --all-targets` clean;
import-linter gate passes.

## Mechanism 3 — `check_creepage_clearance_drift.py` CI invocation commented out

**What it was**: a real, sophisticated, discovery-based cross-source SSOT
gate (every creepage/clearance declaration across `elec/*.ato`,
`scripts/*.py`, `packages/**/*.py|yaml`, `configs/*.yaml`, found by walking
source, each (metric, tier) family with 2+ members must carry one value),
with 38 passing unit tests — but its CI steps were commented out under
"PREPARED, NOT ENABLED -- pending human approval" since 2026-08-08. It was
never wired into any workflow; the only record of it was the comment block
in `python-tests.yml` and a `gate_input_registry.py` entry.

The exit-5 blocker (selection alias `DEFAULT_TANK_CREEPAGE_MM` in
`tank_creepage.py` resolving to a Table-18-functional-insulation figure with
no comparable family) was already fixed on main by #1203 (dict-lookup form),
so the gate now runs to completion.

**What was done** (commit `1e074290d`):
- Enabled both steps in the `board-provenance-requirements-gates` job:
  the gate's 38 unit tests (green) and the gate itself.
- The gate is **red by design on origin/main** — exit 3 with 4 mismatched
  families. This is an honest, labelled red, not a silent one:
  - `[clearance/basic]` + `[creepage/basic]`: documented, investigated
    non-defects (different requirements sharing a coarse tier label; the
    gate's own docstring and the previous comment block cite the
    2026-07-29 investigation).
  - `[clearance/reinforced]`: reviewed semantic tier-label drift — 2.0mm is
    intra-class HighVoltage routing clearance, while 6.0mm is the HV-to-LV /
    isolated-domain barrier figure. The closed set is accepted without
    changing either safety value; see the 2026-09-03 evidence record.
  - `[creepage/reinforced]`: accepted 6.0mm legacy vs 12.6mm enforced PD3
    values, with 8.0mm deliberately rejected as a reappearing PD2 figure.
- The job (`board-provenance-requirements-gates`) is **not** in
  `required_contexts`, so the red is visible on every PR without wedging
  merges. The step is deliberately **not** `continue-on-error`'d — per this
  file's convention, a gate that can run must fail loudly. Un-redding it is
  a human value decision on the two DECISION-NEEDED families.
- `gate_input_registry.py` entry updated to match.

**Verification**: gate exits 3 against the origin/main tree with the
documented families (37 files / 149 declarations / 6 comparable families);
unit tests 38/38; `actionlint` clean on `python-tests.yml`; YAML valid;
registry tests pass.

## Surveyed, verified not-actionable (batch 2 did not touch)

- **`if: false` in workflows** — none exist.
- **allowlist entries** — all root allowlists (`.typecheck-allowlist`,
  `.coverage-allowlist`, `.net-classification-allowlist`,
  `.migration-narrowing-allowlist`, `.loc-allowlist.txt`, ...) are
  *enforced* monotonic-shrink ratchets with written justification rules in
  the gate scripts themselves; each has a live gate that rejects unjustified
  or non-shrinking entries. Not silenced.
- **`# type: ignore` / `# noqa` on safety-relevant lines** — surveyed; the
  remaining sites are lint noise (ARG001 unused args, E402/F401 imports),
  not safety-value silencing. The rotation-sign exemption (#1202) was the
  safety-relevant one and is fixed.
- **`--ignore` paths** — `regression.yml`'s two `--ignore` entries
  (`test_zone_pour_production_measurement.py`,
  `test_hybrid_pour_stitch_measurement.py`) are workload splits: both tests
  run in the *same* workflow immediately below, or nightly in
  `r9-evidence.yml`. Not disabled.
- **`skip` markers on safety tests** — 13 of 18 are conditional
  environmental guards (`make netlist` first, pcbnew unavailable, board
  refs missing); CI builds the netlist, so they do not trigger there. The 5
  unconditional ones are honest placeholders whose skip message says
  "not yet implemented" (e.g. `test_emi_filter.py:214`); they assert
  nothing, so un-skipping them would require *implementing* the
  verification — feature work, not un-silencing. Documented here as known
  verification gaps; they are visible as `S` in CI's requirements suite
  (`pytest_guard --min-tests 240`).
- **`only_run_on_schedule` instead of per-PR** — the four jobs narrowed
  2026-08-11 (`extended-bundle-workflow-checks`, `extended-cpsat`,
  router_v6 group 1, and the io/deterministic cluster) are *masked*
  (`continue-on-error`) steps whose results nothing can act on; their
  narrowing removed ~860 job-minutes/week of push-trigger load and
  "changes zero gating behavior (there was none to change)" per the inline
  comment. Un-narrowing before batch 1's un-masking lands would only restore
  load. `astar-nightly` is a deliberately nightly 45-minute exhaustive
  verification (by design, not demotion).
- **`workflow_dispatch`-only workflows** — `board-regeneration`,
  `corpus-batch`, `health-digest`, `metrics-reconcile`, `metrics-trend-check`,
  `r9-evidence` are intentional evidence producers / digest jobs (weekly or
  nightly cadence or on-demand), documented as such in their headers. Not
  per-PR gates that were demoted.
- **`regression.yml` / `ci_check_drc.py`** (handoff §6 note): the DRC
  ceiling truth gate runs only in `regression.yml`, which is red on main
  (golden-board DRC regression + an OOM at exit 137) and deliberately NOT in
  `required_contexts` — the manifest's own `_gate_vacuity_survey_note`
  documents "fix-then-require". This is an honest, investigated red with a
  documented path, not a silenced check; wiring it into required contexts
  while red would wedge every PR (the exact failure mode #1032 warns
  against).

## Status summary

| mechanism | status |
|---|---|
| 22 non-strict xfails / `xfail_strict` | **un-silenced** (`52fc0aea8`) |
| 5 dead `Stage<BoardState>` impls (2 no-op stubs) | **un-silenced** (`d824a80b2`) |
| creepage/clearance drift gate commented out | **enabled, honest red** (`1e074290d`) |
| `cargo test --doc` | done upstream (#1217) |
| rotation-sign lint exemption | done upstream (#1202) |
| continue-on-error (4 in required job) | batch 1 (`ci/unsilence-checks-batch-1`) |
| dormant Rust tests CI wiring | batch 1 |
| router_v6 collection | batch 1 |
| drift gate tier fix | batch 1 |
| if:false / allowlists / noqa / --ignore / skips / schedule-only / dispatch-only | surveyed, not-actionable (see above) |
