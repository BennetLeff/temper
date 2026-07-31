---
date: 2026-07-30
topic: safety-closure-evidence
status: approved-for-evidence-pass
---

# Safety-closure evidence pass

## Purpose

Create a current, commit-pinned evidence record for the remaining safety and
board-closure questions after the rotation-convention work landed. The record
must distinguish measured facts from design decisions that still require human
approval.

## Scope

The pass covers four objective questions:

1. Does the ADC divider retain the claimed 1.4x double-fault margin using the
   committed resistor values, tolerances, ratings, and bus limit?
2. What does the current board report for REQ-SAFE-01, and which violations are
   placement-fixable, footprint-intrinsic, netlist/resync defects, or blocked
   on the isolation architecture?
3. Is `tank.c_tank3` represented consistently across the Atopile source,
   compiled netlist, PCB reference/designator, footprint, and staged position?
4. Is `power_pcb_dataset/drc_ceiling.json` current and schema-valid against the
   unchanged board, and what exactly are the two stale axes requiring review?

No PCB geometry, Atopile source, netlist, ceiling value, or safety threshold is
changed by this evidence pass unless a separate approved implementation scope
is opened afterward.

## Method

- Run from a fresh worktree based exactly on `origin/main` and record the base
  commit and dirty state.
- Prefer existing project gates and measurement tools over ad-hoc scripts.
- Recompute electrical worst cases from source values and manufacturer-rated
  limits; do not inherit the existing prose claim without checking it.
- Use the existing REQ-SAFE-01 and isolation validators, preserving their
  distinction between violations that a barrier/placement change can fix and
  violations intrinsic to a component or netlist identity.
- Validate `c_tank3` through both source and generated artifacts; treat a
  missing or staged PCB position as an explicit finding, not as a silent pass.
- For DRC, first run provenance/schema checks. If a fresh measurement is
  required, use the repository-prescribed `run_drc` tool, flags, and sample
  count, and report any ceiling rise with its measured cause. Do not ratchet a
  ceiling merely to make a gate green.

## Deliverable and acceptance criteria

Add a dated evidence document under `docs/evidence/` containing:

- commit, branch, dirty-state, and tool provenance;
- ADC equations, assumptions, worst-case result, and unresolved certification
  caveats;
- REQ-SAFE-01 counts with a fix-class table and the exact validator commands;
- `c_tank3` source/netlist/PCB reconciliation and placement status;
- DRC ceiling validation or a precise blocked/stale diagnosis;
- an explicit list of decisions still requiring the owner, including PD2 vs
  PD3 isolation architecture and the mains↔SELV barrier implementation.

The document must not claim that the appliance is safe, that the barrier is
buildable, or that the ADC chain is standards-certified. It records evidence
and open decisions only.
