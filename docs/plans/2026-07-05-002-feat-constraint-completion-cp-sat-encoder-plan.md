---
type: feat
origin: docs/brainstorms/2026-07-05-constraint-completion-cp-sat-encoder-requirements.md
status: abandoned
swept: 2026-07-25
swept_basis: "only 1/20 named paths exist"
---
# feat: Constraint Completion — CP-SAT Encoder for 8/8 PCL Types + Discrete Rotation

## Summary

Build the CP-SAT constraint encoder from scratch — replace the forbidden soft `_encode_loop_area` with a hard physics-grounded ceiling (500mm², tol=0), add ANCHORED / KEEPOUT / ALIGNED handlers, add discrete 4-way rotation for all non-polarized parts via `AddElement`/`IntVar`, and wire the two-tier audit+DRC gate. Decisive result: the temper board places with all 8 PCL constraint types honored, with non-polarized parts rotated, and passes real KiCad DRC at 6mm with zero violations.

**Scale:** Greenfield CP-SAT module (3-4 new files), 3 new constraint handlers, 1 loop-area replacement, 1 rotation model, 3 new audit checks. ~30 rotatable parts on temper board.

---

## Problem Frame

The CP-SAT feasibility spike handles 4 of 8 PCL constraint types (Separated, Enclosing, OnSide, Adjacent). The existing `_encode_loop_area` in the routing SAT bridge is a stub that creates a hardcoded ChannelSeparationConstraint with no relationship to `max_area_mm2` — and the JAX loss-bridge version was a soft weighted-sum wirelength minimization, which is the forbidden pattern under the umbrella's Objective-Discipline Contract. Four constraint types are missing handlers entirely, and no rotation infrastructure exists anywhere. The L_loop derivation settled the physics: loop area is a hard ceiling at 500mm² (79% of the 635mm² IGBT overvoltage limit), with tol=0. Rotation is CP-SAT's paradigm dividend — discrete 4-way enumeration that avoids the JAX softmax-rotation bug class.

---

## Implementation Units

### U1. Set Up OR-Tools Dependency and CP-SAT Module Skeleton

**Goal:** Add `ortools` to `pyproject.toml`, create the `placer/cp_sat/` package structure, and establish the `CpSatModel` wrapper class.

**Requirements:** R1-R4 (foundational for all encoder work)

**Dependencies:** None — greenfield, no existing CP-SAT code

**Files:**
- Modify: `packages/temper-placer/pyproject.toml` — add `ortools>=9.10`
- Create: `src/temper_placer/placer/cp_sat/__init__.py` — public API surface
- Create: `src/temper_placer/placer/cp_sat/model.py` — `CpSatModel` wrapper around `CpModel`
- Create: `tests/placer/cp_sat/test_model.py` — basic model construction tests

**Approach:** The `CpSatModel` class wraps `ortools.sat.python.cp_model.CpModel` and provides:
- `add_component(ref, x_start, y_start, width, height) -> ComponentVars` — creates interval vars and position IntVars
- `add_rotation(ref, is_polarized: bool) -> IntVar | None` — creates 4-valued rotation var (None for polarized)
- `add_no_overlap_2d(x_intervals, y_intervals)` — wraps `AddNoOverlap2D`
- `solve(time_limit_s: float) -> CpSolverSolution` — wraps solver invocation with time limit
- Assumption Boolean management for UNSAT-core extraction

**Patterns to follow:** SAT bridge dispatch pattern (`sat_bridge.py` TYPE_HANDLERS); `Component.bounds` for initial sizes; `placer/deterministic.py` `PlacementResult` for output shape.

**Test scenarios:**
- `CpSatModel()` creates an empty model with no errors
- `add_component("Q1", x=0, y=0, w=10, h=20)` returns ComponentVars with valid IntVar fields
- `add_rotation("Q1", is_polarized=False)` returns IntVar with domain [0, 3]
- `add_rotation("K_5", is_polarized=True)` returns None (pinned to 0)
- `solve(time_limit_s=1.0)` returns `FEASIBLE` or `OPTIMAL` on an empty model in <100ms
- Model with 33 components (temper board scale) can be solved in <2s

