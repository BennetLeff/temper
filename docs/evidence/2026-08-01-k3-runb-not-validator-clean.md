<!-- provenance: commit=1f85f4ad1b15ea5d9e920d9ea6e0972268ca3186 dirty=false (measured on a clean origin/main tree; every figure in this doc was taken at 1f85f4ad1 or an immediate ancestor, board pcb/temper.kicad_pcb unchanged) -->

# K3 RT314012 landing attempt — run-B placement is not validator-clean (2026-08-01)

**Date:** 2026-08-01
**Branch:** scratch `fix/k3-relay-landing` (reset to origin/main after the
finding; no board or elec change landed).
**Context:** issue #523. The PD2/8.0mm board re-solve (#517, commit `55226f8ad`,
merged via #521) re-placed the whole board and paid the geometry walls
(edge quantization, bounds-box overlaps, tau/netclass violations) that made the
2026-07-31 scoped pin solve infeasible. REQ-SAFE-01 on origin/main is down to
**3 violations, 1 pair, all K3-intra** (G5LE-1's 3.559mm coil-to-contact gap vs
the 4.0/6.0/8.0 bars). K3 is now the single remaining REQ-SAFE-01 violation on
the board. K2 already carries the RT314012 at the re-solved position (134.26,
30.46, rot 90, commit `27ea686c5`). tank.c_tank3 is still staged off-board at
(20, 272.75).

## What was attempted

1. **elec unblock** (`k_dis2` → RT314012) + **embedded footprint swap** on the
   board at K3's re-solved position (69.72, 29.0, rot 90). Verified: that
   position does NOT fit the RT314012 — all four rotations short fixed copper
   (segments on B.Cu/F.Cu) or hit the board edge, confirmed with the exact
   pad-rect predicate from the issue-#523 spike (`/tmp/k3_search.py`).
2. **Scoped solve** (FREE {K3, C27}, everything else pinned, domain-clearance
   8.0mm bar, fixed-copper at 0.05mm): infeasible — the pinned formulation
   still hits the solver's own edge-margin quantization on refs like C1/C10..
   (the re-solve placed some components within the solver's 0.5mm
   copper-edge margin; pinning them violates the encoder's `edge_margin_*`
   constraints). This is the same wall-1 class, now inside the solver's own
   model rather than the board geometry.
3. **Production repair recipe** (the evidence-doc run-B: nothing hard-pinned,
   min-displacement to current, max 60mm, fixed-copper WITHOUT zone items):
   **feasible, audit-clean** — K3 → (63.52, 51.97) rot 90°, C27 → (44.44,
   236.56); `audit_fixed_copper` 0 violations, `audit_domain_clearance`
   0 violations.

## The finding — run B's "audit-clean" is not validator-clean

Writing the run-B placement to the board and measuring with the actual gates:

| metric | origin/main | run-B candidate |
|---|---|---|
| REQ-SAFE-01 violations / pairs | **3 / 1** (all K3-intra) | **12 / 9** |
| `courtyards_overlap` (DRC) | 11 | **30** (+19) |
| `shorting_items` (DRC) | 199.5 | 199.2 |
| `solder_mask_bridge` | 163 | 158 |

REQ-SAFE-01 on the candidate, worst first:

```
C27 <-> U24  creepage  0.32 / 8.0
C27 <-> R1   creepage  1.528 / 8.0
C27 <-> Q1   creepage  5.123 / 8.0
C27 <-> R48  creepage  5.675 / 8.0
C27 <-> R63  creepage  6.683 / 8.0
C27 <-> U10  creepage  6.87 / 8.0
C3  <-> K3   clearance 5.94 / 6.0
K3  <-> R60  clearance 5.07 / 6.0
C24 <-> K3   creepage  4.971 / 8.0
C3  <-> K3   creepage  5.94 / 8.0
K3  <-> R60  creepage  5.07 / 8.0
C27 <-> D4   creepage  4.63 / 8.0
```

**Why**: the run-B solve's domain-clearance constraints are box-on-bounds
constraints generated from the fixture's full placement classification; the
solver's audit checks those same constraints, so "0 violations" only proves the
solver's own model is satisfied. The REQ-SAFE-01 *validator* measures exact
pad-to-pad copper on a different pair set (including pairs the generator's
`component_refs` filter or the intra-footprint-straddler exemption skipped), so
a placement can be solver-clean and validator-dirty. The 8 straddling
components the generator itself warns about (C6, K1, K2, K3, PS1, T1, U3, U7 —
DC_BUS<->LV_CONTROL intra-footprint) are exactly the class the generator
declines to constrain, and K3's new inter-component pairs (C3/K3, K3/R60,
C24/K3) are generated but were satisfied in box space while failing in exact
copper.

Also: dropping the fixed-copper zone items (run-B's `_no_zones` variant) means
K3/C27 can land on whole-board pour bboxes (SW_NODE, PWR_RTN, ac_n) — the
solver has no zone obstacles, so `courtyards_overlap` jumps +19 and the new
positions sit inside other components' courtyards. The zone-inclusive run C is
infeasible because the zone *bbox* encoding blocks every placement (the
documented conservatism; the spike's exact-polygon search found 945 viable
origins).

## What this means

The fixed-copper constraint (PR #561) is sound and load-bearing — run B proves
the part *can* be placed without shorting fixed copper — but the **current
solve recipe cannot produce a validator-clean K3/tank3 placement yet**. The
two gaps are exactly the ones the evidence doc already named:

1. **Zone-polygon exact encoding** (fixed_copper.py's documented future
   tightening): replaces the zone-bbox obstacle with the outline polygon, so
   run C becomes feasible and K3/C27 stop landing on pours/inside courtyards.
2. **Solver-validator pair-set alignment**: the domain-clearance generator's
   pair set and the validator's must agree (including the 8 intra-footprint
   straddlers and the exact-copper measurement), so "solver audit clean"
   implies "REQ-SAFE-01 clean".

Neither is a test-weakening or a gate change; both are implementation work in
the placer. The elec unblock and board swap are NOT landed (reverted after the
finding) so main stays green (REQ-SAFE-01 3/1, board gates green, ceiling
fresh).

## Recommended next step

Implement gap 1 (zone-polygon encoding) first — it is self-contained, has an
exact oracle (the spike's polygon predicate), and likely also helps gap 2 by
letting the solver see real copper. Re-run the scoped solve with zones
included; verify with the actual gates (REQ-SAFE-01 must not rise above 3,
`courtyards_overlap` must not rise above 11, `shorting_items` must not rise
above ~200). Only then land the elec unblock + board write, with the
drc_ceiling.json re-measurement in the same PR per AGENTS.md.
