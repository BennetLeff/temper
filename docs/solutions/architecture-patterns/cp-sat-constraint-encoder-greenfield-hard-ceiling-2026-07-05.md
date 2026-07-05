---
module: temper_placer
date: "2026-07-05"
problem_type: architecture_pattern
component: placer
severity: high
applies_when:
  - "When building a constraint-solving module from scratch with no existing solver code"
  - "When replacing soft loss-function constraints with hard feasibility constraints"
  - "When adding discrete choice variables (rotation) to an integer programming model"
  - "When bridging a domain-specific constraint language (PCL) to a general-purpose solver (OR-Tools CP-SAT)"
symptoms:
  - "Existing codebase has constraint types defined but only 4 of 8 have solver handlers"
  - "Loop-area currently encoded as a soft weighted-sum objective term — forbidden pattern"
  - "Rotation handled via continuous Gumbel-Softmax relaxation that produces silent garbage (250M boundary loss)"
  - "BMC exhaustive enumeration infeasible for rotation space (~10^18)"
root_cause: greenfield_module
resolution_type: architecture_pattern
tags:
  - cp-sat
  - or-tools
  - constraint-encoding
  - discrete-rotation
  - hard-constraints
  - loop-area
  - pcl-bridge
  - type-handlers-dispatch
---

# CP-SAT Constraint Encoder: Greenfield Builder with Hard-Physics Ceiling

## Problem

The Temper placer needed a CP-SAT constraint encoder that handles all 8 PCL constraint types and supports discrete 4-way rotation for non-polarized parts. No CP-SAT or OR-Tools code existed anywhere in the codebase. The existing soft `_encode_loop_area` was a stub in the SAT bridge that created a hardcoded `ChannelSeparationConstraint` with no relationship to `max_area_mm2`, and the JAX loss-bridge version was a soft weighted-sum wirelength minimization — the forbidden pattern under the Objective-Discipline Contract. Rotation was handled via JAX Gumbel-Softmax, which produced silent garbage metrics (250M boundary loss) when raw logits were passed directly to loss functions.

## Solution

### 1. Model wrapper following SAT bridge dispatch pattern

The SAT bridge (`pcl/sat_bridge.py`) uses a `TYPE_HANDLERS: dict[ConstraintType, Callable]` dispatch pattern. Mirror this for CP-SAT:

```python
TYPE_HANDLERS: dict[ConstraintType, Callable] = {
    ConstraintType.SEPARATED: _encode_separated,
    ConstraintType.ENCLOSING: _encode_enclosing,
    # ... 8/8 types
}
```

Each handler returns `list[AssumptionLiteral]` — assumption Booleans that enable UNSAT-core extraction via `OnlyEnforceIf`. This is the mechanism that tells the domain expert *which constraints conflict*, instead of returning "no feasible placement found."

**Critical fix discovered during review**: SEPARATED and KEEPOUT handlers initially created `AddNoOverlap2D` constraints unconditionally without calling `.OnlyEnforceIf(assumption)`. This meant the solver could not isolate which separated pair or keepout zone caused UNSAT — the constraint was always enforced regardless of the assumption literal. Every handler MUST capture the constraint return value and wire it to its assumption via `.OnlyEnforceIf()`.

### 2. Hard loop-area ceiling via AddMultiplicationEquality

Loop area enters the encoder as a hard feasibility constraint (tol=0), not a soft objective term. Per the L_loop physics derivation: failure mode is IGBT overvoltage destruction above 635mm²; the 500mm² constraint sits at 79% with 21% parasitic margin.

Implementation:
1. Resolve loop components via `trace_commutation_loop(netlist, switch_high, switch_low)` — returns `[C_BUS+, Q1, Q2, C_BUS-]`
2. Construct AABB IntVars: `loop_x_min <= comp_x - size/2`, `loop_x_max >= comp_x + size/2`
3. Area constraint: `AddMultiplicationEquality(area, [width, height])` then `area <= max_area_units`