**Verification:** `ortools` imports cleanly; model creation + solve round-trips on a trivial 2-component test.

---

### U2. Build the PCL-to-CP-SAT Encoder with Existing 4-Type Handlers

**Goal:** Create `encoder.py` with the TYPE_HANDLERS dispatch pattern, implementing handlers for the 4 types that CP-SAT already supports (SEPARATED, ENCLOSING, ON_SIDE, ADJACENT) and stubs for the 4 missing types.

**Requirements:** R2 (TYPE_HANDLERS covers all types, UNSUPPORTED_TYPES empty after completion)

**Dependencies:** U1 (CpSatModel available)

**Files:**
- Create: `src/temper_placer/placer/cp_sat/encoder.py` — `TYPE_HANDLERS` dict, `encode_constraints()`, handler functions
- Create: `tests/placer/cp_sat/test_encoder.py` — per-type encoding tests
- Modify: `src/temper_placer/placer/cp_sat/__init__.py` — export encoder

**Approach:** Follow the SAT bridge dispatch pattern exactly:
```python
TYPE_HANDLERS: dict[ConstraintType, Callable] = {
    ConstraintType.SEPARATED: _encode_separated,
    ConstraintType.ENCLOSING: _encode_enclosing,
    ConstraintType.ADJACENT: _encode_adjacent,
    ConstraintType.ON_SIDE: _encode_on_side,
    ConstraintType.ANCHORED: _encode_anchored_stub,     # returns [], logs warning
    ConstraintType.KEEPOUT: _encode_keepout_stub,       # returns [], logs warning
    ConstraintType.ALIGNED: _encode_aligned_stub,       # returns [], logs warning
    ConstraintType.LOOP_AREA: _encode_loop_area_stub,   # returns [], logs warning
}
```

Each handler signature: `(constraint: BaseConstraint, components: dict[str, ComponentVars], model: CpSatModel, ctx: EncoderContext) -> list[AssumptionLiteral]`. Assumption literals enable UNSAT-core extraction per the existing U7 pattern. Four existing-type handlers encode:
- **SEPARATED:** `AddNoOverlap2D` expanded by `(min_distance_mm - component_half_size)` — or use Chebyshev clearance expressed as integer-interval `AddNoOverlap2D` with inflated intervals
- **ENCLOSING:** component interval must be contained within region interval: `x_inner >= x_outer + margin`, etc.
- **ADJACENT:** proximity constraint — `AddNoOverlap2D` with explicit adjacency (OR-tools adjacency encoding or pairwise proximity threshold)
- **ON_SIDE:** pin component to a board edge: `x == edge_x ± tolerance` for the specified side

**Test scenarios:**
- `_encode_separated(Q1, Q2, min_distance_mm=6.0)` adds constraints that enforce ≥6mm between Q1 and Q2
- `_encode_enclosing(outer=HV_ZONE, inner=[Q1, Q2], margin=1.0)` places Q1, Q2 inside the zone with 1mm margin
- `_encode_adjacent(Q1, Q2, max_distance_mm=10.0)` keeps Q1 and Q2 within 10mm of each other
- `_encode_on_side([Q1], side=LEFT, edge=flush)` places Q1 on the left board edge
- All handlers create assumption Booleans consumable by `extract_unsat_core`
- Stub handlers log warnings but do not block placement

**Verification:** 4-type encoder produces valid CP-SAT models; existing temper-board PCL constraints encode without errors; solver returns FEASIBLE.

---

### U3. Replace Loop-Area Stub with Hard Physics-Grounded Ceiling

**Goal:** Replace the `_encode_loop_area_stub` with a hard ceiling constraint (tol=0): the axis-aligned bounding rectangle of loop components satisfies `width × height ≤ max_area_mm2_units`. Remove any loop-area contribution from the objective.

**Requirements:** R1, R5 (hard ceiling, tol=0, per L_loop derivation)

