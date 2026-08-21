# Triage of the 388 CI-uncovered tests (`.ci-test-coverage-inventory`)

Ran every entry in `.ci-test-coverage-inventory` and triaged each failure.
Nothing was fixed, wired into CI, deleted, skipped, or re-baselined — this
document is the triage, not a change.

Base: `gate/ci-test-coverage` @ `dd52178db`.
`pcb/temper.kicad_pcb` sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
verified identical before and after the run.

## Environment

`make venv-isolate` under `env -u CONDA_PREFIX` in a private worktree. Before
attributing anything, the symbol-verifying stale-extension gate from
`gate/extension-symbol-verification` was run against this venv:

    10/10 extension modules fresh; 1087/1087 registered symbols present

`temper_io_types.write_types` is present here (the shared-venv staleness noted
in the task did not apply). `kicad-cli 10.0.5` available; `pcb/temper.kicad_dru`
regenerated from `scripts/generate_kicad_dru.py`; `elec/build/default.net` built
via `make netlist`; `pcb/fp-lib-table` present. Every failure below was
re-confirmed in a serial re-run in this environment.

## Counts

### pytest — 369 files

| | |
|---|---|
| collected | 12,652 (collect-only, **0 collection errors**) |
| executed | 12,643 |
| passed | 12,546 |
| failed | 42 |
| errors | 0 |
| skipped | 55 |
| files timing out at the 2400 s guard (NOT failures) | 1 |

File-level, of the 369: **340 fully green**, **19 carrying all 42 failures**,
**9 collecting zero tests**, 1 exceeding the 2400 s per-file guard
(`tests/closure/test_router_completion.py` — three SM gates each shelling out
to a full closure pipeline; not a failure).

### ctest — 19 entries

| | |
|---|---|
| 11 registered-but-CI-unselected suites | 260 Unity tests, **0 failures** |
| 8 unregistered `add_executable` targets | 50 Unity tests, **0 failures** |
| all 14 registered suites under `ctest` | 14/14 passed |

The whole firmware surface builds with zero errors and passes. CI selects 3 of
14 registered suites (`ctest -R "state_machine|fault_list"`, `ctest -R
sil_fault_tests`). **The ctest half of the inventory is pure neglect — no
defects.**

## Real defects, ranked by consequence

### 1. Four OVP protection nets have no netclass — DRC enforces 0.2 mm where the SSOT says HighVoltage (2.0 mm)

Detected by `scripts/tests/test_sync_kicad_netclass_assignments.py::TestRealRepoInvariant::test_real_kicad_pro_agrees_with_ssot`.

`pcb/temper.kicad_pro` is missing netclass assignments for four nets that exist
on the committed board:

    safety.ovp.r_div_top1-p2   safety.ovp.r_div_top2-p2
    safety.ovp.r_adc_top1-p2   safety.ovp.r_adc_top2-p2

The SSOT (`TEMPER_NET_ASSIGNMENTS`) assigns all four to `HighVoltage`. They
appear in none of the 100 explicit `netclass_assignments` and match none of the
8 `netclass_patterns` (`+*V`, `VCC*`, `VDD*`, `DC_BUS*`, `GATE_*`, `PWM_*`,
`VBOOT_*`, `AC_*`), so they resolve to `Default`.

Consequence, two layers deep:

* `Default` clearance is **0.2 mm**; `HighVoltage` is **2.0 mm** — a 10x
  shortfall on the OVP divider / ADC-sense top resistors, which sit on the
  high-voltage side of the protection dividers.
* Worse, the fab-authoritative `pcb/temper.kicad_dru` keys its cited rules on
  netclass membership (34 `NetClass` conditions, e.g.
  `A.NetClass == 'ACMains' && (B.NetClass == 'HighVoltage' || ...)`), covering
  **17 `clearance`, 6 `creepage` and 12 `track_width` constraints**. Because
  these four nets resolve to `Default`, **none of those rules fire for them at
  all** — including every creepage rule, on a mains-referenced protection
  divider.

