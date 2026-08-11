# `point_to_segment_distance` dedupe spike (issue #918) — decision evidence — 2026-08-11

<!-- provenance: commit=d21926ffbddd2b896801e4ff2336bd6b0cf30697 dirty=false (measurements taken in worktree <wt-918> on branch spike/point-to-segment-918; the tracked tree was pristine — only an untracked scratch driver was present, removed before commit) -->

**Direct answer: the 3 non-canonical copies ARE standardizable onto the canonical hypot contract — the divergence is a decision-immune pin artifact on real inputs, not real-input semantics — but the repoint cannot be executed within this spike's constraints.** The canonical home is a *private* fn in the never-touched `temper-geometry/src/creepage_check.rs`, and the real production consumers are internal Rust aggregate kernels (one of them in a file outside the allowed set). Standardizing requires the cross-crate plumbing + oracle re-pinning that issue #918 already said this "requires its own plan" for. This note is that plan's decision evidence: per-copy consumers, the divergence magnitude, why re-pinning is safe in the decision sense, and why it still cannot land here.

Verdict per copy: **KEPT-with-evidence** for all 3 (`constraint_model.rs`, `deterministic_leaf_drc.rs`, `deterministic_phase.rs`). No code changed; the whole tree is green.

---

## The four copies and their three contracts

| copy | file (crate) | degenerate arm | clamp | final distance |
|---|---|---|---|---|
| canonical | `temper-geometry/src/creepage_check.rs:54` | `denom == 0 OR !denom.is_finite()` → `py_hypot` | `py_min(1,t)` → `py_max(0,t)` (NaN t → 1.0) | `py_hypot` (CPython Dekker double-double) |
| A | `temper-design-bundle/src/constraint_model.rs:149` | `len_sq == 0.0` → `sqrt` | `if/elif/else` (**NaN propagates**) | `sqrt(dx²+dy²)` |
| B | `temper-drc-rs/src/deterministic_leaf_drc.rs:198` | `len_sq == 0.0` → `sqrt(pow+pow)` | `py_max(0, py_min(1,t))` (NaN t → 1.0) | `sqrt(pow+pow)` |
| C | `temper-design-bundle/src/deterministic_phase.rs:514` | `l2 == 0.0` → `pow(pow+pow, 0.5)` | `py_max(0, py_min(1,t))` (NaN t → 1.0) | `pow(pow+pow, 0.5)` |

Each copy is a Wave-4 migration of a *differently-written* pre-migration `_point_to_segment_distance` and is pinned bit-exact to that module's own verbatim oracle. The `pow(_, 0.5)`-vs-`sqrt` distinction is a deliberate, documented pin (`docs/evidence/2026-08-06-wave4-phase5-final-leaves-mutation-sweep.md`, row 10). There are additionally two *different* functions in `temper-geometry` itself (`geometry_kernels.rs:105` with a `len2 < 1e-12` degenerate threshold, and `drc_constraints_geometry.rs:107` with `seg_len_sq < 1e-10`) — out of scope here; they are documented separate references.

## Per-copy: WHO consumes it

### Copy A — `constraint_model.rs`
- **Production:** `is_candidate_edge` (Rust) → `dist_min_edge_to_pins` (`constraint_model.rs:222`) → the divergent kernel. Reachability: `temper-design-bundle/model_builder.rs:770,883` call `is_candidate_edge` only under `if pruning`; the default is `enable_geographic_pruning=False` (`router_v6/net_batching.py:871`). So the production path is real but opt-in.
- **Python shim:** `router_v6/constraint_model.py:187` `_point_to_segment_distance` → `constraint_model.point_to_segment_distance_py`. **No production caller** (differential-only; `_dist_min_edge_to_pins`/`_is_candidate_edge` delegate straight to Rust).
- **Pins:** `tests/router_v6/test_constraint_model_rust_differential.py` (`TestPointToSegmentDistance` random×40 / adversarial×15 / denormal / degenerate-zero-length / nan-inf; `TestDistMinEdgeToPins` random×30 + single-pin-equals; `TestIsCandidateEdge` random×30), `test_constraint_model_pbt.py`.