**Dependencies:** U2 (encoder dispatch in place); U4 from the loop_extractor research below

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/encoder.py` — replace `_encode_loop_area_stub` with full `_encode_loop_area` implementation
- Modify: `src/temper_placer/core/loop_extractor.py` — ensure `trace_commutation_loop` signature is well-documented (or add convenience `resolve_loop_by_name` if needed)
- Create: `tests/placer/cp_sat/test_loop_area.py` — loop-area encoding tests

**Approach:**
1. Resolve loop components: `loop = trace_commutation_loop(netlist, switch_high_component, switch_low_component)` → `loop.components` = `[C_BUS1, Q1, Q2, C_BUS2]` (ordered)
2. Get component vars from the model for each component in the loop
3. Construct the AABB as CP-SAT IntVars:
   - `loop_x_min = model.NewIntVar(min_x, max_x, "loop_x_min")`
   - `loop_x_max = model.NewIntVar(min_x, max_x, "loop_x_max")`
   - Same for y
   - Constraints: `loop_x_min <= comp_x - comp_w/2` and `loop_x_max >= comp_x + comp_w/2` for each component
4. Area constraint: `(loop_x_max - loop_x_min) * (loop_y_max - loop_y_min) <= max_area_units`
   - Use `model.AddMultiplicationEquality(area, [width, height])` — OR-Tools has `AddMultiplicationEquality` for exactly 2 variables
   - Then `model.Add(area <= max_area_units)`
5. Tie to an assumption Boolean via `OnlyEnforceIf` for UNSAT-core extraction

**Key decision from origin:** Loop area is a **hard feasibility constraint**, not a lex-opt objective level. The existing soft wirelength-sum handler (from the JAX path) is replaced, not extended. No objective-term contribution for loop area.

**Patterns to follow:** `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — hard constraints only, no soft fallbacks; `docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md` — loop-area spec format and chain-of-proof pattern.

**Test scenarios:**
- Loop with components at (0,0), (10,0), (10,20), (0,20): AABB area = 200mm², ≤ 500mm² → FEASIBLE
- Loop with components forced apart: AABB area > 500mm² → solver returns INFEASIBLE (UNSAT from loop_area assumption)
- `max_area_mm2=10` (artificially tight) → INFEASIBLE, assumption Boolean for loop_area in unsat core
- No "loop wirelength" term appears in the CP-SAT objective (verified by inspecting model objective)
- Covers AE1. AABB area ≤ 500mm², verified by audit.
- Covers AE6. Over-constrained loop (10mm²) → UNSAT; core names loop_area; because field cited.

**Verification:** Loop area is a hard constraint, not an objective term; solver handles the multiplication constraint correctly; UNSAT core extraction isolates loop_area on over-constrained inputs.

---

### U4. Add ANCHORED, KEEPOUT, and ALIGNED Handlers

**Goal:** Implement the three missing constraint handlers, bringing TYPE_HANDLERS to 8/8 and making UNSUPPORTED_TYPES empty.

**Requirements:** R2, AE2 (TYPE_HANDLERS covers all 8 types, UNSUPPORTED_TYPES empty)