Root cause — a fail-closed guard blocking an unrelated write:

    $ uv run python scripts/sync_kicad_netclass_assignments.py --check
    ERROR: 'CGND' (protected) now resolves to a declared kicad_pro netclass
    ('GND') -- this script refuses to proceed rather than silently pick it up.
    ...reserved for a human decision.
    EXIT=5

The sync refuses for the whole file, so the four pending OVP assignments never
land. Refusing is right in isolation; refusing file-wide is what leaves a
clearance hole.

Why nobody saw it: `python-tests.yml` Gate 6 covers netclass **parameters**
(a class's own clearance/track_width) and its own comment states that the
assignment-level checks "only ever compare/write `netclass_assignments`". The
only test that checks net→class assignment against the SSOT is this one, and
it is in the uncovered inventory. `sync_kicad_netclass_assignments.py`'s
manifest entry calls itself "the CI tripwire against future drift"; no CI job
runs it.

Note: this proves DRC is not *enforcing* HighVoltage on those nets. Whether the
routed geometry currently violates 2.0 mm is a separate measurement.

Reproduce:

    uv run pytest scripts/tests/test_sync_kicad_netclass_assignments.py -v
    uv run python scripts/sync_kicad_netclass_assignments.py --check

### 2. Rust obstacle rasteriser has lost GEOS parity on the real board — 3,020 cells freed that GEOS blocks

Detected by `packages/temper-placer/tests/router_v6/test_occupancy_grid_rust_differential.py::test_rasterize_area_polygons_matches_shapely_on_real_board`.

The test asserts on the first failing layer only (F.Cu, 623). Re-running the
same comparison across all six layers, feeding **the identical eroded polygon**
to both rasterisers:

| layer | mismatches | Rust FREE / GEOS BLOCKED | Rust BLOCKED / GEOS FREE |
|---|---|---|---|
| F.Cu  | 623 | 273 | 350 |
| In1.Cu | 17 | 17 | 0 |
| In2.Cu | 17 | 17 | 0 |
| In3.Cu | 1053 | 503 | 550 |
| In4.Cu | 2136 | 1138 | 998 |
| B.Cu  | 1384 | 1072 | 312 |
| **total** | **5,230** | **3,020** | **2,210** |

`docs/evidence/2026-08-15-rust-obstacle-map-integration.md` records **0
mismatches across ~22.3M cells** for this exact measurement. It is now non-zero.

This is consumed in production: `router_v6/occupancy_grid.py:482` calls the same
`_tg.rasterize_area_polygons_py`. That call site's own comment states the
convention and the stake:

> a cell center exactly on the boundary is NOT contained (stays blocked, the
> conservative direction — the boundary is already C-space-inflated, so freeing
> it would let A\* route at exactly clearance distance). Parity against the GEOS
> reference on the real board's six layers is proven by the differential in
> `test_occupancy_grid_rust_differential.py`.

That parity claim is currently false, and 3,020 cells err in the permissive
direction — the router can treat as routable space that the authoritative
geometry engine excludes, where the exclusion already carries the half-trace
-width inflation.

Scope nuance: the file's 30 synthetic parity tests (including the explicit
boundary-aligned-cell case) all pass. The divergence appears only on the real
board's heavily eroded, near-degenerate geometry — consistent with a numerical
robustness gap, not a gross algorithmic error. The board gained copper since
2026-08-15 (96 -> 151 zones, `#1312`/`#1333`), which plausibly exposed it rather
than caused it.

Reproduce:

    uv run pytest packages/temper-placer/tests/router_v6/test_occupancy_grid_rust_differential.py::test_rasterize_area_polygons_matches_shapely_on_real_board -v

### 3. `optimize --no-loop` cannot succeed on any board with a non-zero origin

Detected by `packages/temper-placer/tests/cli/test_optimize_no_loop.py` (4 failures).

