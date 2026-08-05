<!-- provenance: commit=5c480a3bcbdddfa42f47b3ad16bb3921fcaf589f dirty=false (re-pointed 2026-08-05: the measurement tree e19fc516934bfc95c3b311602380db50d7e0393d was a pre-merge branch commit, orphaned by force-push; the probe and its artifacts landed on main at 5c480a3bcbdddfa42f47b3ad16bb3921fcaf589f (#683), which is the cited commit; dirty=false because the artifacts are committed there) -->

# Run-C compound probe — the 14 non-zone conflicts under the sound zone encoding (issue #651 follow-up)

**Date:** 2026-08-04. **Base:** origin/main at `c60825861` (the general-convex
zone encoding, #674). **Measurement tree:** `5c480a3b` (see header; the
envelope artifacts were regenerated at the branch commit `e19fc5169` --
orphaned by force-push -- and landed on main at `5c480a3b`, which the header
cites; `dirty=false` because the artifacts are committed there).

## Question

The #674 encoding fix removed the run-C encoding-level blocker (C27 pad 2 vs
DC_BUS_RTN encoded-clear 0 → 14,966 of 14,973 exact) but left run-C
**still infeasible** (3.1 s, unsat core 15,285). The residual was the probe's
honest caveat: moving the free refs to their exact zone-clear positions
produces **14 new exact fixed-copper violations** at the naive candidate
(K3 pad 2/4 vs the GATE_HS zone, K3 pads vs the ESP32 module's
io41/io42/gpio35/gpio36 pads, K3 pad 4 vs two segments, K3 pad 1 vs three
pads). This probe answers the compound question deterministically:

> Is the compound conflict solvable by placement (then run-C feasibility is a
> search problem — try repair rounds/seeds/orderings through the production
> caller with the zone items included), or is some pair of demands mutually
> exclusive (component footprint vs zone demand vs another component's box —
> pure geometry, needing a slot/zone-geometry/floorplan decision)?

## 1. Run-C reproduction on origin/main (the sound encoding)

`gap1_runc_envelope_probe.py --variant C_60_s0` — the identical formulation to
the #674 re-run (nothing pinned, rotations fixed, 60 mm Manhattan cap,
12,101 SeparatedConstraints, fixed-copper FREE={K3,C27} at margin 0.05 mm),
regenerated on this tree:

| variant | status | solve time | core |
|---|---|---|---|
| `C_60_s0` (zones) | **infeasible** | 3.6 s | 15,285 |

The infeasibility reproduces byte-identically in core size (15,285) on
origin/main's board under the sound encoding. The encoding is not the
residual blocker; the compound is.

## 2. Deterministic conflict enumeration at the naive zone-clear candidate

Best-known placement = the current board (K3 at (43.12, 17.92), C27 at
(28.62, 222.0) — the written board IS the best-known placement). The exact
fixed-copper audit there reports **20 zone-item violations** (SW_NODE ×16,
DC_BUS_RTN ×2, +15V_LS ×2 — the run-C zone demands).

The naive candidate (the envelope probe's joint zone-reachability
first-clearing positions: C27 → (29.62, 222.0), K3 → (16.12, 7.42)) produces
**14 exact non-zone conflicts** — reproduced unchanged on this tree:

| # | K3 pad | item kind | item net | clearance at best | at candidate | required |
|---|---|---|---|---|---|---|
| 1 | 2 | zone | GATE_HS | 20.574 mm | 0.0348 mm | 0.05 |
| 2 | 2 | zone | GATE_HS | 20.574 mm | 0.0348 mm | 0.05 |
| 3 | 2 | pad | io41 (ESP32 module) | 27.833 mm | 0.000 mm | 0.05 |
| 4 | 2 | pad | io42 (ESP32 module) | 26.639 mm | 0.000 mm | 0.05 |
| 5 | 5 | pad | gpio35 (ESP32 module) | 27.946 mm | 0.000 mm | 0.05 |
| 6 | 5 | pad | gpio36 (ESP32 module) | 26.751 mm | 0.000 mm | 0.05 |
| 7 | 4 | segment | hb.gate_hs.driver-p2 | 24.972 mm | 0.000 mm | 0.05 |
| 8 | 4 | segment | safety.coil_thermal.comp-inp | 22.871 mm | 0.000 mm | 0.05 |
| 9 | 4 | segment | safety.coil_thermal.comp-inp | 22.871 mm | 0.000 mm | 0.05 |
| 10 | 4 | zone | GATE_HS | 19.552 mm | 0.000 mm | 0.05 |
| 11 | 4 | zone | GATE_HS | 19.552 mm | 0.000 mm | 0.05 |
| 12 | 1 | pad | hb.power_loop.q_high-g | 26.280 mm | 0.000 mm | 0.05 |
| 13 | 1 | pad | SW_NODE | 27.864 mm | 0.000 mm | 0.05 |
| 14 | 1 | pad | gnd | 105.953 mm | 0.000 mm | 0.05 |