**Dependencies:** U3 (encoder dispatch and model structure established)

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/encoder.py` — replace three stub handlers with full implementations
- Modify: `src/temper_placer/placer/cp_sat/model.py` — add `add_keepout_interval()` helper for NoOverlap2D integration
- Create: `tests/placer/cp_sat/test_anchored.py`
- Create: `tests/placer/cp_sat/test_keepout.py`
- Create: `tests/placer/cp_sat/test_aligned.py`

**Approach:**

**_encode_anchored** (ANCHORED — single-component exact-position fix):
```
Fix component at (anchor_x, anchor_y): set x_start domain to [anchor_x, anchor_x], y_start to [anchor_y, anchor_y]
```
Simplest handler — the IntVar domain is collapsed to a singleton. For region-based anchoring (component within a named region), encode as containment: `x >= region_x_min, x + w <= region_x_max, same for y`.

**_encode_keepout** (KEEPOUT — components must not overlap a keepout rectangle):
```
Add the keepout rectangle as an interval in the global AddNoOverlap2D call.
```
Per the origin doc: use `AddNoOverlap2D` with a union of component-intervals and keepout-intervals — "the pattern is the documented OR-Tools idiom for axis-aligned keepouts." Create a "keepout component" interval at the zone location with fixed position and size, and add it to the global `AddNoOverlap2D`. This is more efficient than per-component disjunctives.

**_encode_aligned** (ALIGNED — components pairwise within tolerance along an axis):
```
For axis X: |cx_a - cx_b| <= tolerance_units for every pair in the aligned set.
For axis Y: same on y-axis.
```
O(n²) linear inequality pairs — `model.Add(abs(cx_a - cx_b) <= tolerance_units)` using two linear inequalities: `cx_a - cx_b <= tol` and `cx_b - cx_a <= tol`. n is small in the expected case (a handful of aligned components per constraint).

Each handler creates its assumption Boolean via `OnlyEnforceIf`.

**Patterns to follow:** Existing handler signatures; `docs/solutions/architecture-patterns/alternating-projections-constraint-feasibility-optimization-init-2026-07-01.md` — mapping projection operators to CP-SAT constraints.

**Test scenarios:**
- ANCHORED: component at (50, 50) with anchored position (50, 50) → solver places it exactly there
- ANCHORED: component anchored at position that conflicts with board edge → FEASIBLE if within bounds
- KEEPOUT: component placed at (10, 10); keepout at (8, 8, size=5,5) → component shifted outside keepout; distance ≥ margin
- KEEPOUT: all components placed outside the keepout rectangle; audit verifies no overlap
- ALIGNED: two components aligned on X-axis with tol=1mm → |cx1 - cx2| ≤ 1mm
- ALIGNED: three components aligned pairwise with tol=0.5mm → all pairwise differences ≤ 0.5mm
- Covers AE2. TYPE_HANDLERS returns callable for every ConstraintType; UNSUPPORTED_TYPES is empty.

**Verification:** 8/8 constraint types dispatch to handlers; no warnings for unsupported types; solver returns FEASIBLE with all types active.

---

### U5. Add Discrete 4-Way Rotation to the CP-SAT Model

**Goal:** Add rotation support: every non-polarized component gets a 4-valued `IntVar rot_ref ∈ {0, 1, 2, 3}`; per-component `x_size`/`y_size` become `IntVar`s selected via `AddElement`; all existing constraint helpers read post-rotation sizes.

**Requirements:** R3, AE3, AE4

**Dependencies:** U2 (encoder and model structure); U4 (handlers must be rotation-aware)

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/model.py` — add rotation variables, AddElement size selection, rotation-aware AddNoOverlap2D
- Modify: `src/temper_placer/placer/cp_sat/encoder.py` — all handlers read post-rotation x_size/y_size IntVars
- Create: `tests/placer/cp_sat/test_rotation.py` — rotation encoding and correctness tests

**Approach:**

1. **Rotation variable creation (model.py):**
   - Per component: `rot_ref = model.NewIntVar(0, 3, f"rot_{ref}")` unless `is_polarized`
   - Polarized components: `model.Add(rot_ref == 0)` (pinned)

2. **Post-rotation size selection via AddElement:**
   ```python
   # For each rotatable component:
   w_0, h_0 = component.bounds  # un-rotated (0° / 180°)
   w_90, h_90 = h_0, w_0        # 90° / 270° (swap width↔height)
   
   x_size = model.NewIntVar(0, max_board_dim, f"x_size_{ref}")
   y_size = model.NewIntVar(0, max_board_dim, f"y_size_{ref}")
   
   # AddElement: index array maps rotation → size
   model.AddElement(rot_ref, [w_0, w_90, w_0, w_90], x_size)
   model.AddElement(rot_ref, [h_0, h_90, h_0, h_90], y_size)
   ```

3. **Polarized detection:** Derive from footprint metadata. Initial implementation: a hardcoded set of polarized footprint names (TO-247, Electrolytic, Diode footprints with polarity markers in `footprint_library.yaml`). The Deferred-to-Planning question about metadata source should be resolved by inspecting what `footprint_library.yaml` provides — if it lacks polarization markers, use a manually-audited allowlist of polarized refs from the temper-board PCL config as the v1 path.

4. **Migration of all constraint helpers to read post-rotation sizes:**
   - `add_chebyshev_clearance` (new) — must use `x_size[ref]`/`y_size[ref]` IntVars, not static bounds
   - Region membership — `x_start + x_size <= region_x_max` (uses variable size)
   - Loop-area bounding rectangle — `loop_x_max >= comp_x + x_size[comp] / 2` (uses variable size)
   - AddNoOverlap2D — intervals must expand by post-rotation half-size

