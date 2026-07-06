---
date: 2026-07-01
topic: z3-smt-preplacement-verification
---

# Z3 SMT Pre-Placement Satisfiability Gate

## Summary

Before running an expensive JAX placement loop, encode PCL geometric constraints (keepout rectangles, minimum spacing) as Z3 SMT formulas. Z3 proves satisfiability — an `unsat` result means the constraint set is contradictory and a counterexample shows exactly which components conflict. A `sat` result with vacuous constraints (e.g., empty PCL = trivially satisfiable) triggers a warning because the constraint set is suspiciously weak. Run as CI gate on every PCL manifest change. Also serve as post-hoc verification: after placement, check the output against Z3-encoded constraints.

---

## Problem Frame

Constraint sets can be contradictory (unsatisfiable keepout zones) or vacuous (empty PCL = silent skip). JAX optimizer runs for hours on unsatisfiable constraints with no signal. Z3 catches both in seconds with exact arithmetic.

---

## Actors

- A1. Constraint author: Writes PCL YAML manifests defining keepout zones, clearance rules
- A2. CI system: Runs SMT satisfiability check on every PCL manifest change
- A3. Pipeline operator: Runs `temper optimize` with pre-placement verification gate

---

## Key Flows

- F1. Pre-placement satisfiability check
  - **Trigger:** `temper optimize --verify-constraints` or CI gate on PCL manifest change
  - **Actors:** A1, A3
  - **Steps:** Encode PCL keepout zones and spacing rules as Z3 assertions; check satisfiability; if unsat, report minimal conflicting constraint set; if sat but vacuous (zero constraints), warn; otherwise proceed to optimization
  - **Outcome:** Optimization only runs when constraint set is provably satisfiable and non-trivial
  - **Covered by:** R1, R2, R3, R4

- F2. Post-placement constraint verification
  - **Trigger:** Pipeline completes placement optimization
  - **Actors:** A3
  - **Steps:** Encode final component positions + active constraints as Z3 assertions; check that placement satisfies all constraints; if violation found, report which component + which constraint
  - **Outcome:** Placement is Z3-certified constraint-compliant OR violation is localized to specific component/constraint pair
  - **Covered by:** R5, R6

---

## SMT Theory

Constraints are encoded in **QF_LRA** (quantifier-free linear real arithmetic), which Z3 can solve efficiently with the Simplex-based decision procedure. This covers:

- Axis-aligned rectangle keepout zones (linear inequalities over coordinates)
- Chebyshev spacing (disjunctions of linear inequalities: |x1-x2| >= d OR |y1-y2| >= d)
- Tag-based constraints (decomposed to pairwise QF_LRA formulas, with index sets for group membership)

Euclidean spacing — which is quadratic ((x1-x2)^2 + (y1-y2)^2 >= d^2) and requires Z3's NRA (nonlinear real arithmetic) theory — is **deferred to v2**. NRA can be orders of magnitude slower than QF_LRA and is not suitable for the 30-second CI gate budget.

---

## Requirements

**[Constraint encoding]**
- R1. **Board bounds and keepout zones.** The board rectangle is encoded as a QF_LRA constraint: every component center must lie within the board boundaries. Additionally, PCL keepout zones (axis-aligned rectangles) are encoded as QF_LRA constraints: component (x, y) coordinates must NOT fall within keepout regions. Board bounds are treated as a special keepout zone — the complement of the board rectangle — so a component constrained to the board but with a keepout covering the entire board will produce `unsat`.
- R2. **Edge-to-edge Chebyshev spacing.** PCL minimum spacing rules are encoded as Chebyshev distance constraints between component bounding boxes: given two components with axis-aligned bounding boxes (widths w_i, w_j and heights h_i, h_j), the edge-to-edge clearance is `max(|x_i - x_j| - (w_i + w_j)/2, |y_i - y_j| - (h_i + h_j)/2)` and must be >= min_spacing. This decomposes to the QF_LRA-friendly disjunction: `|x_i - x_j| >= (w_i + w_j)/2 + d  OR  |y_i - y_j| >= (h_i + h_j)/2 + d`. Chebyshev is the standard PCB spacing metric: components must clear in at least one dimension. Euclidean spacing (center-to-center distance >= d) requires nonlinear arithmetic and is deferred to v2.
- R3. **Tag-based group constraints with decomposition threshold.** PCL tag-based constraints (e.g., "all HV_ZONE components must be >= 8mm from LV_ZONE components") are encoded as pairwise QF_LRA constraints across tagged groups. If |G_1| x |G_2| > 100, decompose the check with a bounding-box pre-filter: components are only constrained against nearby components in the opposing group (those whose bounding boxes overlap when expanded by the clearance distance). The base constraint set can be reused across pairwise checks via Z3's incremental solver API (`Solver.push()` / `Solver.pop()`).