`cli/__init__.py:714` writes with `board_origin=board.origin`, converting solved
positions into absolute file coordinates. The after-write oracle at `:746` is
then handed the raw `cp_result.positions`, still in the normalized frame.
`check_placement_roundtrip`'s docstring requires positions "in the same
coordinate frame the writer wrote (file coordinates)", so every component and
pad mismatches by exactly `board.origin` and the CLI raises
`Round-trip oracle FAILED after write` and exits 1.

Observed offset on the fixture is (90, 70) mm; the fixture's Edge.Cuts origin is
(90, 70). The real board's origin is **(8, 20)** — also non-zero, so the path is
broken for `pcb/temper.kicad_pcb` too.

Introduced by `e5539273a` (#1050), which added `board_origin=board.origin` to
the write call and did not offset the oracle's expected positions.

Direction of failure is safe: the board written is correct; the oracle wrongly
rejects it, so the command fails closed rather than emitting bad geometry. Blast
radius is the CLI only — the oracle has no other caller, and
`scripts/_placement_subprocess.py` solves to JSON without writing or oracling.

Reproduce:

    uv run pytest packages/temper-placer/tests/cli/test_optimize_no_loop.py -v

### 4. CI invokes two `pipeline_metrics.py` subcommands that do not exist

Detected by `scripts/tests/test_pipeline_metrics.py` (8 failures,
`module 'pipeline_metrics' has no attribute 'cmd_spc' / 'cmd_slo'`).

`scripts/pipeline_metrics.py` registers only `trend` and `record`. Three CI
steps invoke the missing ones:

* `.github/workflows/metrics-trend-check.yml:76` — `pipeline_metrics.py spc`
* `.github/workflows/metrics-trend-check.yml:112` — `pipeline_metrics.py slo`
* `.github/workflows/health-digest.yml:89` — `pipeline_metrics.py spc`

The step captures the argparse error into `spc-result.json` and then
`json.load`s it, so the step fails. `metrics-trend-check.yml` is weekly
(`cron: "0 8 * * 1"`), so this fails out of sight. The implementation exists
only on unmerged `origin/fix/completion-pct-metric-chain` (`550269f49`,
"implement the `slo` and `spc` subcommands CI already invokes").

Consequence: SPC and SLO monitoring have never run. No board-safety impact.

### 5. `backlog_grace_seconds` default of 0 is unloadable

Detected by `scripts/tests/test_classify_changed_paths.py` (5 failures,
`manifest backlog_grace_seconds must be a positive integer`).

`check_required_checks.py:135` calls `_positive_int(raw, "backlog_grace_seconds", 0)`
while `_positive_int` (`:211`) rejects `value <= 0`. So the documented default is
rejected and any manifest omitting the key fails to load. The dataclass default
(`:78`) is `0` and `:890` branches on `backlog_grace_seconds > 0`, both of which
show 0 is meant to be a valid "disabled" value — that branch is dead.

The shipped `.github/required-checks.json` sets `7200`, so production is
unaffected; only manifests omitting the key (including these tests' fixtures)
break. Lowest consequence here.

## Stale tests — behaviour deliberately changed, test not updated

All attributed to a landed commit.

| Test(s) | Pins | Changed by |
|---|---|---|
| `test_courtyard_violation_report::test_real_board_violation_count_in_expected_range` | `5 <= courtyards_overlap <= 11`, now 1 | `6285d6889` (#1173) "land 7 of 8 verified courtyard-collision fixes (courtyards_overlap 8 -> 1)" |
| `test_e2e_netclass_ssot::test_class_pairs_contain_safety_critical_entries`, `test_netclass_feedback::test_yaml_loaded_carries_because_text` | `"IEC 60335-1" in because` | `5b481f697` (#1226) relabelled the 6.0 mm family UNSOURCED after debunking the Table 16 citation. **The 6.0 mm value itself is unchanged** — only the citation text. |
| `test_adapter_convert_marshal_rust_differential` (5), `test_pipeline_route_rust_differential` (2) | Python oracle returns via diameter 0.6; production returns 0.9 | `968d1a33d` (#1316) added the annular floor in `Via::new` (`drill + 2*ANNULAR_RING_TARGET_MM` = 0.3 + 0.6 = 0.9). Safety-improving; the test oracle lagged. |
| `test_strip_copper::test_matches_real_production_board_zone_count` (96 vs 151), `test_r2_serialize_board::…deterministic_across_parses` (2149 vs 4553), `test_u2_stackup_role_ssot` (3), `test_ground_plane::…improves_real_board_pad_connectivity`, `test_power_islands::…measurably_improve_connectivity` | Hardcoded counts / "board has no copper yet" preconditions | `23b5daf8d` (#1312) regenerated the board's copper (isolated_copper 109 -> 0) and `342e1bd08` (#1333) re-routed it |
| `test_place_route_loop_temper::test_optimize_non_convergent_loop_fails_closed` | Expects the "did not converge" message | Mock is `netlist=object()`; production now reads `netlist.components` in the pre-loop REQ-SAFE-01 / F.Fab audit wiring. Under-specified mock. **The fail-closed property it guards still holds** — exit code is non-zero and no output is written; only the message differs. |
| `test_closure_bottleneck_perf::test_temper_pcb_within_budget` | `elapsed <= 210.0`, measured 1134 s | Budget set in `47bab3388`; the closure pipeline's real runtime is the ~1193 s the task itself cites. Stale budget, not a fresh regression. |
| `test_quality_metrics_oracle_pin::test_corpus_corridor_scores_match_pin[piantor_right]` | Pinned corridor-score hex for one external corpus board | Not attributed — see Cannot determine. |

## Environment artifacts / vacuous

* **4 files collect zero tests** because of a module-level `pytest.importorskip("jax")`
  on a pipeline that was deliberately removed (the CLI prints "The JAX
  gradient-descent pipeline has been removed"; `jax` is in no pyproject):
  `test_cli_error_handling.py`, `test_export_command.py`, `test_multi_seed.py`,
  `test_validate_command.py`. These are green-but-vacuous — wiring them into CI
  would add **zero** coverage.
* `firmware/test/test_sil_coverage.py` — 0 tests under pytest; already ledgered
  as executed via `scripts/check_sil_coverage.py --gate`. Correct exclusion.
* `tests/requirements/validators/test_points.py` — 0 tests collected; the
  `TestPoint*` names are helper enums/dataclasses with `__init__`, not tests.
  The file is a fixture module that pytest's naming convention picks up.
* `test_stage2_golden_parity.py`, `test_stage4_golden_parity.py`,
  `test_stage4_monolith_parity.py` — module-level
  `pytest.skip("No golden fixtures available", allow_module_level=True)`.
  Environment artifact: the golden fixtures are absent from a fresh clone, so
  these would need fixture generation before they could contribute anything.
* `test_dag_expr_perf::test_parse_perf_ab_with_parity` — a microbenchmark
  (`Rust parse is 1.4x SLOWER`) measured under the 4-way-parallel sweep.
  Timing-sensitive; re-run serially before treating as real.

## Cannot determine

* `test_quality_metrics_oracle_pin::test_corpus_corridor_scores_match_pin[piantor_right]`
  — one external-corpus board's pinned corridor consolidation score differs
  (`0x1.4e47ef130a942p-2` vs pinned `0x1.125f8a6956f77p-2`); the other 52
  parametrisations pass. Not attributed to a commit; low consequence (external
  corpus board, not the product board). The oracle pin was left untouched.

## Verdict

The 388 are **mostly neglect, but not only neglect.** All 19 ctest entries and
12,545 of 12,641 pytest tests pass — a surface that is 99.7% green and would
largely just work if wired in. But the 41 failures are not uniform rot: five are
real defects, and two of those touch mains-voltage safety directly — a netclass
gap that disables the cited creepage/clearance DRU rules on four OVP protection
nets, and a router obstacle map that has silently lost GEOS parity in the
permissive direction on the production board. Both were invisible precisely
because the only tests that check them are the ones CI does not run.