(14 = 4 zone + 7 pad + 3 segment; all on K3. The GATE_HS zone items are
*not* among the run-C zone demands in violation at the best placement — they
only bind at the candidate, which is exactly why the naive candidate is not
compound-clean.)

## 3. Per-conflict joint-clear analysis (exact-oracle, all 96 zones)

The probe's joint-clear search scans the owning free ref's (K3's) 60 mm
Manhattan envelope (0.5 mm step, edge-margin-gated) for a center that clears
**every zone item on the board** (all 96, with the audit's same-net skip — a
strictly stronger check than the envelope probe's 18 zones-in-violation-at-
best) AND the specific conflict item.

Key structural finding first: **the all-96-zones joint-clear set for K3
within the 60 mm cap is only 96 cells of 58,081** (first-clearing at disp
52 mm — the naive candidate at 37.5 mm violates GATE_HS, so it was never
zone-clear under the FULL zone set). The run-C zone side is satisfiable
per-ref (C27: 920 cells, first at disp 1.0 mm), but K3's zone-clear region is
a narrow corridor, not the 1,030 cells the 18-zone subset suggested.

Within that 96-cell zone-clear corridor, **every one of the 14 conflicts is
individually jointly-clearable with all the zones**:

| conflict | zone-clear cells also clearing it | jointly clearable |
|---|---:|---|
| pad 2 vs GATE_HS | 96 | ✓ |
| pad 4 vs GATE_HS | 96 | ✓ |
| pad 2 vs io41 | 96 | ✓ |
| pad 2 vs io42 | 91 | ✓ |
| pad 5 vs gpio35 | 96 | ✓ |
| pad 5 vs gpio36 | 94 | ✓ |
| pad 4 vs driver-p2 seg | 93 | ✓ |
| pad 4 vs coil_thermal seg | 92 | ✓ |
| pad 1 vs q_high-g | 94 | ✓ |
| pad 1 vs SW_NODE / gnd | 96 | ✓ |

So **no single conflict is individually impossible** — each has 91–96 of the
96 zone-clear cells jointly available.

## 4. The compound question: all 14 + all zones at once

**Within the 60 mm cap: 0 compound-clear cells.** The 96-cell zone-clear
corridor is entirely covered by the union of the 14 items' exclusion regions
— every corridor cell violates at least one of the 14 (typically 2+; the
drop-one analysis shows no single item, removed, unblocks any cell, so the
block is combinatorial, not one dominant demand).

**Board-wide (no cap, 1.0 mm step over the full board): 30 compound-clear
cells exist**, min-displacement **119.23 mm** at (135.97, 44.3). Verified
with the full exact audit: **0 violations** for K3 at that position. C27's
own zone side clears independently (920 cells at disp 1.0 mm, verified).

**Verdict: the compound is placement-solvable — it is cap-limited, not
mutually exclusive.** A placement exists that clears all 96 zones AND all 14
non-zone items simultaneously (full exact audit clean); it simply requires
K3 to move ~119 mm, far beyond the 60 mm run-C cap. No pair of demands is
geometrically exclusive (no footprint-vs-zone-vs-box deadlock).

## 5. The decisive test: the production caller with the zone items included

`run_clearance_repair_solve` (validator-gated, fixed-copper hoisted #653)
expresses the run-C formulation directly: `fixed_copper={'parse_result': pcb,
'free_refs': {K3, C27}, 'margin_mm': 0.05}` — the full parse_result carries
all 96 zones. Three attempts at the run-C cap (seeds 0/1/2, 180 s) plus the
enlarged-envelope decisive test (cap 120 / 240, seed 0):

| attempt | cap | status | wall | rounds | result |
|---|---|---|---|---|---|
| seed 0 | 60 | **infeasible** | 3.7 s | 0 | proven UNSAT, core 15,285 |
| seed 1 | 60 | **infeasible** | 3.6 s | 0 | proven UNSAT, core 15,285 |
| seed 2 | 60 | **infeasible** | 3.6 s | 0 | proven UNSAT, core 15,285 |
| seed 0 | 120 | **feasible (clean)** | 183.0 s | 1 | validator 0/0/0, fc-audit 0 |
| seed 0 | 240 | **feasible (clean)** | 182.2 s | 1 | validator 0/0/0, fc-audit 0 |

The cap-120 solution: K3 → (135.12, 43.58) at **117.66 mm** displacement —
inside the exact-oracle's board-wide compound-clear region (min-disp
119.23 mm at (135.97, 44.3), same corridor) — C27 → (32.44, 218.86) at
6.96 mm. Full exact fixed-copper audit at the solved placement: **0
violations**. The production caller with the zone items included terminates
`clean` the moment the envelope reaches the compound-clear region.

## Verdict: PLACEMENT-SOLVABLE — run-C is a cap-limited search problem, not a geometry deadlock

1. **Run-C is infeasible at cap 60 under the sound encoding — confirmed**
   (3.6 s, core 15,285, byte-identical to #674), by the direct formulation
   and by the production caller (seeds 0/1/2, all proven UNSAT, identical
   core). The encoding is not the residual blocker.
2. **The 14 non-zone conflicts are individually jointly-clearable with all
   zones** (91–96 of 96 zone-clear cells each) — none is a single-demand
   blocker.
3. **The compound (all 14 + all 96 zones at once) is placement-solvable**:
   a board-wide exact-oracle scan finds 30 compound-clear placements
   (min-disp 119.23 mm, exact-audit-clean), and the production caller
   terminates `clean` at cap 120/240 with K3 in that exact region.
   **No demand pair is mutually exclusive** — the isolation-slot /
   zone-geometry / floorplan decision is NOT demonstrated as necessary by
   this probe.
4. **The binding constraint is the 60 mm displacement cap.** Within it the
   96-cell zone-clear corridor is fully covered by the 14 items' exclusions
   (combinatorially — drop-one unblocks nothing); beyond it a clean compound
   placement exists. This refines the #650/#674 residual: run-C feasibility
   is a search/envelope problem, and the answer to "is the compound solvable
   by placement" is **yes** — a ≥120 mm envelope (or a K3-friendly
   zone-geometry / slot change that widens the corridor) is what run-C needs.
5. **Implication for #651/#618.** The isolation slot is not forced by
   geometry; the lever is the envelope (or equivalently, zone geometry that
   moves the ESP32/GATE_HS/segment demands out of the zone-clear corridor).
   A follow-up (retry run-C at cap ≥120 through the production caller, then
   the DRC ceiling protocol for any written board) is the concrete next step
   — the 183 s clean solve here is the existence proof, not yet a board.

## Artifacts

- `gap1_runc_compound_probe.py` — the compound probe: run-C reproduction,
  the 14-conflict enumeration, per-conflict joint-clear (all 96 zones),
  board-wide compound scan, drop-one analysis, and the production-caller
  attempts (cap 60 seeds 0/1/2 + cap 120/240). No src/ or pcb/ changes.
- `gap1_runc_compound_summary.json` — the full measurement.
- `gap1_runc_compound_conflicts.csv` — the 14-conflict table.
- `gap1_runc_compound_caller.json` — the 5 caller attempts.
- `gap1_runc_envelope_matrix.json` / `_zones.json` / `_joint.csv` /
  `_pairs.csv` — regenerated on this tree (run-C reproduction).

## Provenance

Measured on the tree at `e19fc5169` (see header; `dirty=true` records the
uncommitted probe/artifact files at stamp time). The measurement scripts
re-derive the run-C formulation from the committed board
(`pcb/temper.kicad_pcb` at origin/main) and the committed test fixture;
`pcb/`, `src/`, and `elec/` were untouched.