**[Satisfiability checking]**
- R4. Z3 satisfiability check runs as a CI gate on every PCL manifest change — `unsat` blocks the PR with a minimal conflicting constraint report. The minimal conflict report uses Z3's **unsat-core** feature (`Solver.assert_and_track()` + `Solver.unsat_core()`) to identify the subset of constraints responsible for unsatisfiability. Enabling unsat-core tracking adds a small overhead (~10-20%) to solve time; this is acceptable within the 30-second CI budget.
- R5. Vacuous constraint detection: if Z3 returns `sat` but the constraint set is empty or trivially satisfiable (total keepout area < 1% of board area), emit a structured warning
- R6. Satisfiability check must complete within 30 seconds for boards up to 50 components and 20 keepout zones

**[Post-placement verification]**
- R7. After placement optimization completes, the DAG engine can optionally run Z3 post-hoc verification (`--verify-placement`) that checks the final positions against all active constraints
- R8. Post-hoc violations are reported with: component name, violated constraint type, constraint parameters, actual position vs required position

**[Operational integration]**
- R9. Z3 verification is runnable as a standalone CLI: `temper verify-constraints temper_induction_cooker.pcl.yaml`
- R10. Z3 is a soft dependency — pipeline runs without Z3 in environments where it's not installed, but CI requires it

---

## Acceptance Examples

- AE1. **Covers R1, R4.** Given a PCL manifest with a keepout zone covering the entire board area AND a component that must be placed, when `temper verify-constraints --pcl manifest.yaml` runs, Z3 returns `unsat` with a report: "Conflict: component U1 requires placement within board bounds, but keepout HV_ZONE covers entire board."
- AE2. **Covers R5.** Given a PCL manifest with zero constraints (empty file or file not found), when the satisfiability check runs, it produces `[WARN constraint-sat] constraint set is vacuous — 0 constraints, 0 keepouts, 0 spacing rules. Expected non-empty for production board.`
- AE3. **Covers R6.** Given a board with 40 components and 15 keepout zones, when `temper verify-constraints` runs, the Z3 solver returns `sat` or `unsat` within 30 seconds on CI hardware.
- AE4. **Covers R7, R8.** Given a placement where component U3 is placed at (12.7, 3.4) but the HV_ZONE keepout starts at x=12.0, when `temper verify-placement placement.pkl --pcl manifest.yaml` runs, Z3 reports: "U3 at (12.7, 3.4) violates keepout HV_ZONE [x in (0, 12.0)] — offset 0.7mm into zone."

---

## Success Criteria

- Contradictory PCL manifests are caught at PR time (minutes) rather than optimization time (hours)
- The ISOLATION_BARRIER ghost-zone bug (vacuous constraints from silent PCL skip) is detectable by the vacuity warning
- Post-placement Z3 verification provides a definitive yes/no on constraint compliance with exact arithmetic

---

## Scope Boundaries

- Z3 covers linear constraints only (keepout rectangles, Chebyshev spacing, alignment) — nonlinear constraints (Euclidean distance, thermal, EMI wave propagation) are excluded from v1
- Not a solver for placement — Z3 only verifies satisfiability, does not produce placements
- Not exhaustive for large boards — 50 components / 20 keepouts is the practical upper bound for CI gate
- Not a replacement for JAX loss-based optimization — Z3 is a verification companion, not an optimizer

---

## Key Decisions

- Z3 is a soft dependency (optional import) so the placer works without it, but CI requires it
- Keepout rectangles and Chebyshev spacing rules are the initial constraint subset for Z3 encoding
- 30-second timeout is the CI gate budget; longer runs allowed in interactive `--verify` mode
- Spacing metric is edge-to-edge Chebyshev (PCB standard); Euclidean spacing deferred to v2

---

## Dependencies / Assumptions

- Z3 Python bindings (`z3-solver` package) are installable and work on macOS, Linux, and CI containers
- PCL constraint types (keepout zones, Chebyshev spacing, board bounds) have well-defined geometric interpretations that map cleanly to Z3's QF_LRA theory
- For the initial subset, board geometry, keepout zones, and component bounding boxes are axis-aligned rectangles (not polygons or rotated regions)
- Z3's unsat-core tracking (`assert_and_track` / `unsat_core`) provides the minimal conflicting subset needed by R4; the ~10-20% solve-time overhead is acceptable within the 30-second CI budget

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R1][User decision] What constraint types beyond keepout rectangles and Chebyshev spacing are in scope for Z3 encoding v1? Decoupling proximity? Thermal zone adjacency?
- [Affects R6][User decision] Is a 50-component / 20-keepout CI budget sufficient for the temper_induction_cooker board, or does it need to scale higher?
- [Affects R3][User decision] Is |G_1| x |G_2| > 100 the right threshold for triggering bounding-box pre-filter decomposition, or should it be tuned per board?

### Deferred to Planning

- [Affects R4][Technical] Whether to use Z3's Tactic/Goal API for incremental solving across CI runs (performance optimization)
- [Affects R2][Technical] Euclidean spacing with Z3's NRA theory (nonlinear real arithmetic) — evaluate performance on NRA-solvable problem sizes after v1 ships with Chebyshev
