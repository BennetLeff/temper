# D-4: adversarial review of round 17

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Round 17 produced the first FEM board-inductance matrix for leg A and fed
it into the D2 switching simulation. Several of its own bugs were found
late (spurious PEC "vias" from dropped mesh faces; Elmer's VTU averaging of
DG fields; a closure that did not vanish at h = 0). A fresh reviewer should
try to break what remains. **Review only; do not change round-17 files.**

## Read

- `round17/README.md` (all sections) and `round17/d2/README.md`
- `validation-plan/D1-FEM.md` "Amendments after round 17"
- `round17/PACKAGE-INDUCTANCE.md`
- Scripts: `round17/scripts/inductance_matrix.py`, `extrapolate.py`,
  `mesh25d_hybrid.py` (closures and port definitions), `campaign.py`;
  `round17/d2/leg_matrix.cir`, `run_d2.py`, `grid.py`
- Closures: `round17/closures-legA.json`, `closures-legB.json`

## Questions to attack (at least these)

1. **Matrix → SPICE mapping** (`leg_matrix.cir`): the four FEM ports sit at
   the capacitor pads and the driver pins; FETs, gate resistors and shunt
   were short closures. The deck puts one coupled inductor per port in the
   capacitor branches and gate paths. Is that equivalent to the FEM
   network with real devices inserted at the closure positions? Check port
   polarity (each inductor's first node is the port's `a` side) against the
   closure definitions, and the sign of every K.
2. **Common-source inductance:** the deck has no separate LCS; the
   power-to-gate coupling comes only from the FEM mutuals (k 0.13–0.17).
   Round 3's heuristic used LCS = 11.5 nH and failed badly. Is the FEM
   capturing the shared source path correctly (P3/P4 closures return
   through U1.14 sw_a / U1.9 leg_ret)? Could the low coupling be an
   artefact of where the ports and closures are?
3. **Extrapolation to h = 0** (`extrapolate.py`): is the straight line /
   parabola through 1, 2, 3 mm a sound way to remove the closure arches, and
   what does h = 0 physically represent (a flat connection across the pads)?
   Is adding the parts' package inductance afterwards double- or
   under-counting anything?
4. **Mutuals by reciprocity** (`inductance_matrix.py`): L_ij = (1/μ0) Σ vol
   B_i·B_j. Any way the gates (within-tet spread, diagonal vs energy) could
   pass while an off-diagonal is wrong?
5. **Crop margin:** 10 → 15 mm lowered P1 by ~5 %. Is the planned additive
   per-entry correction (from 1.0 mm-mesh matrices at 10 and 20 mm) sound?
6. **D2 criteria and the off-gate cause split** in `grid.py`.

## Deliverable

`round17/delegation/out-D4/README.md`: findings ranked by severity, each
with the file and line, a concrete failure scenario, and how to check it
(a small script or hand calculation committed in your folder where
possible). Explicitly list what you checked and found sound.

## Acceptance

Every finding names a file/line and a reproducible check; no edits to
round-17 files.