**Key decision from origin:** All non-polarized parts get 4-way rotation (maximalist default). If model size proves prohibitive during implementation, selective-by-class (e.g., "two-pad passives") is the fallback. The BMC exhaustive-enumeration is infeasible for rotation space (~10^18) — test strategy uses property-based sampling.

**Patterns to follow:** `docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md` — discrete rotation eliminates the softmax-rotation bug class.

**Test scenarios:**
- Non-polarized resistor: solver can place it at 0°, 90°, 180°, or 270°; bounds swap correctly at 90°/270°
- Polarized capacitor: rot_ref stays 0; bounds are fixed
- Covers AE3. Non-polarized part at rot=2 (180°) has bounding box matching x_size/y_size IntVar values
- Covers AE4. Misclassified polarized cap → test with polarized footprint rotated catches error (the test asserts rot_ref==0 for the polarized class)
- 33-component temper board with rotation enabled: solver returns FEASIBLE within 60s
- Clearance between two rotated components is correctly enforced using post-rotation bounds
- Property-based test: random rotation assignment × constraint set → audit passes for all rotation-invariant constraints

**Verification:** Rotation variables present in model; post-rotation sizes correct for all 4 orientations; polarized parts never rotated; solver handles ~30 rotatable parts on temper.

---

### U6. Add Three New Audit Checks and Loop-Area Ceiling Audit

**Goal:** Add ANCHORED region membership, KEEPOUT exclusion, ALIGNED axis-tolerance, and loop-area-ceiling audit checks to `audit.py`. All six audit checks must pass after every solve on the temper board.

**Requirements:** R4, AE5 (audit passes X/X + KiCad DRC zero)

**Dependencies:** U3, U4, U5 (constraints and rotation encoded; audit verifies them)

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/audit.py` — add `AuditResult` dataclass, `PlacementAuditor` class with 6 check methods
- Modify: `src/temper_placer/placer/cp_sat/encoder.py` — wire audit invocation after solve
- Create: `tests/placer/cp_sat/test_audit.py` — per-check audit tests

**Approach:**

Each audit check:
1. Takes placement output (positions dict + rotation indices) and constraint spec
2. Computes geometry from the placement (post-rotation component bounds)
3. Verifies the geometric invariant
4. Returns `AuditViolation` or passes

Check types:
- **Separated clearance:** Chebyshev distance between component bounding boxes ≥ min_distance_mm
- **Enclosing containment:** Component bounding box fully within region bounding box + margin
- **Adjacent proximity:** Chebyshev distance ≤ max_distance_mm
- **OnSide edge alignment:** Component edge within tolerance of board edge
- **ANCHORED region membership:** Component center within anchored region (new)
- **KEEPOUT exclusion:** No component bounding box intersects keepout rectangle (new)
- **ALIGNED axis-tolerance:** Pairwise axis differences ≤ tolerance_mm (new)
- **Loop-area ceiling:** AABB area ≤ max_area_mm2 (new — uses post-rotation bounds)

**Patterns to follow:** Existing `placement/audit.py` `PlacementAuditor.check_collisions()` — Shapely-based geometric verification.

**Test scenarios:**
- Separated violation: two components at 3mm with 6mm constraint → audit fails with violation details
- KEEPOUT violation: component centered inside keepout rectangle → audit fails
- ALIGNED violation: two components with x-difference 2mm, tolerance 0.5mm → audit fails
- Loop-area violation: AABB area 600mm² with 500mm² ceiling → audit fails
- All passing: valid placement → all 6 checks return pass, no violations
- Covers AE5. Audit passes X/X (where X = number of active constraint types on the board).

**Verification:** Audit catches encoder bugs (if encoder fails to enforce a constraint, audit detects the violation); audit passes on valid CP-SAT placements.

---

### U7. Integrate KiCad DRC as Truth Gate

**Goal:** After CP-SAT solve and audit pass, run `validation/drc_runner.run_drc()` on the placed+routed PCB. Acceptance requires `DrcResult.errors == 0` at 6mm design rules.

**Requirements:** R4, R5, AE5 (decisive result: KiCad DRC zero violations at 6mm)

**Dependencies:** U6 (audit passes — placement is geometrically valid before DRC)

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/encoder.py` — add post-solve DRC gate call (or create a separate `gate.py`)
- Create: `src/temper_placer/placer/cp_sat/gate.py` — `AcceptanceGate` class with inner (audit) + truth (DRC) stages

