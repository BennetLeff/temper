# `point_to_segment_distance` dedupe — execution record (issue #987) — 2026-08-11

<!-- provenance: commit=783ca00e77c2f056284de9a487c928cc335e7989 dirty=UNKNOWN -->

**Executes the plan whose decision evidence is `2026-08-11-point-to-segment-distance-dedupe-spike.md`** (issue #987, spiked as #918). The spike proved the 3 non-canonical Wave-4 copies are standardizable onto the canonical hypot contract — the divergence is a decision-immune pin artifact on real inputs — and the two blockers it identified (private canonical kernel; missing `temper-geometry` dependency in `temper-design-bundle`) were both authorized by the orchestrator for this execution.

Target state after this change: **1 canonical copy** (`temper-geometry::creepage_check::point_to_segment_distance`) and **0 reimplementations** of copies A/B/C.

## What changed, per plan step

### 1. Canonical kernel promoted to `pub`
`packages/temper-geometry/src/creepage_check.rs::point_to_segment_distance` is now `pub` (module `creepage_check` is already `pub mod`). **Body unchanged** — only the visibility + a doc note. Its pyo3 binding `point_to_segment_distance_py` was already registered (`bridge.rs:1557`) and wired (creepage_check.py).

### 2. Dependency wiring
- `packages/temper-design-bundle/Cargo.toml`: added `temper-geometry = { path = "../temper-geometry" }` (default features are empty, so no pyo3 in a `--no-default-features` wasm32 build). `Cargo.lock` updated (new transitive graph + a benign `thiserror 2.0.18 → 2.0.20` patch bump).
- `packages/temper-drc-rs/Cargo.toml`: **no change needed** — `temper-geometry` was already an optional dependency, enabled under the `python` feature, and `deterministic_leaf_drc.rs` (the only drc-rs consumer of the canonical kernel) is python-gated.

### 3. Repointed callers (who now calls the canonical kernel)
| copy | deleted kernel | repointed caller | canonical call site |
|---|---|---|---|
| A | `constraint_model.rs::point_to_segment_distance` | `constraint_model.rs::dist_min_edge_to_pins` (fed by `model_builder.rs:770,883` `is_candidate_edge` under opt-in `pruning`) | `temper_geometry::creepage_check::point_to_segment_distance(px, py, edge_ax, edge_ay, edge_bx, edge_by)` |
| B | `deterministic_leaf_drc.rs::point_to_segment_distance` | `deterministic_leaf_drc.rs::validate_signal_hv` (the signal-HV clearance hot path, via `validate_signal_hv_py`) | `temper_geometry::creepage_check::point_to_segment_distance(*hx, *hy, sx, sy, tx, ty)` |
| C | `deterministic_phase.rs::point_to_segment_distance` | `deterministic_phase.rs::min_distance_to_polygon` (no production consumer; differential/PBT-only) | `temper_geometry::creepage_check::point_to_segment_distance(x, y, p1.0, p1.1, p2.0, p2.1)` |

### 4. Deleted kernels + registrations + unit tests
Copy A: the `point_to_segment_distance` fn, `point_to_segment_distance_py`, its `register()` line, and the `point_to_segment_clamps_and_degenerates` unit test. Copy B: the fn, the pyfunction, the `register()` line, and `point_to_segment_distance_cases`. Copy C: the fn, the pyfunction, the `register()` line, and the two unit tests (`point_to_segment_projection_clamps`, `point_to_segment_degenerate_segment`). The `min_distance_to_polygon` aggregate and its `_py` binding survive (they fold the canonical kernel). Stale `.pyi` stubs for the two design-bundle pyfunctions removed.

### 5. Python shims repointed to the geometry kernel's name
- `router_v6/constraint_model.py::_point_to_segment_distance` → `_tg.point_to_segment_distance_py(px, py, seg_ax, seg_ay, seg_bx, seg_by)`
- `deterministic/stages/placement_validation.py::_point_to_segment_distance` → `_tg.point_to_segment_distance_py(*point, *seg_start, *seg_end)`
- `deterministic/stages/zone_aware_slot_generation.py::_point_to_segment_distance` → `_tg.point_to_segment_distance_py(px, py, *p1, *p2)` (its `_min_distance_to_polygon` still delegates to the surviving `deterministic_phase.min_distance_to_polygon_py`)
- The D5/D6 run oracles (`_zone_aware_slot_generation_run_py_oracle.py`, `_placement_validation_run_py_oracle.py`) mirror the same repoint.

### 6. Differential oracles re-pinned with documented drift
The three verbatim mirrors of the deleted sqrt/pow contracts were re-pinned to the canonical hypot contract (identical formula to the already-passing `test_creepage_check_rust_differential.py` oracle — the equivalence between Python `math.hypot` and Rust `py_hypot` is itself pinned there):

- `_constraint_model_builder_py_oracle.py::_point_to_segment_distance` (+ the in-file `_oracle_point_to_segment_distance` in `test_constraint_model_rust_differential.py`)
- `_drc_leaf_py_oracle.py::point_to_segment_distance`
- `_zone_aware_slot_generation_py_oracle.py::point_to_segment_distance`

Canonical contract re-pinned to: `denom == 0.0 OR !denom.is_finite()` → `math.hypot(point, endpoint)`; clamped projection `t = max(0.0, min(1.0, ...))` (builtin min/max, NaN `t` → 1.0); final `math.hypot`. Body-digest pins updated in the same commits: `test_constraint_model_builder_rust_differential.py::_ORACLE_BODY_DIGEST`, `test_deterministic_d5_rust_differential.py::_PINNED`, `test_deterministic_d6_rust_differential.py::_PINNED`. `scripts/oracle_hashes.json` recorded the 5 drifted oracles via `make regen --accept-oracle-drift` — the cause is this re-pin, named here.

Test-side updates: `test_ptsd_pow_vs_sqrt_discriminating_operand` → `test_ptsd_degenerate_uses_canonical_hypot_contract` (pins the canonical degenerate arm on a hypot-vs-`sqrt(pow+pow)` discriminating operand — a `sqrt`- or `pow`-close port would diverge on it); `test_drc_leaf_pbt.py::test_mr3_segment_collapse` and `test_zone_aware_slot_generation_pbt.py::test_p4_*` now assert the canonical `math.hypot` degenerate arm.

## Why the drift is safe (cite the spike's driver)

The spike (`docs/evidence/2026-08-11-point-to-segment-distance-dedupe-spike.md`, §"Divergence magnitude", measured 2026-08-11 with a Python mirror of all four Rust kernels) measured the four contracts against each other over 6000 board-scale cases across three corpora: ~40% of ordinary inputs differ by **≤1 ulp** (0 catastrophic, 0 nan/inf-flip in the uniform and board-like corpora), and **0 of 6000** decision comparisons (`dist_min <= max(k·span, m_min)`; `clearance < required_clearance_mm`; `min_dist < min_routing_channel`) flip when the three contracts are re-tested against the canonical at the hardest possible margins (`g·(1±1e-15)`). Every production consumer feeds the distance into such a mm-scale threshold; a 1-ulp rounding difference cannot cross it. On the non-real input classes (inf/NaN segments, 1e308 magnitudes, denormals) the canonical contract is strictly more correct — finite where the copies produced inf/NaN/0. This is a production byte-level delta on ~40% of ordinary inputs, which is exactly why it required "its own plan + oracle re-pinning" rather than a silent dedupe (issue #918's bar), and why every oracle re-pin here is attributed to this cause in the same commit.

## Gates

- `cargo test` (CI-consistent, default features) + `cargo check --features python --tests` + `cargo clippy --all-features --all-targets -- -D warnings` green for `temper-geometry`, `temper-design-bundle`, `temper-drc-rs`.
- Python suites green: `test_constraint_model_rust_differential.py` (269), `test_constraint_model_builder_rust_differential.py` (+ pbt, 45), `test_drc_leaf_rust_differential.py` + pbt (30), `test_zone_aware_slot_generation_rust_differential.py` + pbt (35), `test_deterministic_d5/d6_rust_differential.py` (78), `test_creepage_check_rust_differential.py` + creepage geometry PBT + boundary + pruning-geographic (178).
- `check_unwired_kernels.py`: the four deleted `_py` symbols simply un-register — **no NEW_UNWIRED, no STALE_ENTRY** (the `.unwired-kernel-inventory` ledger needed no change). `check_wire_format_fidelity.py` unaffected (its 4 entries are pin/radius kernels, not point-to-segment — see the spike's "Correction" section).
- `make regen --accept-oracle-drift`: recorded exactly the 5 re-pinned oracle hashes; wasm registries and README counts were already consistent.

## Remaining separate implementations (documented, out of scope)

`drc_constraints_geometry.rs` (`seg_len_sq < 1e-10` threshold), `geometry_kernels.rs` (`len2 < 1e-12` threshold), and `temper-rust-router-core::pruning.rs` (a pre-existing pure-Rust router-encoding kernel, not a Wave-4 migration copy) remain distinct functions with their own callers and differentials. The spike's "4-copy" ledger is exactly copies A/B/C + canonical; none of these three is one of those copies.