### Copy B — `deterministic_leaf_drc.rs`
- **Production:** `validate_signal_hv` (`deterministic_leaf_drc.rs:361`) → the divergent kernel. Reachability: temper-orchestration `placement_validation_stage.rs:120` calls back `stage._validate_signal_hv` → `_drc.validate_signal_hv_py` (`placement_validation.py:218`). **Hot path — every signal-HV constraint sweep.**
- **Python shim:** `deterministic/stages/placement_validation.py:254` `_point_to_segment_distance` → `_drc.point_to_segment_distance_py`. **No production caller.**
- **Pins:** `test_drc_leaf_rust_differential.py` (pts2seg bit-tests), `_drc_leaf_py_oracle.py` (kernel + `validate_signal_hv`), `_placement_validation_run_py_oracle.py` (D6 run oracle), `test_drc_leaf_pbt.py` (`test_mr3_segment_collapse` among the 15 failed).

### Copy C — `deterministic_phase.rs`
- **Production: none.** The only consumer class, `RoutingChannelAwareSlotStage`, is re-exported (`stages/__init__.py`) but **never instantiated**: the D5 orchestration (`run_zone_aware_slot_generation`) and the deterministic pipeline (`deterministic/__init__.py:405`) use `ZoneAwareSlotGenerationStage`. `_point_to_segment_distance`/`_min_distance_to_polygon`/`_compute_slot_routing_cost` all live on the dead subclass.
- **Python shim:** `deterministic/stages/zone_aware_slot_generation.py:337` → `deterministic_phase.point_to_segment_distance_py`. No production caller.
- **Pins:** `test_zone_aware_slot_generation_rust_differential.py` (`test_ptsd_pow_vs_sqrt_discriminating_operand`, `test_ptsd_randomized` among the 15 failed), `_zone_aware_slot_generation_py_oracle.py`, `_zone_aware_slot_generation_run_py_oracle.py`, `test_zone_aware_slot_generation_pbt.py` (`p4`, `p5`).

## WHY each contract differs from geometry's

The four kernels were written independently, pre-migration, in four different Python modules: `creepage_check.py` used `math.hypot` + builtin `min`/`max`; `constraint_model.py` used `math.sqrt` + `if/elif/else`; `placement_validation.py` used `sqrt(pow(_,2)+pow(_,2))` + `max(0,min(1,t))`; `zone_aware_slot_generation.py` used `pow(pow(_,2)+pow(_,2), 0.5)` + `max(0,min(1,t))`. Each Wave-4 port pinned its own oracle bit-for-bit. The resulting contract deltas:

1. **Final distance rounding** — `sqrt(dx²+dy²)` vs `pow(dx²+dy², 0.5)` vs Dekker `hypot(dx,dy)`. Differ by ≤1 ulp on a large class of ordinary inputs; `pow`-vs-`sqrt` is the deliberate pin.
2. **Degenerate arm** — canonical triggers on `denom==0 || !finite` (returns `hypot(point, endpoint)`); the others trigger only on `==0`. Non-finite direction vectors (inf/NaN segments) take the projection arm in the others; huge-magnitude degenerate inputs overflow to `inf` under `sqrt(pow+pow)` where `hypot` stays finite.
3. **NaN clamp** — copy A propagates NaN through `if/elif/else`; canonical/B/C clamp NaN `t` to 1.0 via builtin-`min`/`max` semantics.

## Divergence magnitude (measured 2026-08-11, Python mirrors of all four Rust kernels)

