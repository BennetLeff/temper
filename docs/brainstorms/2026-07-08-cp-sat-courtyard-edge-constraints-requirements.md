---
date: "2026-07-08"
topic: cp-sat-courtyard-edge-constraints
status: requirements
tier: deep-feature
supersedes_headline: "121 -> 0 (retracted; see Evidence)"
---

# Two Hard Geometry Constraints for the CP-SAT Placer: Courtyard-Inflated NoOverlap2D + Board-Edge Margin

## 1. Problem & Evidence

The netclass 6 mm SEPARATED constraint now works (bug fixed in `8c3bc2a3`: `_resolve_component_net_class` iterating `component.pins[].net` instead of the tuple-typed `net.pins[].component`). 303 cross-class SEPARATED constraints fire; CP-SAT is OPTIMAL in ~2.56 s. But the placement is still **worse than the human on placement-relevant DRC**.

DRC decomposition (33 `lib_footprint_issues` are placement-independent library noise, excluded):

| violation type | human | CP-SAT | Δ | reached by current model? |
|---|---|---|---|---|
| clearance | 12 | 8 | **−4** | yes — netclass SEPARATED, working |
| shorting_items | 5 | 12 | +7 | **no** |
| solder_mask_bridge | 5 | 15 | +10 | **no** |
| copper_edge_clearance | 0 | 6 | +6 | **no** |
| **placement-relevant total** | **22** | **41** | **+19** | |

The excess is entirely in three classes the model does not constrain. Root causes, both structural (not tunable):

1. **`NoOverlap2D` runs on raw pad/fab bboxes with zero margin.** `component.bounds` prefers the courtyard layer but falls back to pad/fab bbox when absent; the synthetic temper footprints have no courtyard layer. NoOverlap allows 0-gap touching ⇒ pads short (`shorting_items`) and solder-mask openings merge (`solder_mask_bridge`).
2. **No board-edge margin.** The objective parks components on `x = 0` (visible in the render: the HV cluster is flush against the left edge) ⇒ `copper_edge_clearance`.

**Note on the retracted headline.** The prior "121 → 0" was three stacked silent failures (kicad-cli exit-3 read as 0, net_class-syntax rejection, 0 constraints from the tuple bug); the "121" was measured under different DRC conditions. Honest baseline is **22 (human) → 41 (CP-SAT)**. This document closes that gap by construction.

## 2. Goals / Non-Goals

**Goals**
- Add two hard-constraint classes to the CP-SAT model such that **solver-SAT ⇒ zero** `shorting_items`, `solder_mask_bridge`, and `copper_edge_clearance` on the placed board.
- Each constraint has a stated invariant, a soundness theorem proved from the encoding, and a Hypothesis PBT suite asserting soundness/monotonicity/rotation-invariance.
- Placement-relevant DRC total ≤ human baseline (22); target < 22 since clearance is already 8.

**Non-Goals**
- Non-rectangular board outlines / cut-outs (edge modeled as an axis-aligned rectangle; complex outlines deferred to a keepout-polygon follow-up).
- Parsing real KiCad courtyard layers (we derive a provable margin from the netclass SSOT instead — robust to missing courtyards).
- Routing-induced shorts (these are placement-level guarantees; the router must preserve them, tracked separately).
- Per-pad exact geometry (bbox ⊕ margin is conservative and sufficient for the DRC classes above).

## 3. Locked Decisions (defaults; revisitable)

- **D1 — Margin policy:** *per-pair SEPARATED-τ + redundant NoOverlap2D.* C1 encodes as pairwise SEPARATED constraints at `min_distance_mm = τ` via the existing `_encode_separated` handler, with a redundant global `AddNoOverlap2D` for propagation. The existing cross-class SEPARATED at 6mm continues unchanged. Per-pair assumption literals (`courtyard_<i>_<j>`) surface in UNSAT cores via the mechanism the handler already provides.
- **D2 — Infeasibility:** *fully hard + surface UNSAT core.* On INFEASIBLE, reuse `SufficientAssumptionsForInfeasibility()` to name the over-constraining class (edge margin / courtyard / a SEPARATED pair) with its physical `because`. No silent relaxation — preserves the `SAT ⇒ DRC-clean` soundness property.

## 4. Notation

