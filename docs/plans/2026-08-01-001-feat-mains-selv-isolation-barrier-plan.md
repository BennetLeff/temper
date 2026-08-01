---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
title: Mains-SELV Isolation Barrier Placement - Plan
type: feat
date: 2026-08-01
topic: mains-selv-isolation-barrier
focus: Place the physical mains<->SELV isolation barrier (MAINS_SELV_ISOLATION_BARRIER keepout) on the production board so scripts/check_isolation_keepout.py exits 0, making the one red required Board & Netlist Gates step green. The verified precondition is a domain-first floorplan re-solve: the current interleaved board has no valid corridor.
origin: Task brief (human-settled sequencing: the short-term report-only split of the gate is handled elsewhere; this plan owns the long-term real fix, the barrier placement itself). Prior work: docs/evidence/2026-07-28-isolation-keepout.md, docs/evidence/2026-07-28-barrier-constrained-placement.md, docs/solutions/architecture-patterns/physical-isolation-barrier-requires-domain-first-floorplan-2026-07-30.md, docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md.
---

# Mains-SELV Isolation Barrier Placement - Plan

## Goal Capsule

- **Objective:** place a gate-compliant physical mains<->SELV isolation barrier on the production board so `scripts/check_isolation_keepout.py` exits 0 against `pcb/temper.kicad_pcb`, turning the one red required step in CI's Board & Netlist Gates job green.
- **Product/design authority:** the gate (`scripts/check_isolation_keepout.py` and its test suite `scripts/tests/test_check_isolation_keepout.py`) owns the acceptance criteria; `elec/domain_manifest.yaml` owns the HV/SELV domain split; a human PCB designer owns the physical placement decision (the gate's own violation text: "A human must place a keepout region...").
- **Open blockers (not resolved by this document):** the barrier width figure (8.0 vs 10.0 vs 12.6mm — see OQ1); whether the boundary-part BOM work is in scope (OQ2); the corridor axis/position (OQ3); who validates the placement and the PD2 enclosure prerequisite (OQ4); whether the DRC ceiling is expected to rise (OQ5).

---

## Product Contract

<!-- ce-section: work-relationships -->

### How This Work Fits Together

This plan owns the long-term real fix: the physical barrier placement on the single production board. Surrounding, separately-planned pieces are not active scope:

- The short-term split of the isolation-keepout gate to report-only (to unblock PRs while this lands) — human-settled, handled elsewhere, `Can proceed independently of` this plan; this plan references it but does not depend on it.
- The boundary-part BOM work for isolators that cannot yet straddle the corridor (C6/K2/K3/T1/U3/U7, per `docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md`) — `Depends on` being resolved (or in-scoped, per OQ2) before the floorplan solve is feasible.
- The split-board topology (Alternative B, manifest contract `POWER_CONTROL_SELV_INTERFACE`) — `Still to decide` at product level; `Enables` a different, larger fix; not this plan's shape.
- Isolation-barrier crossing-count reduction (`docs/plans/2026-07-29-001-feat-isolation-barrier-crossing-reduction-plan.md`) — `Can proceed independently of` this plan.

### Summary

Place the `MAINS_SELV_ISOLATION_BARRIER` keepout — four copper layers, at least 8.0mm wide throughout, bisecting the board edge-to-edge, with zero copper intrusion and the HV domain wholly on one side and SELV on the other — by first re-solving placement into domain islands, because the current interleaved board has no corridor a compliant barrier can occupy. Then route, and re-measure the DRC ceiling in the same PR.

### Problem Frame

The gate is red for a physical reason, not a missing annotation. The current board interleaves the HV and SELV domains checkerboard-style: every full-height 10mm column across the board contains components of both domains, the nearest cross-domain, cross-component pad pair is 1.372mm, and 24 pad pairs are within the 8.0mm figure (verified fresh on 2026-08-01; `docs/evidence/2026-07-28-isolation-keepout.md` established the same finding on 2026-07-28). A keepout drawn across this placement either cuts through real pads and footprints or leaves one domain on both sides — the gate's far-side-crossing and intrusion checks exist precisely to reject that.

The repo already tried the plausible short paths and proved them infeasible. The CP-SAT hard-barrier re-solve (`docs/evidence/2026-07-28-barrier-constrained-placement.md`) returned INFEASIBLE in both orientations because 7 of the 8 manifest-declared isolators cannot physically straddle an 8mm corridor with their HV and SELV pads on the correct sides, regardless of placement or rotation. The scoped K3 relay swap (`docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md`) and the minimal-disruption clearance solve (`docs/evidence/2026-07-31-minimal-disruption-clearance-solve-attempt.md`) hit the same wall. The project's own architecture pattern (`docs/solutions/architecture-patterns/physical-isolation-barrier-requires-domain-first-floorplan-2026-07-30.md`) names the failure mode: the keepout is the final machine-checkable expression of a domain-first floorplan topology, not the topology itself; drawing the zone first is the documented anti-pattern ("Do NOT fake a zone", `docs/plans/2026-07-31-002-fix-pr513-red-checks-and-board-debt-plan.md`).

The gate's error text reads as a simple placement instruction ("A human must place a keepout region..."), but the evidence shows the placement itself must change first. This plan scopes that change.

### Key Decisions

- **KD1. This plan is the barrier placement itself** (session-settled: user-directed — the long-term real fix, chosen over folding in the short-term unblock). The gate's short-term report-only split is human-settled elsewhere and is referenced only, never a dependency. Governs R9, R11.
- **KD2. Domain-first floorplan, then keepout, then routing** — the repo's documented sequence; a zone drawn over the current interleaved board is rejected as the anti-pattern. Governs R8, R9, R10.
- **KD3. Single-board scope** — the split-board topology is an approved manifest-level contract but a different product shape; it is not this plan's scope. Governs R8.
- **KD4. Never weaken `MIN_BARRIER_WIDTH_MM`** — the gate floor stays 8.0mm; the placement corridor targets the currently-enforced creepage figure, which may be larger (see OQ1). Governs R4.

### Requirements

**Barrier properties (gate-verifiable)**

- R1. Exactly one keepout zone named `MAINS_SELV_ISOLATION_BARRIER` exists on `pcb/temper.kicad_pcb`; no other zone shares the name.
- R2. The zone's keepout settings forbid everything: `tracks`, `vias`, `pads`, `copperpour`, and `footprints` are all `not_allowed`.
- R3. The zone's declared layers cover all four copper layers (F.Cu, In1.Cu, In2.Cu, B.Cu); a `*.Cu` wildcard declaration satisfies this.
- R4. The zone is at least `MIN_BARRIER_WIDTH_MM` (8.0mm) wide at its narrowest point — Shapely erosion by half the width leaves a non-empty region — and no wider figure selected per OQ1 is undercut anywhere.
- R5. The zone bisects the board: the board outline (Edge.Cuts) minus the zone yields exactly two disjoint regions, so copper cannot route around either end.
- R6. No copper intrudes on any shared layer: no segment, arc, via (ordinal-expanded through every internal layer), pad (extent by bounding radius, never under-approximated), or non-keepout zone overlaps the zone.
- R7. The domain split holds: every HV-classified pad lands in exactly one region, every SELV-classified pad in the other, and the two domains sit on opposite sides.

**Placement precondition**

- R8. The board placement is domain-separated: all HV-only components sit on one side of the corridor and all SELV-only components on the other, so a gate-compliant barrier can exist without intrusion or far-side crossings.
- R9. Each of the 8 manifest-declared isolators (C6, K1, K2, K3, PS1, T1, U3, U7) straddles the corridor with its HV pads on the HV side and SELV pads on the SELV side; an isolator that cannot is replaced or re-footprinted (per `docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md`) before the floorplan solve.

**Process and verification**

- R10. Routing happens only after the keepout exists and never crosses the corridor.
- R11. The same PR that changes `pcb/temper.kicad_pcb` re-measures `power_pcb_dataset/drc_ceiling.json`: 120 samples via `temper_placer.validation._drc_api.run_drc` (kicad-cli with `--all-track-errors`), per-type observed ranges, provenance block updated, a `_march` entry attributing every per-type delta to a named component/commit, and a `Ceiling-Approval:` trailer on any per-type or aggregate rise.
- R12. `scripts/check_isolation_keepout.py` exits 0 on the real board, its full unit-test suite passes, `scripts/check_measurement_provenance.py` reports the record fresh, the import-boundary gate passes, and no safety requirement or gate is weakened.

### Acceptance Examples

- AE1. **Covers R1-R7, R12.** Given the barrier zone on the routed board, when `uv run python scripts/check_isolation_keepout.py` runs, then it exits 0 with `barrier_found=True`, zero violations, and HV/SELV pad counts matching the manifest classification.
- AE2. **Covers R6.** Given a through-via whose `layers` field names only F.Cu/B.Cu positioned inside the corridor, when the gate runs, then an `intrusion` violation names it, because the drill physically breaches the internal layers too.
- AE3. **Covers R4.** Given a barrier that narrows below the selected width at any point, when the gate runs, then a `width` violation reports it.
- AE4. **Covers R8, R9.** Given the re-solved placement (before the zone is drawn), when the gate's own geometry is applied, then a full-height corridor of the target width exists with zero far-side crossings and zero isolator straddle failures.
- AE5. **Covers R11.** Given the board changed in the PR, when `scripts/check_measurement_provenance.py` runs, then the `drc_ceiling.json` record is fresh (not STALE), and every per-type rise carries an attributed `_march` entry and a `Ceiling-Approval:` trailer.

### Scope Boundaries

**Deferred for later**

- Split-board topology (Alternative B) — a different product shape, already contracted at manifest level.
- Short-term report-only split of the gate — human-settled elsewhere, referenced only.
- Crossing-count reduction — owned by `docs/plans/2026-07-29-001-feat-isolation-barrier-crossing-reduction-plan.md`.
- PD2 enclosure mechanical verification (gasketed compartment) — required before the 8.0mm figure is relied on (OQ1, OQ4).

**Outside this plan's identity**

- Weakening `MIN_BARRIER_WIDTH_MM` or the gate itself to get a green result.
- Globally exempting mixed-domain footprints from intrusion/far-side checks.
- Rewriting the gate's violation text.

### Dependencies / Assumptions

- D1. `kiutils` and `shapely` are available in the workspace venv — the gate and its tests already depend on them.
- D2. The boundary-part BOM work per OQ2 — the repo's evidence proves the floorplan solve is infeasible until isolators can straddle the corridor; K2's RT314012 swap has landed, K3 remains blocked on placement.
- A1. The interleaving finding remains true for the current board — re-verified fresh on 2026-08-01 (all 14 full-height columns contain both domains; nearest cross-domain pair 1.372mm).
- A2. The DRC-ceiling record is fresh at plan time — verified 2026-08-01: recorded board sha256 matches the board at HEAD.
- A3. Corridor orientation and position are fixed constants in the existing placer model, not solver variables; choosing them is a human decision (OQ3).

### Outstanding Questions

**Resolve Before Planning**

- OQ1. **Barrier width figure.** The gate floor is 8.0mm (PD2), but `clearance.py` currently enforces 12.6mm REQ-SAFE-01 creepage (PD3) until the PD2 enclosure prerequisite is verified, and a reconciled reinforced figure of 10.0mm also appears in the record. Which does the placement corridor target? **Recommendation:** solve the corridor at the figure `clearance.py` currently enforces (12.6mm until the PD2 enclosure is verified), keep the gate at ≥8.0mm as an immutable floor, and align the gate's constant with the enforced figure in the same PR if they diverge.
- OQ2. **Boundary-part BOM scope.** Is the isolator BOM/footprint work (C6 Y-cap sourcing, K3 RT314012 swap, T1/U3/U7 validation, K1) in this plan's scope or a separately-delivered prerequisite? **Recommendation:** in-scope as the plan's first phase, driven by `docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md`, because the placer is proven infeasible without it.
- OQ3. **Corridor axis, position, and HV side.** Vertical or horizontal strip; where along the axis; which side carries HV. **Recommendation:** require a feasible solve in both orientations (per the handoff doc's Phase 3), then a human picks the axis and side based on the mains connector, heatsink, and enclosure constraints.
- OQ4. **Validation ownership.** Who validates the re-solved physical placement, and who verifies the PD2 gasketed-compartment prerequisite? **Recommendation:** a human PCB designer reviews the floorplan against mechanical constraints; the PD2 enclosure verification gates relying on the 8.0mm figure.
- OQ5. **DRC-ceiling direction.** Is a ceiling rise expected from re-placement and re-routing, and can every rise be attributed? **Recommendation:** plan for per-type movement, attribute every delta in `_march`, and stop-and-report rather than ratchet any rise that cannot be attributed.

**Deferred to Planning**

- OQ6. CP-SAT solve configuration (fixed-position pins, corridor working width, orientation enumeration) and the minimum-displacement vs full-resolve choice.
- OQ7. How the keepout polygon is authored (kiutils round-trip, text patch, or KiCad GUI) and how routing is regenerated with the existing route tooling.
- OQ8. Whether staged/unrouted parts (e.g. the tank capacitor staged outside the outline) are placed in this work or left staged.

### Sources / Research

- Grounding dossier: `/tmp/compound-engineering-501/ce-brainstorm/isolation-barrier/grounding.md` (verbatim quotes with file:line for every claim above).
- `scripts/check_isolation_keepout.py` and `scripts/tests/test_check_isolation_keepout.py` — the acceptance criteria.
- `elec/domain_manifest.yaml` — HV/SELV nets, isolators, board interface.
- `docs/evidence/2026-07-28-isolation-keepout.md`, `docs/evidence/2026-07-28-barrier-constrained-placement.md`, `docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md`, `docs/evidence/2026-07-31-minimal-disruption-clearance-solve-attempt.md` — feasibility evidence.
- `docs/solutions/architecture-patterns/physical-isolation-barrier-requires-domain-first-floorplan-2026-07-30.md` — the recommended implementation sequence.
- `docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md` — the boundary-part footprint-fix requirements.
- `power_pcb_dataset/drc_ceiling.json` and `scripts/check_measurement_provenance.py` — the same-PR re-measurement contract.

## Feasibility Evidence (2026-08-01)

Full reproducible analysis in `docs/evidence/2026-08-01-isolation-barrier-feasibility.md`
(script: `docs/evidence/2026-08-01-isolation-barrier-feasibility.py`). Board 152×234 mm;
HV-only = 45, SELV-only = 106, isolators = 8, unclassified = 10 components.

**As-is: no corridor exists.** All 15 full-height columns mix domains; nearest
cross-domain pad pair 0.178 mm; 42 pad pairs within 8.0 mm. Straight-corridor
sweep finds NO clean corridor at W = 8.0/10.0/12.6 mm in either orientation
(raw region gaps −150.6 mm vertical, −233.5 mm horizontal).

**Drift required for a clean corridor (best position):**
- X (vertical, HV left): 78 movers / 3096.0 mm total / max single 134.85 mm @ 8.0 mm;
  HV-dominant moves.
- Y (horizontal, HV bottom): 52 movers / 3727.1 mm total / max single 127.05 mm @ 8.0 mm;
  mixed HV+SELV moves.

**Isolator feasibility (placer's `evaluate_isolator_feasibility`):** **K3 is
infeasible at even the 8.0 mm floor** (pad overlap −0.5 mm); C6/K1/T1/U3/U7
achieve exactly 8.0 mm; only K2/PS1 clear 12.6 mm.

**Re-homing isolators does not create a corridor** (gaps unchanged) — the
floorplan re-solve is genuinely required.

### Updated OQ answers from the data
- **OQ2 (isolator BOM):** REQUIRED, first phase, and **K3 is the named blocker**
  (RT314012 swap per the plan's brainstorm) — no width target above 8.0 is reachable
  until K3's pads clear.
- **OQ3 (corridor axis):** both orientations are feasible only after the re-solve.
  **Data recommends Y** (horizontal): 52 movers vs 78, lower max drift (127 vs 135 mm);
  X keeps the power stage clustered. Human picks per mains-connector/enclosure.
- **OQ1 (width):** 12.6 mm costs only ~+183 mm total drift over 8.0 mm (X) but is
  gated by the isolator work. **Recommend: gate at 8.0 mm now, widen after the
  isolator BOM phase.**
- **OQ4 input:** `C27` is staged outside the outline; nearest in-board pads sit
  0.95–1.16 mm from the edge — the corridor will squeeze edge clearance and needs
  human re-validation after the solve.
