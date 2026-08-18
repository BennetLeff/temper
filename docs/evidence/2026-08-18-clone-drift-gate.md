<!-- provenance: commit=11a7e7c52d21ebca3ff8ff06e6e3b941441189fd dirty=false (worktree agent-afcc97cd16c4d5843, main tip at task start). pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b at stub time, matches task brief -- this stub is a placeholder written before any board write, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "A clone-drift gate: catching 'one file cloned from another, then diverging' (the STITCH_TRACE_WIDTH_MM / _blocked() incident)"
date: 2026-08-18
module: scripts
tags: [ci-gate, clone-drift, ast-similarity, power-islands, ground-plane, zone-pour]
problem_type: gate-design
status: in-progress
---

# Clone-drift gate

**Status: IN PROGRESS**, committed incrementally per this project's survival
rule (a worktree with no commits is destroyed on stop).

## Task

Build a gate that catches "one file cloned from another and then
diverging" — distinct from `scripts/check_fact_registry_drift.py` (catches
one scalar FACT duplicated across homes) and
`scripts/check_duplicate_predicates.py` (catches a NEW copy of an
ALREADY-consolidated predicate). The motivating incident: `_power_islands.py`
was cloned from `_ground_plane.py`, and on 2026-08-17 three separate
divergences were found between them in one day (`STITCH_TRACE_WIDTH_MM`
0.3 vs 1.0mm; a false "identical" comment; `_blocked()`/via-drop-stub
missing a foreign-copper collision check that `_ground_plane.py` had
already been fixed to include). Both files are now fixed on main
(`d33c0446e` #1143, `7979a0ee1` #1329, `4d7373eca` #1332).

This document will be appended incrementally as the gate is built,
measured, and wired in.

(To be continued in this same file.)

## Progress log

- 2026-08-18: stub committed. Registry (`scripts/clone_drift_registry.py`)
  and gate (`scripts/check_clone_drift.py`) written and passing against the
  real repo (3 registered pairs, all clean): `power_islands_ground_plane_
  blocked` (sim 0.877, floor 0.80), `power_islands_ground_plane_emit_segment`
  (sim 0.883, floor 0.80), `zone_pour_clearance_creepage_required` (sim
  0.949, floor 0.85). Mechanism: normalized-AST structural similarity
  (Name/Attribute-base/Constant/arg leaves collapsed to placeholders,
  control-flow shape and call names preserved), difflib.SequenceMatcher
  ratio, explicit hand-reviewed registry (mirrors
  `duplicate_predicate_registry.py`'s `ConsolidatedFamily` shape) rather
  than a full-repo sweep gating every PR. A one-off discovery sweep
  (`scripts/find_clone_pairs.py`, directory-scoped pairwise AST-similarity
  scan, NOT wired into CI) found this pair plus a second real family:
  `zone_pour_clearance.py::ZonePourClearanceTable.required` /
  `zone_pour_creepage.py::ZonePourCreepageTable.required` (0.949 similarity,
  the creepage module's own docstring calls itself the clearance module's
  "Twin"). Registered both; the zone_pour pair's ~5% gap is a documented,
  permanent, safety-relevant divergence (different unmatched-pair
  fallback: 0.2mm floor vs 0.0 = no requirement) — the `#1332`-shaped
  "legitimate and permanent" case the task brief asked the registry to be
  able to hold apart from the `#1329`-shaped accidental one.
- Next: non-vacuity tests (synthetic drift fails, reconciliation passes),
  CI wiring into `hygiene-gates` (required, unmasked per
  `.github/required-checks.json`), full write-up of the sweep's other
  findings and what was and was not registered.
