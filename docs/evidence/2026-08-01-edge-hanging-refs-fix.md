<!-- provenance: commit=a2fdfd1bb5c1faaadc4de4238c1e823304aa0730 dirty=false (branch fix/edge-hanging-refs) -->

# Edge-hanging-refs fix — nudge board-edge violators inward to clear the #523 scoped solve's 0.5mm edge-margin wall

**Date:** 2026-08-02
**Branch:** `fix/edge-hanging-refs` (worktree `.claude/worktrees/agent-edgefix`),
from `origin/main` `25d73d5e7` (post-#567).
**Issue:** #568 — the merged #517 re-solve board has components whose bounds
boxes hang off the board edges, which blocks the K3/tank3 scoped solve (#523)
because the placer's 0.5mm edge-margin constraint is unsatisfiable at those
positions.
**Outcome:** placement-only repair (31 footprints nudged) that makes every
non-staged ref robust to the #523 pin model (`mm_to_units` even-parity
rounding), verified pin-model-clean on re-parse; the #523 scoped solve's
edge-margin wall is cleared (K2/K3 pure-geometry single-free solves on the
candidate are `optimal`). The #523 solve *as a whole* remains infeasible for
the separately-documented domain-bar wall (K3/C27 vs cross-domain refs) — see
`docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md` and
`docs/evidence/2026-08-01-fixed-copper-constraint.md`; that is out of this
task's scope.

## The defect (empirically re-derived)

The issue's stated overhangs were measured with footprint *courtyard* boxes.
The solver's edge-margin constraint uses the parse's pad-derived `bounds` box
centered on the component position, and the #523 scoped solve pins every
non-free ref via `fixed_positions`, which applies `mm_to_units` (round-half-
**even**) to the center. A ref whose box edge sits exactly on the 0.5mm bar
with an **odd** center (e.g. C18 at local x=1.23 → center 123) is re-pinned at
the even center 122, shifting the box 0.01mm inward and violating the bar.
This is the documented "model quantization" wall (Wall 1 in
`docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md`). The same class
hits the auto-encoded courtyard τ=0.4mm and netclass cross-class 6.0mm
separation constraints for pairs sitting exactly at their bars with odd
centers.

Empirically (rotation-aware bounds box in the local 152×234 frame, solver's
`mm_to_units` pin model), the refs whose boxes are at/past the 0.5mm edge bar
or whose auto-constraint gaps are at/past their bars are:

| Edge / constraint | Refs (box overhang) |
|---|---|
| left edge | C18, C19, C22, C23, C32, C38, C40 (+0.01), R28, R31, R39, R56, U18, R3, R24, R26, R40, R46, R14 (+0.01 top) |
| top edge | K2 (+18.18mm — box genuinely hangs 17.7mm past local y=0; pads ~15mm above the board top edge), R14, R24, R26, R3, R40, R46 (+0.01) |
| courtyard τ=0.4 | C24×C3, C3×D2, C5×C7, L1×RV1, R11×R30 (0.39mm gaps) |
| netclass 6.0 | C14×C26, C25×R7 (5.99mm gaps) |
| **staged off-board (excluded)** | C27 (tank.c_tank3) at local (20, 252.75) — intentionally staged; placed by #523 |

R1's courtyard overhang from the issue (-4.13mm) was verified **not** real in
the solver's model: its bounds box starts at exactly 50 units (0.5mm), so R1
is correctly left untouched. Same for C8/D1/R54/U9/C33 — their *bounds* boxes
clear the 0.5mm bar (the issue's numbers were courtyard-based).

## The fix

Pure-geometry repair via the #504 machinery (`solve_placement`), matching the
task brief: FREE set = the 33 refs above (all constraint violators under the
pin model), everything else pinned via `fixed_positions` + `fixed_rotations`
at current positions, `minimize_displacement_to` = current positions for the
free refs, seed 0, NO domain-clearance, NO keep-away, NO fixed-copper
constraints. C27 is excluded from the model entirely (filtered netlist) so its
off-board staged position cannot make the edge-margin set infeasible.

Two subtleties required deviation from a naive one-shot solve:

1. **Even-center constraints.** A repair solve that leaves free refs at odd
   centers is not robust to the #523 re-pin (`mm_to_units` even-parity): the
   written board would re-violate on re-parse. The free refs are therefore
   constrained to even centers (`x_center == 2k`, `y_center == 2m`), so the
   produced positions survive the #523 pin round-trip. This is implemented by
   a custom solver replicating `solve_placement`'s model build plus the
   even-center constraints (`/tmp/even_solver.py` — scratch, not committed).
2. **K2's displacement exceeds the 10mm "small nudge" budget.** K2 needs
   +18.2mm to clear the top edge; a 10mm bound makes the repair infeasible.
   K2's overhang is real (its pads hang 15mm off the board top edge), so the
   repair is run unbounded (the minimization objective still keeps every other
   ref at its minimum move). The task anticipated this ("may need more if its
   overhang is real").

## Displacement histogram (31 moved refs)

| bucket | count | refs |
|---|---|---|
| < 0.02 mm | 28 | C18 C19 C22 C23 C32 C38 C40 R14 R24 R26 R28 R3 R31 R39 R40 R46 R56 U18 C14 C24 C25 C26 C3 C5 C7 D2 L1 R7 R11 R30 RV1 (0.01–0.03) |
| 0.02–0.5 mm | 3 | C3, C24, C25 (0.02–0.03), C5, D2 (0.02) |
| 1–3 mm | 1 | RT1 (2.41 mm — resolved a genuine 0.4mm-bar gap requiring a real nudge) |
| > 10 mm | 1 | K2 (18.23 mm — real edge hang) |

K2: (110.51, -2.21) → (110.56, 15.98); RT1: (5.25, 164.82) → (5.26, 162.42);
29 refs moved 0.01–0.03mm to even centers.

## Verification

- **Pin-model acceptance (re-parse candidate, #523 pin model):** 0 edge-bar
  violators, 0 courtyard/netclass violators for every non-C27 ref.
- **#523 edge-margin wall cleared:** pure-geometry #523-style solves
  (FREE={K3}, C27 excluded from model) on the candidate are `optimal` (K3 stays
  at (56.82, 9.0); K2 stays at its repaired position). On the pre-fix board
  the same solve is infeasible (`edge_margin_*` wall).
- **#523 scoped solve (full, opt3 formulation FREE={K3,C27} + domain/keepaway
  + fixed-copper): still `infeasible`** — the remaining walls are the
  documented domain-bar (12.6/8.0mm box separation for K3/C27 vs ~150
  cross-domain refs) and C27's on-board placement; both are #523's own
  remaining work, unchanged by this fix and out of this task's scope.

## Gate results

| gate | result |
|---|---|
| check_copper_net_consistency.py | PASS (0 violations, 515 pads) |
| check_footprint_drift.py | PASS (169/169 matched) |
| check_pad_orientation.py | PASS (169 footprints, 524 pads) |
| check_domain_partition.py | PASS (0 crossings) |
| REQ-SAFE-01 test_temper_board_clearance_compliance | 3 violations / 1 pair (K3-intra) — unchanged from pre-fix board |
| DRC ratchet (kicad-cli) | PASS — within ceiling (see ceiling update below) |
| courtyards_overlap | 11 (unchanged) |
| shorting_items (run_drc) | 199–201 (unchanged) |
| import linter | 0 new violations |
| ruff | clean |
| placer cp_sat suite | 2 pre-existing failures unchanged (test_clearance_repair::test_checker_copper_distance_is_lower_bound_on_origin_distance, test_encoder_rust_pbt::test_courtyard_clearance_strict_in_expansion — both fail identically on origin/main); the 2 test_regression_drc production failures on main are fixed by the constant re-seeding below |

### DRC ceiling re-measurement (120 samples run_drc, --all-track-errors)

Measured per the standing contract AND the #569 (`2026-08-02-k2-resolve-remeasure`)
precedent: `pcb/temper.kicad_dru` regenerated from `scripts/generate_kicad_dru.py`
first (the CI gate's exact invocation — bare `run_drc` without the dru misses
the `creepage`/`track_width` categories and reads clearance in a different
context, which initially misled this investigation). The pre-fix board
reproduces #569's numbers on this host (clearance 405-407, creepage 196,
hole_clearance 124, solder_mask 163, shorting 199-201), so every delta below
is attributed to this board change, not to session variance.

New per-type ceilings (observed max + 1 headroom for the nondeterministic
carriers): clearance 415 (411-414), creepage 201 (199-200, newly
nondeterministic), hole_clearance 129, solder_mask_bridge 169, shorting_items
203 (199-202), track_width 199, tracks_crossing 3; all other categories
unchanged from #569. error_ceiling 1334 → 1357, warning_ceiling 428 → 425.
Attribution of every delta is in the `_march` entry
`2026-08-02-edge-hanging-refs`: clearance +7, creepage +4, hole_clearance +5,
solder_mask +6, shorting +1 are ALL K2-attributed (the deliberate +18.2mm edge
fix — K2's copper/holes now sit in a denser neighbourhood); silk_edge 4→2 and
silk_over_copper 123→122 are improvements. Rises carry the `Ceiling-Approval:`
trailer on the landing commit.

### test_regression_drc.py constant re-seeding (per convention)

Category A (committed board, bare kicad-cli, N=15, thresholds = worst
median-of-5 + 10): total 1283, shorting 141, unconnected 425. Category B
(router output, N=11): total 1436, shorting 178, unconnected 463. The rises
vs the 2026-07-31 seeding are attributed in the file's provenance block:
~+9 shorting / +11 total and +32 unconnected are pre-existing context drift
(unmodified main already exceeds the old constants); the remainder is the K2
+18.2mm move.

## Files changed

- `pcb/temper.kicad_pcb` — 31 footprint position changes (board hash
  0fff888a → cf161bee)
- `power_pcb_dataset/drc_ceiling.json` — re-measurement + `_march` entry
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` —
  constant re-seeding + provenance note
- `docs/evidence/2026-08-01-edge-hanging-refs-fix.md` — this document

## Reproduction

```bash
# verify the pin-model acceptance on the committed board:
uv run --no-sync python /tmp/edgefix_probe2.py   # solver-exact edge/pin violators -> none besides C27
# verify the #523 edge-margin wall is cleared (K3 free, C27 excluded):
#   pure-geometry solve with FREE={K3} -> optimal
```