**Approach:**

Create `AcceptanceGate` with two methods:
```python
class AcceptanceGate:
    def inner_gate(self, placement: PlacementResult, constraints: ConstraintCollection) -> AuditReport:
        """Fast: runs audit checks (U6). Returns pass/fail + violation details."""
    
    def truth_gate(self, pcb_path: Path) -> DrcResult:
        """Slow: runs KiCad DRC. Returns DrcResult with errors/warnings."""
```

The post-solve flow:
1. CP-SAT solve → placement
2. `inner_gate(placement, constraints)` → audit (fast, per-solve)
3. On inner-gate pass: write placement to `.kicad_pcb` file
4. `truth_gate(pcb_path)` → KiCad DRC (slow, per-acceptance)
5. Accepted iff `len(drc_result.errors) == 0`

**Test scenarios:**
- Valid placement → inner gate passes, truth gate runs, DRC returns zero errors
- Covers AE5. Audit passes AND KiCad DRC returns zero violations on temper board at 6mm
- Covers R5 decisive result: "temper board places with 8/8 + rotation + KiCad DRC zero at 6mm"

**Verification:** `temper optimize` on temper board → audit passes → KiCad DRC zero violations.

---

### U8. End-to-End Integration on Temper Board

**Goal:** Wire the full pipeline: PCL YAML → encoder → model → solve → audit → DRC. Run on the temper induction board and verify the decisive result.

**Requirements:** R5 (decisive result)

