---
title: Sealed Compartment for PD2/8.0mm (Owner Decision: Option A)
type: feat
date: 2026-08-02
topic: sealed-compartment
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: mech + placer + elec
---

# Sealed Compartment for PD2/8.0mm — Plan

## Goal Capsule

**Objective:** Make the PD2/8.0mm creepage/clearance regime *legitimate* by actually
building the sealed compartment the standard requires, per the owner's decision
(option A of `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`).

**Product authority:** single maintainer; the plan is executed after the K3
re-solve/board-write cycle lands, in the same release train.

**Open blockers (external, not code):** the compartment is physical hardware —
the geometry, parts, and BOM entries do not exist anywhere in the repo today.
This plan defines the requirements; execution produces the parts.

## Decision Record (2026-08-02)

The owner chose option **(a) build the sealed compartment**, keeping PD2/8.0mm
enforced everywhere. Basis:

- The design is **forced-air-vented, with no sealed-compartment provisions**:
  plain-rectangle outline (zero holes/slots/keepouts), off-board fan, air path
  across the PCB cavity by design; the "gasketed compartment" exists only as a
  prescriptive release requirement in `docs/ENVIRONMENTAL_SPEC.md` §3.1 and
  `docs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2.1.
- All four enforcement points are **aligned at 8.0/PD2 on main** (validator
  matrix `clearance.py:302-333`; DRU `generate_kicad_dru.py:77,106`; keepout
  `isolation_constants.py:45`; corridor `isolation_barrier.py:150`). Keeping 8.0
  enforced while the as-built construction is vented is the one indefensible
  state.
- The alternative (b) — retarget everything to PD3/12.6 — re-opens the full PD3
  wall (123 violations / 86 pairs measured on the same board class; free refs
  move 30-280mm).
- **K3's relay swap (G5LE-1 → RT314012) is required under either bar**: its
  3.559mm coil-to-contact intra gap fails both regimes.

## Requirements

### R1 — Sealed-compartment geometry (mech)

- A cover/gasket/partition geometry isolating the HV region (K3's cavity) from
  the forced-air path, sized so no unfiltered kitchen air reaches the HV
  conductors, with the gasket on a **sealing plane** (not the glass cooktop
  seal, which is not a compartment seal).
- The compartment must contain the MAINS/SELV boundary components the 8.0mm bar
  protects, per `docs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2.1's intent.
- Deliverable forms: mechanical drawing + STEP/PCB-exportable geometry in the
  repo (new `mech/` or the chassis docs' convention), BOM entries, and an
  **assembly drawing with inspection points** (gasket crush, fasteners, sealing
  plane continuity) per `docs/ASSEMBLY_GUIDE.md` conventions.

### R2 — MAINS_SELV_ISOLATION_BARRIER keepout

- Add the `MAINS_SELV_ISOLATION_BARRIER` keepout (currently absent from the
  board) that marks where the partition/gasket meets the PCB, so the placer and
  DRU enforce clearance to the barrier the way `isolation_constants.py` already
  assumes.

### R3 — Thermal re-verification

- The existing thermal bound is marginal at the repo's 55-70°C band; sealing the
  compartment removes the impingement cooling that the IGBT-heatsink duct
  currently provides. Re-verify (thermal model or measured) that the sealed HV
  region stays within the component derating envelope with the fan airflow
  restricted to the non-HV path. If it cannot, the plan returns to the owner
  with the measured numbers (do not silently re-open option (b)).

### R4 — Enforcement alignment (no code change expected)

- All four enforcement points stay at 8.0/PD2. After R1-R3 land, verify the
  drift gate's unanimity still holds and that no artifact silently re-introduced
  a 12.6/PD3 divergence.

### R5 — K3 relay swap (G5LE-1 → RT314012)

- Land the K3 swap in the same release as the board write (the elec unblock +
  board-write step already queued in issue #523's follow-up); the swap is
  required under either bar and does not wait on R1-R3.

## Out of scope

- Re-opening option (b) (PD3 retarget) — owner may revisit only with fresh
  measurements.
- Isolation-slot milling inside the compartment — separate effort if the
  post-swap board still shows a physical short at K3's origin (#523).
- The PD2/8.0 vs PD3/12.6 standards debate — the plan follows the decision-pack's
  condition (PD3 is the cooking-appliance default; PD2 is earned by the sealed
  compartment).

## Execution order

1. R5 (K3 swap + board write, with `drc_ceiling.json` re-measure in the same
   PR) — already queued, unblocked by the validator-gated re-solve.
2. R2 (keepout) — code-side, smallest, makes the barrier enforceable now.
3. R1 + R3 (geometry + thermal) — the physical build; R3 gates R1's
   acceptance.
4. R4 — verification sweep at release time.