**Pitfall**: AABB is a conservative over-estimate vs. pin-loop closure. If components are arranged diagonally, the AABB area overestimates the true loop area, potentially producing false-positive UNSAT. Pin-loop closure is deferred.

### 3. Discrete rotation via AddElement eliminates the softmax bug class

JAX used Gumbel-Softmax over continuous rotation logits — a split-path divergence where training internally applied softmax but evaluation didn't, producing 250M boundary loss. CP-SAT's discrete 4-way rotation eliminates this entire bug class.

Implementation:
- Per non-polarized component: `rot_ref = model.NewIntVar(0, 3, f"rot_{ref}")`
- Polarized components pinned: `model.Add(rot_ref == 0)`
- Post-rotation sizes via `AddElement`:
  ```python
  AddElement(rot_ref, [w_0, w_90, w_0, w_90], x_size)  # 90°/270° swap
  AddElement(rot_ref, [h_0, h_90, h_0, h_90], y_size)
  ```
- All constraint helpers (clearance, region membership, loop-area AABB) read `x_size[ref]`/`y_size[ref]` IntVars, not static bounds

**Polarized detection**: footprint_library.yaml lacked polarization metadata. Fallback: manually-audited allowlist of temper-board polarized refs (electrolytic caps, diodes, ICs with pin-1). If a polarized part is misclassified as rotatable, the board fails on power-up — undetectable by geometric audit or DRC. A pre-flight verification gate cross-references the allowlist against the board's BOM.

### 4. Audit catches encoder bugs; KiCad DRC catches model-vs-reality drift

**Inner gate (audit, fast, per-solve)**: 8 geometric checks verify the solver *enforced* what the encoder *intended*. Catches: forgotten `OnlyEnforceIf`, incorrect clearance math, rotation size mismatches.

**Truth gate (KiCad DRC, slow, per-acceptance)**: Real 6mm design rules via `kicad-cli pcb drc`. Catches: Chebyshev-vs-Euclidean safety-factor gaps (8.5mm Chebyshev ≈ 6.0mm Euclidean at 45°), footprint-vs-model discrepancies.

**Pitfall discovered during review**: The truth gate initially returned `DrcResult(error_count=0)` when the PCB file didn't exist — a false-pass. A missing PCB file is "DRC not run," not "DRC clean." The fix returns `error_count=1` with a synthetic error.

**Pitfall**: Loop-area audit (`_check_loop_area`) was vacuous — it read `_loop_components` from constraint objects, but that attribute was only set by test code, never by the encoder. The fix passes `EncoderContext.loop_components` through the `audit()` → `_check_loop_area()` chain.

## Key Decisions

- **Greenfield, not extend**: the SAT bridge's dispatch pattern is the architectural model, but the implementation is entirely new. No existing CP-SAT code to extend.
- **Maximalist rotation with documented fallback**: all non-polarized parts get 4-way rotation. If model size proves prohibitive (~30 rotatable parts on temper), selective-by-class (two-pad passives rotatable) is the documented fallback.
- **Loop-area AABB, not pin-loop closure (v1)**: the bounding rectangle is the conservative over-estimate. Pin-aware closure is a follow-up if AABB over-constrains.
- **Two-tier gate, not single-pass**: audit and DRC play distinct roles. Audit-pass without DRC-pass is not acceptance. When they disagree, DRC wins.

## Files Affected

- `placer/cp_sat/model.py` (new) — CpModel wrapper, rotation, AddNoOverlap2D
- `placer/cp_sat/encoder.py` (new) — TYPE_HANDLERS, 8 handlers
- `placer/cp_sat/audit.py` (new) — 8 geometric checks
- `placer/cp_sat/gate.py` (new) — two-tier AcceptanceGate

## See Also

- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — hard constraints only, no soft fallbacks
- `docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md` — why discrete rotation
- `docs/solutions/architecture-patterns/pcl-constraint-system-triple-extension-2026-07-01.md` — PCL extension pattern
- `docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md` — loop-area chain-of-proof
