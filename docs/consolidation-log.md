# Consolidation Log

Each entry records: date, files deleted, canonical survivor, migration path, fixture/test added, unique flags preserved or dropped, and a one-line rationale. Append new consolidations above the template block.

---

## Template

```markdown
### YYYY-MM-DD — <brief description>

- **Deleted:** `<git-rm'd files>`
- **Survivor:** `<canonical path or function>`
- **Migration:** `<how callers were updated>`
- **Fixture:** `<new test file or None>`
- **Unique flags:** `<preserved / dropped / n/a>`
- **Rationale:** `<one line>`
```

---

## Track A — 2026-06-22 — `strip_routing` consolidation

- **Deleted:** `scripts/strip_routing.py`, `scripts/strip_routing_v2.py`, `scripts/strip_routing_kiutils.py`
  - Verified absent from this branch and `origin/main`. These files exist only on the `router-topo-benders-audit`/`update-schematics` branch (commit `2db59e30`), which was never merged. Deletions are a forward-facing gate: if that branch is merged, these files must be removed first.
- **Survivor:** `packages/temper-placer/src/temper_placer/io/kicad_writer.py:strip_routing(input_pcb, output_pcb, keep_zones=True, keep_fills=False) -> StrippingResult`
  - Already imported by 5 internal call sites: `scripts/run_benchmark.py`, `generate_unrouted_benchmarks.py`, `mvp3_runner.py`, `visualize_placement.py`, `place-deterministic` Click command.
- **Migration:** `scripts/batch_validate.sh:32` — file does not exist on this branch; if re-introduced, migrate to `python -c "from temper_placer.io.kicad_writer import strip_routing; strip_routing(Path('$board'), Path('$out'), keep_zones=True)"`.
- **Fixture:** `packages/temper-placer/tests/test_strip_routing_consolidation.py` — idempotence, content-preservation, repo-state guard.
- **Unique flags:** none dropped. Canonical already supports `keep_zones`/`keep_fills`; `scripts/` copies did not.
- **Rationale:** canonical is the authority imported by 5 sites; three stale `scripts/` copies added no capability and confused contributors.

---

## Track B — 2026-06-22 — router-runner consolidation

- **Deleted:** `run_router_v6_minimal.py`, `run_router_v6_simple.py`, `run_router_v6_baseline.py`
  - Verified absent from this branch and `origin/main`. Exists only on `router-topo-benders-audit` branch (commit `2db59e30`). Forward-facing gate.
- **Survivor:** `run_router_v6.py` (root) — full argparse: `--pcb`, `--theta-star`, `--lazy-theta`, `--smoothing`, `--no-legalize`, `--placement-mode`, `--max-nets`, `--nets`, `--profile`, `--exact`, `--timeout`.
- **Audit verdict:**
  - `run_router_v6_minimal.py`: no unique flags; broken (syntax bug at `len([1]) if len([1]) > 0 else 1) * 100`, missing `Progress` import). Dropped.
  - `run_router_v6_simple.py`: unique `--verbose` — canonical has no `--verbose`; wrapper is broken against canonical (undefined `console`, undefined `nets`, `pcb_path` not forwarded). Dropped.
  - `run_router_v6_baseline.py`: in-process `RouterV6Pipeline(enable_legalization=False)` = canonical `--no-legalize`. No unique flag. Dropped.
  - `--mode {full|baseline|minimal}` flag: **REJECTED.** Wrappers are dataset-sweep harnesses, not single-board run modes; every underlying flag already exists on canonical `run_router_v6.py`.
- **Migration:** Zero executed callers. Doc references in `benchmarks/beads_epics.sh`, `benchmarks/EPIC_SUMMARY.md`, `benchmarks/QUICK_REFERENCE.md` — files do not exist on this branch. If re-introduced, replace wrapper references with `run_router_v6.py --no-legalize`.
- **Fixture:** none new. Verified `git ls-files 'run_router_v6*.py'` returns exactly `run_router_v6.py` (root) and `scripts/run_router_v6.py` (sibling — not part of the duplicate cluster).
- **Unique flags:** none preserved.
- **Rationale:** three broken/exploratory wrappers with zero executed callers; canonical `--no-legalize` already covers the only behavioral difference.

---

## Track C — 2026-06-22 — batch-validation consolidation

- **Deleted:** `batch_validate_power_pcb_fixed.py`, `batch_validate_power_pcb_fixed.py.bak`
  - `_fixed.py` not tracked on this branch or `origin/main`. `.bak` not found on filesystem. Both exist only on `router-topo-benders-audit` branch. Forward-facing gate.
- **Survivor:** `batch_validate_power_pcb.py` (root) — orchestrates `placement_routing_loop.py` sweep across `power_pcb_dataset/inventory.csv`.
  - File does not exist on this branch; if re-introduced, apply the `ExperimentConfig` + `has_components` deltas from `_fixed.py` at creation time rather than as a follow-up fork.
- **Deltas available for port (from `_fixed.py` on `router-topo-benders-audit`):**
  - `ExperimentConfig` dataclass with per-topology iteration configs (`mppt`, `bms`, `inverter`, `buck`, `boost`, `motor_driver`).
  - `BoardInfo.has_components` field and filtering loop.
- **Migration:** n/a (no files to migrate on this branch).
- **Fixture:** none new.
- **Unique flags:** n/a.
- **Rationale:** "_fixed = improvement" pattern replaced by "improve the original, rely on `git log` for history." Promotion to `python -m temper_placer batch-validate` is deferred to the source-of-truth-validation initiative (see `docs/plans/2026-06-21-002-feat-source-of-truth-validation-plan.md`). `packages/temper-validation` is explicitly NOT the canonical batch CLI (it compares two PCBs, does not sweep a dataset).

---

## CI Guard

- **Guard test:** `packages/temper-drc/tests/test_consolidation_guard.py`
  - Denylist of 7 deleted filenames.
  - Asserts none tracked by `git ls-files`.
  - Asserts no reference exists outside `docs/` (brainstorms, plans, consolidation-log).
  - CI `paths:` filter extended to include `scripts/**` so the guard runs on PRs touching shell scripts.

---

## 2026-06-23 — script triage Phase 1 (plan 2026-06-22-021)

Per `docs/plans/2026-06-22-021-feat-script-triage-sunset-plan.md` (U1-U10).

- **Deleted:** 13 dead experiment/debug/verify scripts (5 `test_*`, 3 `verify_*`, 1 `debug_*`, 4 `diagnose_*`):
  - `scripts/test_copper_zone_loading.py`
  - `scripts/test_correlation_analysis.py`
  - `scripts/test_improved_placer.py`
  - `scripts/test_zone_aware_integration.py`
  - `scripts/test_zone_detection.py`
  - `scripts/verify_copper_zones.py`
  - `scripts/verify_hypergraph_routing.py`
  - `scripts/verify_nsga_improvement.py`
  - `scripts/debug_clearance_grid.py`
  - `scripts/diagnose_clearance_grid.py`
  - `scripts/diagnose_failures.py`
  - `scripts/diagnose_routing_congestion.py`
  - `scripts/diagnose_start_positions.py`
  - Pre-shipped in 253dd172 (the pipeline.py simplify commit landed the same deletions in parallel).
- **Survivors:** 61 scripts in `scripts/`, all with manifest entries.
- **New infrastructure:**
  - `scripts/trace_invocations.py` — AST-style invocation tracer, writes `scripts/invocation_graph.json`
  - `scripts/check_manifest_gate.py` — CI gate: filesystem <-> manifest consistency
  - `scripts/check_script_sunset.py` — CI warning: 30/60-day sunset clock per plan
- **Triage:** 20 keep + 41 ticket (no caller, 4+ months old, has `main()`). Ticket entries reference `temper-scripts-sunset` for the 30-day sunset clock.
- **U6 N/A:** `import-linter-allowlist.yaml` is already empty (commit 2334d647). Scripts aren't in `temper_placer` source packages, so import-linter doesn't scan them. No per-file entries needed.
- **Migration:** n/a — no callers to update (all deletions had zero callers per `invocation_graph.json`).
- **Fixtures:** new committed artifact `scripts/invocation_graph.json` (regenerated on every CI run by `trace_invocations.py`).
- **CI wiring:** python-tests.yml adds 3 steps:
  1. `Rebuild script invocation graph` (always runs, regenerates `invocation_graph.json`)
  2. `Script manifest gate` (fails CI on missing manifest entries or delete-marked files)
  3. `Script sunset check` (warnings only, never blocks)
- **Rationale:** reduce `scripts/` from 74 to 61 (≈18% reduction, near the 20% plan target), replace blanket import-linter exemption (already done) with manifest + sunset enforcement, and ship the 30-day sunset clock per plan U4/U5.