Integer units via `s = mm_to_units` (scale). Component `i` at integer origin `(xᵢ, yᵢ)`; realized (post-rotation) size `(wᵢ, hᵢ)` — the model's `AddElement` selects swapped sizes for 90°/270°. Copper box `Bᵢ = [xᵢ, xᵢ+wᵢ] × [yᵢ, yᵢ+hᵢ]`. Board outline = axis-aligned rectangle `[0, W] × [0, H]` in units. For axis-aligned boxes, per-axis gap `gˣ(i,j) = max(0, max(xᵢ, xⱼ) − min(xᵢ+wᵢ, xⱼ+wⱼ))` (analogously `gʸ`); Euclidean edge-to-edge distance `d₂(Bᵢ,Bⱼ) = √(gˣ² + gʸ²)`; Chebyshev/L∞ gap `d∞ = max(gˣ, gʸ)`.

---

## 5. Constraint C1 — Per-Pair SEPARATED-τ + Redundant NoOverlap2D

### 5.1 Parameter (unchanged)

Let `τ = max(default_clearance_mm, 2·mask_expansion_mm)` — the binding base target (no short needs gap ≥ `default_clearance`; no mask bridge needs gap ≥ `2·mask_expansion`, mask growing each side). Keep

    δ = ⌈ s · τ / 2 ⌉   (units)

`default_clearance_mm` from `netclass_rules.yaml` (0.2 mm); `mask_expansion_mm` from the board `(setup)` (fallback 0.1 mm).

### 5.2 Encoding (primary: per-pair SEPARATED-τ; redundant: global NoOverlap2D)

Reuse the existing `_encode_separated` handler (`encoder.py:87`). For every pair (i, j), generate a SEPARATED constraint with `min_distance_mm = τ`, and encode via the 4-Boolean Chebyshev disjunction that handler already provides:

```python
for i in range(N):
    for j in range(i+1, N):
        c = SeparatedConstraint(a=refs[i], b=refs[j], min_distance_mm=τ,
                                tier=ConstraintTier.HARD,
                                because="Courtyard clearance τ mm — base clearance + mask expansion",
                                id=f"courtyard_{refs[i]}_{refs[j]}")
        encode_separated(c)   # produces per-pair assumption literal courtyard_<i>_<j>
```

Each pair carries its own `courtyard_<i>_<j>` assumption literal — R3's per-pair UNSAT surfacing works natively.

Also register a redundant global `AddNoOverlap2D` on the copper intervals. SEPARATED-τ with τ > 0 logically implies NoOverlap2D, but the global constraint strengthens propagation and keeps solve time down — proven tractable at N=33 (all-pairs = 528; 303 cross-class pairs already solve in 2.56s).


### 5.3 Soundness (from SEPARATED-τ Chebyshev disjunction)

> **Theorem C1.** If the solver returns SAT with a SEPARATED constraint of `min_distance_mm = τ` on every pair, then every pair has Chebyshev (L∞) edge-to-edge gap ≥ `s·τ` (model units) and therefore Euclidean gap ≥ `τ` mm. Hence **zero** `shorting_items` and **zero** `solder_mask_bridge`.

---

## 6. Constraint C2 — Board-Edge Margin

### 6.1 Parameter

`m_mm` = the `copper_edge_clearance` design rule (from `(setup)`, fallback 0.5 mm). `m = ⌈s·m_mm⌉` units. Uses the **copper** box (not inflated) — `copper_edge_clearance` is copper-to-edge, so inflating would double-count against C1.

### 6.2 Encoding

Four linear bounds per component (domain restriction on existing vars):

```python
model.Add(v.x_start >= m)
model.Add(v.x_end   <= W - m)     # x_end = x_start + active x_size
model.Add(v.y_start >= m)
model.Add(v.y_end   <= H - m)
```

### 6.3 Invariant & Soundness

**I2:** `∀ i : Bᵢ ⊆ [m, W−m] × [m, H−m]`.

> **Theorem C2.** SAT ⟹ every component's copper is `≥ m` from all four board edges ⟹ **zero** `copper_edge_clearance` violations at margin `m`.

*Proof.* Induction on `n` (each component independently constrained). Base `n=0`: vacuous. Step: the four bounds for component `k+1` are exactly `B_{k+1} ⊆ [m,W−m]×[m,H−m]`, whose L∞ distance to each edge is `≥ m`; they do not affect `{1..k}`, so I2 is preserved. At SAT, I2 holds for all `i`; the distance from `Bᵢ` to the nearest edge `≥ m` ⟹ clearance `≥ m` mm. ∎ (Assumes rectangular outline — see Non-Goals.)

