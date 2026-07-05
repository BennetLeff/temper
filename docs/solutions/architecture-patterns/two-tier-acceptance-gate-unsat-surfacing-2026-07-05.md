---
module: temper_placer
date: "2026-07-05"
problem_type: architecture_pattern
component: placer
severity: high
applies_when:
  - "When a solver can return INFEASIBLE and you need to tell the user *which constraints conflict*"
  - "When a geometric audit (Chebyshev) can disagree with physical DRC (Euclidean) — need both gates"
  - "When UNSAT core extraction (OR-Tools SufficientAssumptionsForInfeasibility) needs to surface domain-expert-readable output"
symptoms:
  - "Audit passes but KiCad DRC fails — Chebyshev over-estimate passes, Euclidean rules fail at 45° angles"
  - "INFEASIBLE result is surfaced as a developer pprint, not a domain-expert-readable report"
  - "MUS refinement solver timeout treats UNKNOWN as FEASIBLE — produces non-minimal core reported as minimal"
root_cause: acceptance_gate_design
resolution_type: architecture_pattern
tags:
  - acceptance-gate
  - unsat-surfacing
  - mus-refinement
  - two-tier-gate
  - kicad-drc
  - rich-panel
  - oracle-hierarchy
---

# Two-Tier Acceptance Gate: Audit + KiCad DRC with UNSAT Surfacing

## Problem

A CP-SAT placement can pass the geometric audit (Chebyshev clearance at 8.5mm) but fail real KiCad DRC (Euclidean 6mm) because `8.5mm × sin(45°) ≈ 6.0mm` — the Chebyshev over-estimate masks diagonal clearance violations. If only the audit passes for acceptance, a placement can ship with real DRC violations. Additionally, when CP-SAT returns INFEASIBLE, the existing output was a developer `pprint` — the domain expert couldn't understand *which* constraints conflict or *why*.

## Solution

### 1. Two-tier gate: inner (audit+physics) and truth (KiCad DRC)

```
inner_gate (fast, per-solve)     →  truth_gate (slow, per-acceptance)
├── audit checks (8 geometric)   →  └── kicad-cli pcb drc at 6mm
└── physics oracle (thermal, clearance)
```

**Inner gate** runs every CP-SAT solve. Verifies encoder invariants: did the solver enforce what the encoder intended? Fast (~ms), cheap. Pass condition: all 8 audit checks green + physics scores within thresholds.

**Truth gate** runs only on accepted placements. Verifies physical reality: do the real KiCad design rules pass at 6mm? Slow (~seconds), invoked by `kicad-cli`. Pass condition: `DrcResult.errors == 0`.

**Disagreement is the signal**: when audit passes but DRC fails, the gap is surfaced — not hidden. Causes include: Chebyshev-vs-Euclidean safety-factor mismatch, encoder Clearance value set too low, or footprint model drift.

**Critical fix during review**: `truth_gate()` initially returned `DrcResult(error_count=0)` when the PCB file didn't exist — a false-pass where `accept()` returned True for a placement that was never DRC-checked. The fix returns `error_count=1` with a synthetic `DrcError` message. A missing PCB file is "DRC not run," not "DRC clean."

### 2. UNSAT core extraction with MUS refinement

When CP-SAT returns INFEASIBLE, the solver provides `SufficientAssumptionsForInfeasibility` — proto-indices of assumption literals that are jointly unsatisfiable. The extraction pipeline:

1. **Build proto-index map**: `_build_proto_index_map` translates literal indices to constraint names
2. **Extract sufficient core**: all assumption literals in the infeasibility response
3. **Refine to MUS**: iteratively remove each assumption and re-solve. If the sub-model is still INFEASIBLE, the removed assumption is NOT necessary. If FEASIBLE, it IS necessary. The necessary subset is the Minimal Unsatisfiable Subset.
4. **Surface the result**: human-readable Rich panel (stderr) + optional JSON (`--unsat-report`)

**Critical fix during review**: `_check_assumptions_infeasible` had a hard-coded 5-second timeout. When the solver returned `UNKNOWN` (timed out), the `status == cp.INFEASIBLE` check returned `False`, causing the algorithm to incorrectly mark the assumption as necessary — producing a non-minimal core reported with `is_minimal=True`. The fix:
- On `UNKNOWN`: retry with doubled timeout (up to 60s max)
- If still `UNKNOWN`: conservatively treat as `INFEASIBLE` (err toward smaller core)
- But set `is_confident=False`, and gate `is_minimal` on `all_checks_confident`

### 3. because-field candor: never fabricate, surface gaps

The UNSAT report's `because` text comes from the PCL spec's `because` field — never from a hypothesis about why the constraint exists. If a constraint's `because` field is missing or empty, the report surfaces that as a PCL data-quality finding: `"constraint X — 'because' field is unannotated; rationale not available from PCL spec"`.

This candor surface is the workstream's contribution to PCL data quality. The L_loop-derivation-recommended update to `commutation.yaml`'s `because` field (from "EMI" to "IGBT overvoltage destruction") is consumed here — the UNSAT report cites the overvoltage rationale if the PCL spec carries it; if not, the gap is surfaced.

### 4. Oracle-worktree hierarchy

Per the umbrella's F5 decisions, documented here:

| Oracle | Role | Status |
|--------|------|--------|
| `physics-derived-oracle` | Acceptance inner-gate oracle (thermal, dual-rail clearance, non-DRC physics scores) | LAND as A2 |
| `human-reference-corpus-oracle` | Regression-floor corpus liveness (49 boards, no-crash / geometric-no-regress) | LAND demoted — NOT acceptance |
| `viz-server` | Visualization | Out of scope |

The acceptance path imports from the physics oracle only. The corpus oracle runs in a separate CI regression gate. No parallel-branch mental model residue.

## UNSAT Report Output Format

**Rich panel (stderr)** — per the AE2 acceptance example:

```
Infeasibility detected. Minimum conflicting constraints (2 of 12):

  • loop_area 'commutation' (because: IGBT overvoltage destruction above 635mm²
    at 1A/ns di/dt and 80%-derated V_CE=960V — exceeds derated rating)
    conflicts with enclosure 'HV_ZONE' (because: HV segregation for touch safety)

  • separated 'Q1_Q2' (because field is unannotated; rationale not available
    from PCL spec — PCL data-quality gap)

  Tip: Review which constraints are physics-grounded vs. routing-preference.
```

**JSON (`--unsat-report out.json`)** — machine-readable, mirrors `UnsatReport` dataclass shape, includes `data_quality_gaps` array for unannotated constraints.

## Key Decisions

- **Two-tier gate, not merged**: audit verifies encoder invariants; DRC verifies physical rules. When they disagree, DRC wins.
- **Errors block, warnings don't**: `DrcResult.errors` prevent fabrication; `DrcResult.warnings` are manufacturability suggestions.
- **`because` from spec, never fabricated**: missing `because` is a finding, not an excuse to invent.
- **UNKNOWN in MUS is not silent**: non-minimal core reported with `is_minimal=False`, not a falsely-confident minimal result.

## Files Affected

- `placer/cp_sat/unsat.py` (new) — UNSAT core extraction, MUS refinement
- `placer/cp_sat/unsat_surface.py` (new) — Rich panel + JSON formatting
- `placer/cp_sat/gate.py` (new) — two-tier AcceptanceGate
- `cli/__init__.py` — `--unsat-report` flag integration

## See Also

- `docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md` — A/B divergence and false-pass detection
- `docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md` — loop-area chain-of-proof and because-field importance
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — why audit must catch encoder bugs