Reproducible driver (scratch, not committed — mirrors each kernel's exact expression order, `pow`/`sqrt`/`hypot` from host libm):

```python
import math, random
def py_min(a,b): return b if b < a else a
def py_max(a,b): return b if b > a else b
def geom(px,py,x1,y1,x2,y2):
    dx,dy = x2-x1, y2-y1; d = dx*dx+dy*dy
    if d == 0.0 or not math.isfinite(d): return math.hypot(px-x1, py-y1)
    t = py_max(0.0, py_min(1.0, ((px-x1)*dx + (py-y1)*dy)/d))
    return math.hypot(px-(x1+t*dx), py-(y1+t*dy))
def cm(px,py,x1,y1,x2,y2):
    dx,dy = x2-x1, y2-y1; d = dx*dx+dy*dy
    if d == 0.0: return math.sqrt((px-x1)**2 + (py-y1)**2)   # x*x exact squares
    t = ((px-x1)*dx + (py-y1)*dy)/d
    tc = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return math.sqrt((px-(x1+tc*dx))**2 + (py-(y1+tc*dy))**2)
def dr(px,py,x1,y1,x2,y2):
    dx,dy = x2-x1, y2-y1; d = dx*dx+dy*dy
    if d == 0.0: return math.sqrt(math.pow(px-x1,2.0)+math.pow(py-y1,2.0))
    t = py_max(0.0, py_min(1.0, ((px-x1)*dx + (py-y1)*dy)/d))
    return math.sqrt(math.pow(px-(x1+t*dx),2.0)+math.pow(py-(y1+t*dy),2.0))
def dp(px,py,x1,y1,x2,y2):
    dx,dy = x2-x1, y2-y1; d = dx*dx+dy*dy
    if d == 0.0: return math.pow(math.pow(px-x1,2.0)+math.pow(py-y1,2.0), 0.5)
    t = py_max(0.0, py_min(1.0, ((px-x1)*dx + (py-y1)*dy)/d))
    return math.pow(math.pow(px-(x1+t*dx),2.0)+math.pow(py-(y1+t*dy),2.0), 0.5)
# compare geom-vs-{cm,dr,dp} over corpora; count bit-mismatch, then classify:
#  1ulp-class = relative diff <= 1e-15,  catastrophic = larger,  nan/inf-flip = non-finite
```

Results (corpora and exact counts in the trace below):

| corpus | geom-vs-each mismatches | class |
|---|---|---|
| uniform `[-100,100]`, 3000 pts/segments | ≈1190–1193 / 3000 (≈40%) | **all ≤1-ulp** |
| board-like 200 mm, 3000 | ≈1156–1159 / 3000 (≈39%) | **all ≤1-ulp** |
| adversarial NaN/inf/1e308/denormal, 588 | ≈301–307 / 588 | ~12 ≤1-ulp, ~23 catastrophic, ~266–272 NaN/inf-flip |
| denormal-magnitude `[-1e-200,1e-200]`, 3000 | 3000 / 3000 | **all catastrophic** (geom → tiny finite; others flush to 0.0) |

(issue #918's "524/3024" is the same 1-ulp class at a different corpus density; the *class* is what matters and is confirmed here.)

**Catastrophic examples (issue #918, confirmed):** inf-segment `(5,3)->(0,0),(inf,0)` → geom `5.830951…`, constraint_model `NaN`; degenerate `1e308` point → geom `1.414e308` finite, constraint_model `inf` (intermediate `dx²` overflows). All require non-real coordinates.

**Decision impact — 0 flips in 6000 real-input cases.** Every production consumer feeds the distance into a threshold comparison (`dist_min <= max(k·span, m_min)`; `clearance < required_clearance_mm`; `min_dist < min_routing_channel`). Re-testing all three contracts against the canonical on 6000 board-scale cases with the *hardest possible* margins (`g·(1±1e-15)`, i.e. 4+ ulp from a flip), zero cases change the comparison outcome. A 1-ulp rounding difference cannot cross a mm-scale engineering threshold constructed from real geometry. The canonical contract is *strictly more correct* on the non-real classes (finite instead of inf/NaN/0).

## Why the repoint is still blocked in this spike

1. **The canonical home is private.** `creepage_check.rs::point_to_segment_distance` is a private `fn`, surfaced only as a `#[cfg(feature = "python")]` pyfunction. Cross-crate reuse requires promoting it to a shared `pub` symbol in `temper-geometry` — forbidden by the brief ("canonical geometry copy `creepage_check.rs` is NEVER touched"; "touch NOTHING else").
2. **Missing dependency.** `temper-design-bundle` has no `temper-geometry` dependency; `temper-drc-rs`'s is `optional` (python feature only). Adding/enabling is a `Cargo.toml` change — outside the allowed file set.
3. **The real consumers are internal Rust aggregates, not the Python shims.** Repointing only the (dead) Python `_point_to_segment_distance` shims would delete the divergent kernels' direct pins without changing any production byte, leaving each module with *two* point-to-segment semantics and self-contradictory `==` differentials (`test_single_pin_equals_point_to_segment`). Copy A's true consumer is in `model_builder.rs` — a file outside the allowed set entirely.
4. **The strict re-pin safety bar is not met for the 1-ulp class.** The spike's own definition ("pin difference only observable on inputs the caller never sees") fails: ≈40% of ordinary board-scale inputs differ by 1 ulp, so re-pinning changes *bit-level* production behavior on inputs the callers do see. It is decision-immune, but it is a production delta, which is exactly what issue #918 means by "requires its own plan + oracle re-pinning, not a dedupe".

## Correction: the "wire formats" 4-copy ledger premise

The kernel-dedupe agent attributed the 4-copy state to the "wire formats" gate (`make regen-check` → `wire formats: 4 kernel(s) reimplement a geometry helper`). **That attribution is factually wrong.** `scripts/check_wire_format_fidelity.py` scans only for `fn (pin_world_position|world_radius|pad_world_position)`; its current 4 entries are `congestion_analysis.rs`, `escape_via.rs`, `net_ordering.rs`, `terminal_planning.rs` — pin/radius kernels, not point-to-segment. Standardizing the point_to_segment copies cannot move that gate's count; the 4-copy point_to_segment state is not machine-tracked by any gate. (Also note the gate would not "pay down" from a point_to_segment dedupe at all.)

## The follow-up plan (the "own plan" that CAN execute this)

1. Promote the canonical kernel to a shared `pub` symbol in `temper-geometry` (e.g. `pub` on the existing fn, or a new small module re-exporting it — **no behavior change**, guarded by the existing differentials).
2. Add `temper-geometry` (default features) to `temper-design-bundle/Cargo.toml`; enable it for `temper-drc-rs`.
3. Repoint the three internal Rust callers (`model_builder.rs` `is_candidate_edge`→`dist_min_edge_to_pins`, `deterministic_leaf_drc.rs` `validate_signal_hv`, `deterministic_phase.rs` `min_distance_to_polygon`) **and** the three Python shims to the canonical kernel.
4. Delete the three divergent kernels, their `_py` bindings, and their unit tests.
5. Regenerate the affected differential oracles (`test_constraint_model_rust_differential.py` + `_constraint_model_builder_py_oracle.py`, `test_drc_leaf_rust_differential.py` + `_drc_leaf_py_oracle.py` + `_placement_validation_run_py_oracle.py`, `test_zone_aware_slot_generation_rust_differential.py` + `_zone_aware_slot_generation_py_oracle.py` + `_zone_aware_slot_generation_run_py_oracle.py`) to the canonical contract with documented drift (`make regen --accept-oracle-drift`), updating `scripts/oracle_hashes.json`.
6. Re-run the full differential + PBT + consumer suites. Expected production delta: ≤1-ulp on ≈40% of ordinary inputs (decision-immune, measured 0 flips) and a material improvement on non-real inputs (finite instead of inf/NaN/0).

Target after the plan: 1 canonical copy in `temper-geometry`, 0 reimplementations (copies A/B/C deleted). Until then, the 4-copy / 3-contract state is a **documented-KEEP**: each copy is pinned, green, and its divergence from canonical is decision-immune on real inputs.
