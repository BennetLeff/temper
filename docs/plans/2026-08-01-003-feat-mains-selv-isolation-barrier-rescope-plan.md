---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
date: 2026-08-01
plan_type: re-scope
---

# Isolation-Barrier Re-Scope After the NO-GO Experiment — Plan

## Goal Capsule

**Objective:** Re-scope the physical mains↔SELV isolation-barrier effort in light
of the empirical NO-GO (`docs/evidence/2026-08-01-isolation-barrier-feasibility-experiment.md`),
so the owner can commit to a path with a defensible cost/benefit — not to a
full board re-design by default.

**Product authority:** repo owner (adopts the recommended re-scope path).

**Open blockers:** none — the gate is already report-only (not in
`.github/required-checks.json` `required_contexts`); the enforced safety layer
is the required HV/LV clearance checks, which remain unchanged.

## Product Contract

### Problem

The barrier plan's corridor-constrained floorplan re-solve is empirically
NO-GO as scoped: no within-25 mm/component placement exists (stage-2
infeasible in all four cells), and the only feasible placements (K3-relaxed)
move components 270–360 mm — a full board re-design, not a re-solve. The
re-scope must pick a path that is either (a) a bounded follow-on that attacks
the specific failure mode, or (b) an honest stop.

### Key finding that drives the re-scope

The experiment tested one corridor shape: **straight, full-height, at the board
centreline.** The failure mode was the contradiction between a *straight*
corridor and the displacement budget. The gate itself does **not** require a
straight corridor — `scripts/check_isolation_keepout.py` requires the barrier to
span edge-to-edge and remove the board into **exactly two regions** (verified:
the partition check counts `len(pieces) != 2`; straightness is never tested).
A **non-straight, boundary-following, full-height corridor** is therefore
admissible and would let the corridor snake between HV and SELV clusters —
attacking the exact constraint that made the straight solve infeasible.

### Recommended re-scope path (Option 2): boundary-following corridor probe

Run a second, bounded feasibility experiment identical in shape to the NO-GO
probe (8 cells: X/Y × as-is/K3-relaxed × stage1/stage2, 8.0 mm, ≤25 mm budget)
but with the corridor as a **parameterized polyline path following the HV/SELV
domain boundary** instead of a straight line. Success criteria are unchanged
(stage-1 feasible in ≥1 orientation AND stage-2 within-budget in ≥1).

- The probe is cheap: it reuses the harness and the K3-relax param from the
  NO-GO experiment; only the corridor geometry changes.
- **If it passes:** the barrier plan (2026-08-01-001) resumes with the
  boundary-following corridor geometry — keepout authorship, routing, DRC
  re-measurement, all unchanged in scope.
- **If it fails:** fall back to Option 4 (stand on the report-only gate — see
  Key Decisions), which needs no further engineering.

### Scope (in)

- The boundary-following corridor feasibility probe (the 8-cell matrix with a
  polyline corridor).
- Updating the barrier plan (2026-08-01-001) with the corridor geometry once
  the probe passes.

### Scope (out)

- **Option 1 (full re-design):** rejected as the default — carrying cost is
  unjustified while the physical barrier is report-only and the enforced
  clearance checks remain the safety mechanism. Only revisit if a probe shows
  the boundary-following corridor is itself infeasible *and* the owner wants
  the physical barrier badly enough for a full re-layout.
- **Option 3 (split-board topology):** product-level change (enclosure,
  connector, thermal, two boards) beyond this plan; the interface connector
  exists but splitting is a separate program.
- Authoring the keepout, routing, DRC re-measurement, K3 swap — all unchanged
  follow-ons to the current plan.

### Success criteria

PASS = the boundary-following probe finds stage-1 feasible in ≥1 orientation
AND stage-2 within-budget in ≥1 orientation (as-is or K3-relaxed, K3-delta
quantified) — same acceptance as the NO-GO probe. FAIL = both fail → adopt
Option 4 (report-only stand) and re-file the physical barrier as a tracked
non-blocking item.

### Acceptance examples

- G1. The probe reuses the NO-GO harness (same runner, same seed, same
  caching) with only the corridor-geometry parameter changed.
- G2. The boundary-following corridor, at its best position, produces a
  stage-2 within-budget placement in at least one orientation.
- G3. The decision record reports the same matrix fields (status, max/total
  displacement, movers, unsat witness) so the two experiments are comparable.

### Key decisions (settled)

- The gate admits non-straight corridors (straightness is not a gate
  requirement; edge-to-edge + exactly-two-regions is).
- The re-scope is **a bounded second probe**, not a commitment to a larger
  redesign.
- **Option 4 (report-only stand) is the named fallback**, not a hidden
  default: it is a legitimate safety posture because the enforced HV/LV
  clearance checks + domain declarations remain required.

### Outstanding questions

- OQ-A. **Adopt Option 2 (boundary-following probe)?** Default: yes —
  it is the only option that attacks the measured failure mode at bounded
  cost.
- OQ-B. **Budget for the re-scope probe:** keep 25 mm/component (strict) or
  relax to 50 mm for the second probe? Recommendation: keep 25 mm so the two
  experiments are directly comparable; relax only if the 25 mm probe fails.
- OQ-C. **Corridor path parameterization:** how much freedom the polyline
  corridor has (e.g. ≤2 bends, or fully boundary-following). Recommendation:
  start with ≤2 bends (closest to the current geometric intent) before full
  freedom.

## Measured outcome of the re-scope probe (2026-08-01)

The Option-2 hypothesis (a non-straight corridor materially lowers the
displacement floor) was tested geometrically before any encoder investment:

- **Straight corridor** (measured, solver): no budget ≤ 100 mm is feasible in
  either orientation (budget-floor sweep; the 150 mm Y cell did not terminate
  in 300 s — a full re-layout regardless).
- **1-bend staircase corridor** (geometric, rigid-x, W=8.0): **min-max floor
  83.5 mm** (c1=86, yb=30, c2=100), 76 movers, 3537 mm total — roughly half
  the straight floor, but **still 3.3× above the 25 mm budget**.

A 2-bend corridor is untested and could close part of the gap, but the
evidence direction is unambiguous: even the best staircase needs > 80 mm max
displacement on a 152 mm board — a full re-design, not a re-solve. **No
within-25 mm placement exists under any corridor shape tested.**

### Revised recommendation

Adopt **Option 4 (report-only stand)** as the outcome: the physical barrier is
re-filed as a tracked, non-blocking item; the enforced safety layer (required
HV/LV clearance checks + domain declarations) remains unchanged. Option 1
(full re-design) is the only path to a physical barrier and is not justified
while the gate is report-only. A 2-bend corridor probe or the CP-SAT polyline
encoder is NOT worth building without evidence that a staircase can reach the
budget — which the 83.5 mm floor argues against.

## Sources / Research

- `docs/evidence/2026-08-01-isolation-barrier-feasibility-experiment.md` — the
  NO-GO decision record (8-cell matrix, K3-relax necessity, K1 X-axis finding).
- `docs/evidence/2026-08-01-isolation-barrier-feasibility.md` — geometric baseline.
- `scripts/check_isolation_keepout.py` — the gate (partition = exactly 2
  regions; straightness not required).
- `docs/plans/2026-08-01-001-feat-mains-selv-isolation-barrier-plan.md` — the
  plan this re-scopes.
- `docs/plans/2026-08-01-002-feat-isolation-barrier-feasibility-experiment-plan.md`
  — the NO-GO probe's plan.
