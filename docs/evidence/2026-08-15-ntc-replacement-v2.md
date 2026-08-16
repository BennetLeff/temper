---
module: pcb
tags: [placement, ampacity, ntc, drc, power_in.ntc-no, courtyard, creepage]
problem_type: placement-fix
---

# 2026-08-15: NTC replacement v2 — K1/RT1/U1/U2 relocation to shrink the power_in.ntc-no hull

## Problem

`power_in.ntc-no` (net 88, HighVoltage, 5.0mm fixed width) must carry
15A of mains input current between its four pads. IPC-2221B
(k=0.048 external, 2oz, 40C rise) requires 4.16mm minimum; the declared
5.0mm clears with 1.8x margin at trace level (17.2A @ 20C / 23.3A @ 40C).
The net-level ampacity failed not at the width but at the geometry: the
four components were scattered across 134.6mm of board:

- U2 at x=28, RT1 at x=40, K1 at x=95, U1 at x=168 (origin/main before this change)

The full-board route (docs/evidence/2026-08-15-full-board-route-verification.md)
drew 72 segments at 5.0mm but the zone fill for the net fragmented into
47+ islands under DRC-aware fill — a single 5mm pour hull could not span
140mm without being chopped by clearance/creepage constraints. Two of the
four pads (RT1.2, U1.2) are zone-dependent (THT pads relying on zone
fill), so the fragmentation blocked net-level ampacity entirely.

## Fix

Owner authorized relocation of K1/RT1/U1/U2. Moved all four into a
compact cluster in the bottom power pocket (the only free region on the
board large enough for K1's 30.5x23.5mm courtyard; mid-board is blocked
by C26 tank cap and PS1 aux supply):

| component | before | after | note |
|---|---|---|---|
| K1 (bypass relay, G4A-E) | (95.23, 221.395) rot 180 | (90, 222) rot 0 | ntc-no pad 13 is a non-copper spade tab (F.Fab only, external wiring) |
| RT1 (NTC disc) | (40.4, 210.1) rot 180 | (82, 205.5) rot 0 | |
| U1 (TO-220 D1) | (168.0, 223.03) rot 180 | (60, 218) rot 0 | |
| U2 (TO-220 D2) | (28.29, 175.44) rot 180 | (66, 226) rot 180 | |

power_in.ntc-no pad positions after move:

- K1.13: (86.83, 231.5) — non-copper tab
- RT1.2: (89.5, 205.5)
- U1.2: (65.08, 218.0)
- U2.1: (66.0, 226.0)

**Pad span: 24.4mm x 26.0mm (was 134.6mm).** The three copper pads
(RT1.2, U1.2, U2.1) span 24.4mm; K1's external-wired tab sits 26mm from
the cluster. A single 5mm pour hull can now connect all four pads.

## Verification

### Courtyard clearance

Exact courtyard geometry (fp_rect/fp_circle/fp_line on F.CrtYd, KiCad
clockwise rotation convention) checked for all four moved components
against all 165 other footprints, plus pairwise. All clear with 0.3mm
margin:

```
K1:  bbox (74.75, 210.25)-(105.25, 233.75)  clear
RT1: bbox (77.75, 203.80)-(93.75, 209.50)   clear
U1:  bbox (57.29, 214.60)-(67.79, 219.50)   clear
U2:  bbox (58.21, 224.50)-(68.71, 229.40)   clear
```

Note: an earlier candidate placed the cluster mid-board (x 55-100,
y 83-119) but that region is blocked by C26 (tank cap, courtyard
54.4-77.4 x 70.8-113.9) and PS1 (aux supply, courtyard 92.6-118.5 x
82.3-128.5); the KiCad rotation convention (clockwise) makes those
obstacles vertical, which the initial counter-clockwise model missed.
The bottom pocket is the only viable location.

### Creepage / clearance (pad-to-pad, copper-only)

- HV-to-LV pairs < 12.6mm (RULE 4 "HV to LV", PD3): **0 new** for the
  cluster's HV pads vs. LV/SELV copper pads. The moved components'
  nearest neighbors (R8 zcd/PWR_RTN, C1 w1_1/ac_n, R27 input/GATE_LS)
  are all HV-side; the LV bottom row (R53, R63, R70, R75, U21, U22,
  R50) is at y>=241, clear of the cluster.
- Tank functional creepage < 10mm: 0.
- AC Mains-to-HV clearance < 3mm: 0.
- K1's pad 13/14 are F.Fab-only (non-copper spade tabs) and carry no
  copper, so they do not create creepage surfaces.

### DRC (kicad-cli 10.0.5, --all-track-errors, PD3 DRU regenerated)

