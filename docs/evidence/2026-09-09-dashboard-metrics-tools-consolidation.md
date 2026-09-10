<!-- provenance: commit=DERIVED dirty=false -->
---
title: Dashboard / metrics / tooling consolidation (Track 8)
date: 2026-09-09
status: consolidation, code changes landed on cleanup/dashboard-metrics
---

# Dashboard / metrics / tooling consolidation

**Question asked:** of the several surfaces that look like "dashboards" or
"metrics", and the many one-off measurement/experiment scripts under
`scripts/`, which are live (wired to CI or a documented master flow) and which
are dead duplicates or finished one-shot campaigns?

## Surface verdicts

| Surface | Verdict | Evidence |
|---|---|---|
| `dashboard/` | **SURVIVOR — live** | `dashboard-deploy.yml` builds/validates it and publishes to `gh-pages` on every main push; it consumes `power_pcb_dataset/metrics/pipeline_metrics.jsonl` (copied in at deploy time). Contains the CI-profiling dashboard (`index.html`) and the System Atlas (`dashboard/architecture/`), guarded on PRs by `architecture-atlas.yml`. |
| `power_pcb_dataset/metrics/` | **SURVIVOR — the metrics SSOT** | Produced by `metrics-record.yml` (`scripts/pipeline_metrics.py record`), folded by `metrics-reconcile.yml` (`scripts/reconcile_metrics.py`), drifted on by `metrics-trend-check.yml`, read by `dashboard-deploy.yml`. |
| `metrics/` (top level) | **dead duplicate — deleted** | 15 snapshot json/jsonl, created Dec 2025 – Jun 2026, superseded by `power_pcb_dataset/metrics/`. Zero consumers in `.github/workflows/`, `Makefile`, `scripts/`, `packages/`, or tests; the only prose references are archived `docs/legacy/` records and June-2026 planning docs. Not a write-guarded live artifact class any longer. |
| `metrics/dashboards/` | **dead placeholder — deleted** | Contained only a 44-byte `.gitkeep` ("Placeholder for generated dashboard files"). Nothing ever generated into it; no workflow, script, or doc references it. |
| `docs/architecture/` | **not a dashboard — left alone** | Static architecture write-ups (router-v6 era), cited from plans/evidence/requirements docs. Not wired to any CI dashboard; belongs to doc consolidation, not the metrics-dashboard surface. Deleting would break doc-path citations. |
| `dashboard/architecture/` | live atlas (see `dashboard/`) | Deployed with the dashboard; not touched. |

The survivor is unambiguous on CI wiring: `dashboard-deploy.yml` (deploy) plus
`metrics-record.yml` / `metrics-reconcile.yml` / `metrics-trend-check.yml`
(record/reconcile/trend) all key on `dashboard/` + `power_pcb_dataset/metrics/`
and none reference top-level `metrics/`.

## Tooling verdicts (one-off campaign drivers → `scripts/spikes/`)

All fourteen scripts below have **zero live callers** (no `.github/workflows/`,
`Makefile`, production import, or CI-run test) and their campaigns are
finished. They were moved to `scripts/spikes/` (out of the top-level
`scripts/` manifest scope, per the `check_manifest_gate` top-level-only scan),
not deleted, so their evidence remains re-runnable. `git log` dates are last
commit touching each file.

| Script(s) | Last touched | Why retired |
|---|---|---|
| `phase5_batch{1,2}_mutations.py`, `phase5_cli_adapters_workflow_mutations.py`, `phase5_hubs_mutations.py`, `phase5_final_leaves_mutations.py` | 2026-08-04…06 | Wave-4 anti-vacuity campaign drivers; campaign closed, records in `VERIFICATION.md`s and `docs/evidence/2026-08-0{4,6}-*`. `check_unwired_kernels.py` skips them by path predicate (still matches under `scripts/spikes/`). |
| `rcm_blocking_diag.py`, `rcm_empty_blocker_diag.py`, `rcm_pin_positions.py`, `rcm_spatial_analysis.py` | 2026-08-08 | One-shot placement-remediation diagnostics (evidence: `2026-08-08-placement-remediation-analysis.md`). |
| `generate_ground_plane.py`, `generate_power_islands.py` | 2026-08-11 | Spike CLIs superseded by production wiring: `router_v6/_ground_plane.py`/`_power_islands.py` now emit the planes in every `route_pcb()` run (`_ground_plane.py` docstring: "previously this generator was a standalone spike … with no production caller"). |
| `profile_router_v6_sampling.py`, `profile_rust_topology.py`, `bench_coarse_to_fine.py` | 2026-06-23…29 | `category: ticket` and >60 days stale under the sunset clock (delete-priority); moved rather than deleted to preserve rerun value. |

`scripts/tests/test_phase5_batch1_mutations.py` moved with its subject and its
`sys.path` insert updated to the new directory; 6 tests pass.

**Kept** (live or documented-canonical, verified during this pass):
`kicad_fill_zones.py` (shelled to by `test_zone_pour_production_measurement.py`),
`add_power_planes.py` (invoked by `scripts/run_clean_flow.sh`, which
`AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md` documents as the master design flow),
`measure_router_output_baseline.py` (wired to `regression.yml`),
`bench_rust_constraints.py` / `bench_rust_geometry.py` / `measure_uncapped_drc.py`
(keep-category utilities with recent use), all `tools/wasm/*` (wasm-tier CI),
`tools/measurements/astar_same_net_wiring/*` and
`tools/measurements/zone_emission_geos_parity_spike.py` (touched 2026-09-01/02,
active work).

## Bookkeeping

- `scripts/gen_repo_state.py`: dropped the now-empty `metrics` top-level-dir
  annotation; regenerated the README repo map (20 dirs).
- `scripts/manifest.yaml`: removed the 14 moved entries; refreshed `_meta`
  counts (180 scripts, 169 keep / 10 ticket).
- `scripts/invocation_graph.json`: regenerated by `scripts/trace_invocations.py`.
- Gates run and green: `check_manifest_gate.py`, `check_script_sunset.py`,
  `gen_repo_state.py`, plus `py_compile` + pytest on the moved test.
- Pre-existing manifest quirks observed, NOT fixed here (out of scope):
  duplicate `validate_perf_capture.py` entry; `capture_astar_backbone_corpus.py`
  entry missing `category`. 10 pre-existing sunset ESCALATEs for other
  `ticket` scripts remain open follow-ups.