---

## 7. Interaction, Feasibility, UNSAT

- **Necessary feasibility bound (area pigeonhole).** SAT ⟹ `Σᵢ (wᵢ+2δ)(hᵢ+2δ) ≤ (W−2m)(H−2m)`. Contrapositive is a cheap pre-check and a proof that over-inflation is provably UNSAT (not a solver timeout).
- **Monotonicity (antitone feasible set).** `F(δ, m)` shrinks as `δ, m` grow: `δ'≥δ ∧ m'≥m ⟹ F(δ',m') ⊆ F(δ,m)`, so `SAT(δ',m') ⟹ SAT(δ,m)`.
- **UNSAT surfacing (D2).** Register C1/C2 assumption literals so `SufficientAssumptionsForInfeasibility()` can name `edge_margin_<ref>` or `courtyard_<i>_<j>` in a minimal core, with the physical `because` (e.g. "board-edge copper clearance m=0.5 mm"). No silent relaxation.

## 8. Property-Based Testing Plan (Hypothesis)

Location: `packages/temper-placer/tests/placer/cp_sat/test_geometry_constraints_pbt.py`. Strategies generate small instances (N ≤ ~12), random integer sizes, board sized to leave feasibility plausible, random δ/m, optional forced rotations. Each property re-derives geometry from the returned integer positions/rotations — no trust in solver internals.

| # | Property | Statement |
|---|---|---|
| P1 | **Soundness C1** | solver SAT ⟹ `min_{i≠j} d₂(Bᵢ,Bⱼ) ≥ 2δ/s` mm (⟹ no short, no mask bridge). |
| P2 | **Soundness C2** | solver SAT ⟹ `min_i dist(Bᵢ, ∂board) ≥ m/s` mm. |
| P3 | **Rotation-invariance** | P1/P2 hold under whatever rotations the solver picks; also hold when all rotations are pinned to a random vector. |
| P4 | **Monotonicity** | for a fixed instance, `SAT(δ',m')` with `δ'≥δ, m'≥m` ⟹ `SAT(δ,m)` (looser always solvable when tighter is). |
| P5 | **Area feasibility floor** | if `Σ(wᵢ+2δ)(hᵢ+2δ) > (W−2m)(H−2m)` then result is UNSAT (never a spurious SAT). |
| P6 | **Bounded completeness** | for N ≤ 3 with a hand-constructed placement having clearance ≥ 2δ and edge margin ≥ m, solver returns SAT (guards against over-constraint bugs making feasible boards UNSAT). |
| P7 | **Determinism** | fixed seed + workers ⟹ identical placement (regression anchor). |

Deterministic unit tests (non-PBT) accompany: two-component touching → UNSAT at δ>0; component at `x=0` → UNSAT at m>0; golden temper board → the three DRC classes read 0.

## 9. Success Criteria

1. On the regenerated CP-SAT temper board: `shorting_items = 0`, `solder_mask_bridge = 0`, `copper_edge_clearance = 0` under `kicad-cli pcb drc`.
2. Placement-relevant DRC total (excl. `lib_footprint_issues`) `≤ 22` (human), target `< 22`.
3. Solver remains feasible within the existing time budget (both constraints are cheap: C1 changes interval sizes only; C2 is 4 linear bounds/component). Regressions in solve status/time are failures.
4. P1–P7 green; UNSAT core correctly names the offending class on a deliberately over-constrained instance.

## 10. Assumptions & Open Questions

- **A1.** Board outline is an axis-aligned rectangle `[0,W]×[0,H]` (true for temper 100×150). Non-rectangular boards need C2 generalized to a keepout-polygon formulation — deferred.
- **A2.** `default_clearance_mm`, `mask_expansion_mm`, `copper_edge_clearance` are readable from the SSOT / board `(setup)`; sensible fallbacks (0.2 / 0.1 / 0.5 mm) apply if absent.
- **A3.** C1's uniform δ covers only base same-class clearance + mask; cross-class HV↔LV stays in the disjunctive SEPARATED (D1). If a future board needs pairwise-max base clearance, revisit D1 (per-class δ, weaker per-pair proof).
- **OQ1 (revisit after first run).** If routing later re-introduces shorts the placement guaranteed against, decide whether to push a min-gap into the router or keep it a placement-only guarantee.