Board lineage note: main moved while this branch was in flight (the
#1134 board resync and #1178 6-layer stackup merged). The moves were
re-applied to the post-resync board — K1/RT1/U1/U2 and their
power_in.ntc-no nets verified identical on the new board (identified by
net, not refdes, per handoff §6). All numbers below are measured
against board sha256 `d88fec91` (= main's `b2ae6c66` + the four moves),
with main's pre-move board (`b2ae6c66`) re-measured as baseline.

Main's ceiling vs relocated board (120 samples):

| category | main ceiling (b2ae6c66) | relocated (d88fec91) | delta |
|---|---|---|---|
| creepage | 325 (obs 323-324) | 313 (obs 311-312) | **-13** |
| clearance (uncapped) | 1101 | 1122 | **+21 (move)** |
| hole_clearance | 94 (obs 92-93) | 87 | -7 |
| shorting_items | 196 | 189 | -7 |
| solder_mask_bridge | 146 | 139 | -7 |
| courtyards_overlap | 8 | 8 | 0 (same set, no new) |
| silk_over_copper | 61 | 63 | +2 (move) |
| all other categories | — | — | 0 |

The 8 courtyards_overlap violations are byte-identical to main's set
(R4/C4, K3/C3, L1/C5, C22/C4, C2/C3, C2/PS1, C4/R46, C5/C7) — the move
added zero new overlaps.

## 120-sample re-measurement (protocol)

120 samples of `run_drc` (--all-track-errors, MaximumThreads=1 via
scratch KICAD_CONFIG_HOME) against the relocated board (sha256 d88fec91)
with the regenerated PD3 DRU. Full distribution in
`power_pcb_dataset/drc_ceiling.json` `_march` + provenance.

- creepage observed: 311-312 (spread 1; distribution {312: 104, 311:
  16}; the same upstream KiCad pointer-dedup nondeterminism documented
  since #602). Ceiling set to 313 = max 312 + 1 per the noise-headroom
  guard invariant — DECREASE from main's 325 (band {323, 324}), because
  the relocation moved the cluster away from the LV bottom row.
- clearance (uncapped, `measure_uncapped_drc.py`): 1122, deterministic
  (2 independent runs) — +21 over main's 1101 (main's pre-move board
  re-measured at 1101 this session, matching its committed ceiling
  exactly). Attributed to the relocation: the ntc-no cluster sits in a
  denser neighborhood. This is a genuine, attributed raise — carries
  the `Ceiling-Approval:` trailer.
- warning_ceiling 13583 -> 13585: silk_over_copper 61 -> 63 (+2), a
  direct consequence of the moved components' silkscreen over copper.
  Also carries the `Ceiling-Approval:` trailer.
- Decreases: hole_clearance 94 -> 87, shorting_items 196 -> 189,
  solder_mask_bridge 146 -> 139, creepage 325 -> 313, error_ceiling
  2278 -> 2266.
- courtyards_overlap 8, unchanged — same pre-existing set, zero new.
- All other categories deterministic and at/below the recorded ceiling.

`Ceiling-Approval:` trailer: YES (clearance +21 and silk_over_copper +2,
both attributed to the relocation; measured-live, 120 samples,
kicad-cli 10.0.5, clean tree, resolvable measured_at_commit, input hash
d88fec91 matching the committed board).

## Route verification (batched)

`scripts/route_board.py --net-batching --batch-size 10` was run on the
moved board before the rebase onto main's resync (the route run predates
the rebase; the resync changed unrelated components): **14/14 batches
solved, 0 crashed**, 65/104 nets routed, segments=3483, vias=28,
zones=135.

`power_in.ntc-no` in the routed output: 22 segments at 5.0mm on F.Cu
(vs 72 at 140mm span before — the copper spine is now a compact 26mm
run instead of a 140mm serpentine) + zone outlines. Pad-connectivity
audit reports 2/4 pads joined by drawn copper (K1.13, U2.1) with RT1.2
and U1.2 zone-dependent — the same zone-fill caveat documented in the
full-board-route-verification evidence doc: KiCad zone fill is a
separate stage not available in kicad-cli 10.0.5 (`pcb fill` does not
exist), so zone-dependent verdicts remain "cannot measure" until a
fill pass runs. What the placement fixes is the geometric prerequisite:
the pads are now 26mm apart instead of 140mm, so a single 5mm hull can
span them without fragmenting into 47+ islands.

## Interaction with concurrent board changes (#1173)

While this branch was in flight, main merged **#1173** ("land 7 of 8
verified courtyard-collision fixes", courtyards_overlap 8 -> 1) which
**moved C7 (discharge snubber cap) to (78.12, 224.66)** — directly into
the bottom pocket this placement occupies. Re-clustering on the
post-#1173 board was investigated and found **infeasible without new
violations**: the pocket is now too constrained for K1's 30.5x23.5mm
courtyard plus three companions, and every surviving cluster position
(verified exhaustively over K1's 96 legal spots on the post-#1173 board)
lands a component within 12.6mm of an LV/SELV pad (R26 I_SENSE/+3V3,
R48/R71 safety, U21, R58 gnd, C6 gnd — 14-15 new HV-to-LV creepage
pairs).

Resolution options for the merge (maintainer call):
1. **Rebase order**: land this placement first, then #1173 must choose a
   different spot for C7 (its courtyard fix is not coupled to that exact
   location).
2. **Shift the cluster**: if C7 stays at (78.12, 224.66), the four
   components cannot cluster within 50mm on the current board without
   new creepage violations; the ampacity fix would then require either
   a manual 5.0mm copper connection between the (still scattered) pads
   or moving additional components.

This branch targets the `b2ae6c66` lineage (pre-#1173) where the
placement is fully verified; the conflict is a concurrent-placement
collision, not a defect in either change.

## Files

- `pcb/temper.kicad_pcb` — moved components (only K1/RT1/U1/U2 touched)
- `power_pcb_dataset/drc_ceiling.json` — provenance + `_march` updated
- sha256: `b2ae6c66…` (main pre-move) -> `d88fec91…` (moved; main's resync + the four moves)