**Dependencies:** U1-U7 (all components built)

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/__init__.py` — export the full pipeline entry point
- Create: `tests/placer/cp_sat/test_integration_temper.py` — end-to-end test on temper board

**Approach:**
1. Load `configs/pcl/temper_induction.yaml` using existing PCL parser
2. Create `CpSatModel` with 33 temper-board components
3. Encode all 8 constraint types via the encoder
4. Solve with 60s time limit
5. Run audit on the placement
6. Run KiCad DRC on the placed PCB (write via `kicad_writer`)
7. Assert: audit ≥ X/X passes, DRC errors == 0

**Test scenarios:**
- Covers the origin doc's decisive result: "temper board places with 8/8 constraint types honored AND non-polarized parts rotated AND passes real KiCad DRC at 6mm with zero violations"
- Solver returns FEASIBLE or OPTIMAL within 60s
- Objective wirelength is minimized (not verified against JAX — parity is theater)
- `temper optimize temper.kicad_pcb --config pcl/temper_induction.yaml` produces a DRC-clean placement

**Verification:** The single decisive-result sentence from the origin doc is satisfied.

---

## Key Technical Decisions

1. **Greenfield CP-SAT module — no existing code to extend.** The codebase has no OR-Tools or CP-SAT code. The `sat_bridge.py` pattern (TYPE_HANDLERS dispatch) is the architectural model but the implementation is entirely new. This avoids the JAX loss-bridge's pattern entanglement.

2. **Hard loop-area ceiling with `AddMultiplicationEquality`.** The multiplication constraint `width × height ≤ max_area` uses OR-Tools' built-in `AddMultiplicationEquality` for exactly-two-variable products. This is the canonical OR-Tools idiom and avoids quadratic approximation. (see origin: Key Decisions — loop area = hard ceiling per L_loop derivation)

3. **All non-polarized parts get 4-way rotation — maximalist default, selective-by-class as fallback.** CP-SAT handles 4-way enumeration natively; the JAX softmax-rotation bug class is eliminated. If the model with ~30 rotatable parts exceeds the 60s solve budget, selective rotation by component class (two-pad passives default-rotatable, multi-pad ICs rotatable unless flagged) is the documented fallback. (see origin: Key Decisions — all non-polarized parts get 4-way rotation)

4. **Polarized detection from `footprint_library.yaml` with manual allowlist fallback.** The metadata assumption is UNVERIFIED. If the footprint library lacks polarization markers, use a manually-audited allowlist of temper-board refs (electrolytic caps: K_5, K_6; diodes: D_1, D_2; ICs with pin-1 orientation). This is the v1 path; automatic detection is stretch. (see origin: Key Decisions — polarized detection from footprint library)

5. **Audit (geometric invariants) and KiCad DRC (physical rules) are distinct gates, both must pass.** The audit catches encoder bugs (constraint the solver was supposed to enforce); DRC catches model-vs-reality drift (Chebyshev-vs-Euclidean safety-factor gaps). An audit-pass without DRC-pass is not acceptance. (see origin: Key Decisions — audit and KiCad DRC = distinct gates)

6. **Loop-area bounding rectangle (AABB), not pin-loop closure (v1).** The AABB is the conservative over-estimate. If it over-constrains (false-positive UNSAT), pin-aware loop closure is a follow-up. (see origin: Key Decisions — AABB not pin-loop closure)

---

## Scope Boundaries

### Deferred for Later

- Pin-loop closure (replacing AABB with pin-level area computation) — if AABB over-constrains
- Selective-by-class rotation fallback — if maximalist model exceeds 60s solve budget

### Deferred to Follow-Up Work

- Continuous-angle rotation (free-angle) — requires polygon-aware footprints
- Multi-board generalization (rp2040, bitaxe, piantor) — stretch property, not gating
- `commutation.yaml` `because` field update (EMI → IGBT overvoltage) — consumed by F4 acceptance-gate workstream
- PCL JSON schema update to add KEEPOUT type definition

### Outside This Product's Identity

- Soft-routed loop-area minimization — forbidden by Objective-Discipline Contract
- Cross-objective weighted-sum tradeoffs (loop vs wirelength) — wirelength stays sole soft primary objective
- Manual polarized-part list as permanent solution — must be derived from footprint/spec source

---

## Dependencies / Prerequisites

- L_loop derivation completed (CLEAR — `docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md` should be written per the chain-of-proof pattern from `docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md`; if not yet written, U3 includes the physics values directly from the origin doc)
- `trace_commutation_loop(netlist, switch_high, switch_low) -> Loop | None` — verified working for temper board
- `drc_runner.run_drc(pcb_path) -> DrcResult` — verified working (requires `kicad-cli` in execution environment)
- `ortools>=9.10` must be installable in the project environment — U1 verifies

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Polarized metadata absent from footprint library | U5: manually-audited allowlist of temper-board polarized refs as v1; automatic detection as stretch |
| CP-SAT model with rotation too large (exceeds 60s solve budget) | U5: selective-by-class fallback (two-pad passives rotatable, others pinned) |
| Loop-area AABB over-constrains (false-positive UNSAT) | U3: document pin-loop closure as deferred follow-up; AABB is conservative over-estimate |
| AddMultiplicationEquality for loop area interacts poorly with solver heuristics | U3: test on range of area values; if solver stalls, use linear relaxation or piecewise approximation |
| KiCad DRC at 6mm catches Chebyshev-vs-Euclidean gap | U7: audit-vs-DRC disagreement is the signal the truth gate exists to produce; if DRC fails, the encoder clearance values need Euclidean correction |
| Rotation assignment space ~10^18 — BMC exhaustive infeasible | U5: property-based testing with Hypothesis (already in `tests/conftest.py`) for sampling rotation assignments |

---

## Test Strategy

- **Unit tests:** Every encoder handler (U2-U4), rotation model (U5), and audit check (U6) has targeted unit tests with known inputs and expected geometric outcomes.
- **Property-based tests:** Rotation correctness (U5) uses Hypothesis to sample random rotation assignments and verify post-rotation bounds. Unable to exhaustively enumerate ~10^18 assignments.
- **Integration test:** U8 runs end-to-end on the temper board — the decisive result.
- **A/B divergence:** Over-constrained vs normal PCL (AE6) — verifies UNSAT behavior for loop-area ceiling.
