# Mains↔SELV Isolation Barrier — Feasibility Evidence (2026-08-01)

Reproducible analysis of whether a straight `MAINS_SELV_ISOLATION_BARRIER` keepout
(≥8 mm, 4 copper layers, full-height bisection) can be placed on the current board,
and what the floorplan re-solve must achieve. Script:
`docs/evidence/2026-08-01-isolation-barrier-feasibility.py` (run with
`uv run --no-sync python docs/evidence/2026-08-01-isolation-barrier-feasibility.py`).

## Board inventory
- Board outline: **152 × 234 mm** (x ∈ [20, 172], y ∈ [20, 254]).
- 524 pads. Component domains (from `elec/domain_manifest.yaml` + netlist):
  **HV-only = 45, SELV-only = 106, isolators = 8, unclassified = 10.**
- Isolators: C6, K1, K2, K3, PS1, T1, U3, U7. Unclassified: C10, R34, R40, R42, R45,
  R52, R57, R64, R69, R72.

## As-is geometry (confirms the gate's report)
- **Every one of the 15 full-height 10 mm columns mixes both domains** (HV and SELV
  pads in every column).
- Nearest cross-domain, cross-component pad pair (edge-to-edge, in-board): **0.178 mm**
  (`C17.2` net `hb.gate_hs.driver-p2` ↔ `R32.1` net `+3V3`).
- **42 pad pairs within 8.0 mm** across 25 distinct component pairs.

## Straight-corridor feasibility (as-is, all pads)
No straight corridor exists at W = 8.0 / 10.0 / 12.6 mm in either orientation.

| Orientation | HV side | Raw region gap | W=8/10/12.6 |
|---|---|---|---|
| X (vertical, split L/R) | lo | −150.6 mm | none |
| X (vertical) | hi | −151.1 mm | none |
| Y (horizontal, split T/B) | lo | −233.5 mm | none |
| Y (horizontal) | hi | −232.6 mm | none |

## Drift required for a clean corridor (best position, HV_lo)

| Orientation | W | movers | total drift | max single |
|---|---|---|---|---|
| X | 8.0 | 78 | 3096.0 mm | 134.85 mm |
| X | 10.0 | 80 | 3175.5 mm | 136.35 mm |
| X | 12.6 | 80 | 3279.5 mm | 138.85 mm |
| Y | 8.0 | 52 | 3727.1 mm | 127.05 mm |
| Y | 10.0 | 53 | 3780.8 mm | 127.05 mm |
| Y | 12.6 | 57 | 3852.8 mm | 129.55 mm |

X movers are HV-dominant (the power stage moves toward the hi side); Y movers mix
HV and SELV. Y needs fewer movers and a lower max single-component drift; X keeps
HV components clustered.

## Isolator pad-cluster feasibility (the placer's `evaluate_isolator_feasibility`)

| Isolator | gap_x (mm) | gap_y (mm) | achievable max | feasible @ 8.0 / 10.0 / 12.6 |
|---|---|---|---|---|
| C6 | +8.000 | −2.000 | 8.000 | 8.0 ✓ / ✗ / ✗ |
| K1 | −4.075 | +8.000 | 8.000 | 8.0 ✓ / ✗ / ✗ |
| K2 | +12.760 | −2.500 | 12.760 | ✓ / ✓ / ✓ |
| K3 | −2.500 | −0.500 | **−0.500** | ✗ / ✗ / ✗ |
| PS1 | +35.500 | −3.000 | 35.500 | ✓ / ✓ / ✓ |
| T1 | −5.200 | +9.100 | 9.100 | 8.0 ✓ / ✗ / ✗ |
| U3 | +8.560 | −1.600 | 8.560 | 8.0 ✓ / ✗ / ✗ |
| U7 | +8.100 | −0.600 | 8.100 | 8.0 ✓ / ✗ / ✗ |

**K3 cannot achieve even the 8.0 mm gate floor** (its pad clusters overlap by
0.5 mm). Five isolators (C6, K1, T1, U3, U7) achieve exactly 8.0 mm — none of the
10.0/12.6 mm figures. Only K2 and PS1 clear 12.6 mm.

## Re-homing isolators does not create a corridor
Excluding isolator pads from the domain extents leaves the raw region gaps
unchanged (−150.6 mm X, −233.5 mm Y) — the domain component interleave itself is
the obstacle. **The floorplan re-solve is genuinely required**; isolator re-homing
alone is insufficient (matches the plan's rejected zone-first shortcut).

## Board edge constraints (OQ4 input)
- `C27.1`/`C27.2` are staged **outside the board** (−18.75 mm past the outline).
- Nearest in-board pads to the edge: `U1.2` at 0.95 mm, `TP2.1` at 1.00 mm,
  `R67.1` at 1.16 mm.
- A corridor spans the full 234 mm (X) or 152 mm (Y); edge clearance will be
  squeezed and must be re-validated after the re-solve.

## What this resolves
- **OQ2 (isolator BOM) is required and K3 is the blocker**: the first phase must
  rework K3's pad placement (and widen the C6/K1/T1/U3/U7 clusters beyond 8.0 mm)
  before any 10/12.6 mm target is reachable.
- **OQ3 (axis)**: both orientations are feasible only after the re-solve; Y needs
  fewer movers (52 vs 78) and lower max drift (127 vs 135 mm), X keeps the power
  stage clustered. Human picks; the data recommends Y as less disruptive.
- **OQ1 (width)**: 12.6 mm costs only ~+183 mm total drift over 8.0 mm (X) but is
  gated by the isolator work; target 8.0 mm now, widen after the isolator BOM
  phase.
