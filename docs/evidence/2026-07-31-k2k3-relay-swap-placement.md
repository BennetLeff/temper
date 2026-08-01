<!-- provenance: commit=23f103c9c64f6d892de2fcf9a546bd4024761d31 dirty=true -->

# K2/K3 relay swap — placement measurement, 2026-07-31

Branch `fix/k2k3-relay-swap` (worktree `.claude/worktrees/k2k3-swap`).
`dirty=true`: every "after" figure was measured in this working tree with
the board edit applied; "before" figures were measured on
`git show HEAD:pcb/temper.kicad_pcb` (== origin/main @ 4a387393e) with the
same tool, same flags, same sample count, and -- critically -- the same
project file (`temper.kicad_pro`) and `fp-lib-table`, by temporarily
swapping the committed board into place under the canonical filename.

Environment: macOS arm64, `kicad-cli` 10.0.4, DRC via
`temper_placer.validation._drc_api.run_drc` (`--all-track-errors`;
bare kicad-cli is not reproducible, see that module's own comment).

## Summary

The RT314012 relay swap lands for **K2 only**. K2's embedded footprint is
replaced in-place at its existing origin, rotated 270° — the only
orientation at that origin where the 29.9 mm courtyard stays inside the
board outline. The swap is DRC-neutral on every error category and improves
three warning categories. **K3 is NOT swapped**: at its origin (47.8, 70.78)
every rotation of the RT314012 introduces NEW cross-net shorts. K3's swap
requires a new placement (placer re-solve), which this change deliberately
does not hand-approximate.

## 1. K2: swapped at rotation 270 — the only fit at its origin

K2 (discharge.k_dis1) sits at (147.96, 102.86). The RT314012's local
courtyard spans x ∈ [-2.8, 27.1], y ∈ [-10.55, 3.05] (29.9 × 13.6 mm).

| rotation | courtyard in board space | verdict |
|---|---|---|
| 0 (as-placed for G5LE-1) | x 145.2..175.1 | **hangs 3.06 mm past the board edge (x=172)** — unbuildable |
| 90 | x 137.4..151.0, y 75.8..105.7 | overlaps T1's courtyard (x 141.0..171.5, y 56.9..81.8) |
| 180 | x 120.9..150.8, y 99.8..113.4 | overlaps U3's courtyard (x 117.8..130.0, y 105.5..113.6) |
| **270** | x 144.9..158.5, y 100.1..130.0 | **EDGE-OK, no courtyard overlap** |

All courtyard spans computed with the rotation convention the repo's own
oracle verified against `pcbnew` (KiCad rotates R(−θ); see
`docs/evidence/2026-07-29-board-regeneration-corrected-footprints.md` §1
and the 2026-07-29 rotation-convention fixes).

## 2. K3: blocked on placement — every rotation shorts copper

K3 (discharge.k_dis2) sits at (47.8, 70.78) rot 90. The RT314012's pad
field reaches 25.34 mm from the origin (G5LE-1's reached 14.2 mm), so the
new pads land on pre-existing copper in every orientation. Measured with
`run_drc` over 3 runs per rotation (relay-attributed violations):

| rotation | new cross-net `shorting_items` (worst) |
|---|---|
| 0 | 30+ items incl. `+170V_BUS` × `DC_BUS_RTN`, `RTD_SDI` × `DC_BUS_RTN` |
| **90 (as-placed)** | **5× `hb.gate_hs.driver-p2` × `discharge.k_dis2-no`** — the NO pad at (47.8, 45.44) lands on a pre-existing B.Cu gate-driver track (e.g. 0.1000 mm track @ (48.85, 45.25)) |
| 180 | 10 items incl. `RTD_SDI`, `SHUTDOWN`, `ina`, `inb`, `hb.gate_hs.driver-p1` |
| 270 | 18 items incl. `RTD_SDI` × `DC_BUS_RTN`, `discharge.k_dis1-nc` × `DC_BUS_RTN` |

The rot-90 short is the instructive one: the RT314012's NO pad (local
(25.34, −7.5)/(25.34, 0) → board (40.3/47.8, 45.44)) sits on a B.Cu track
that carries `hb.gate_hs.driver-p2`. No rotation at this origin clears
all of them; the part needs a new position. Per the repo's own precedent
(docs/evidence/2026-07-28-tank-cap-and-isolator-footprints.md: "No CP-SAT
re-solve was run... I am not doing it, and I am not approximating it"),
placement is the placer's job, not a hand nudge in a footprint swap.

Net effect for K3 in this change: the board keeps the G5LE-1 embedded
copy and `elec/src` keeps `k_dis2` on G5LE-1, with a BLOCKED note in both
places pointing at this document. Its isolation gap remains a tracked,
unresolved blocker (the 2026-07-28 Finder excursion notes in
`elec/src/modules.ato` explain why no same-pitch family part substitutes).

## 3. K2 swap: DRC before/after (N=6, then 120-sample confirmation)

Both boards measured in place under the canonical filename (project
settings and fp-lib-table identical). `kicad-cli` 10.0.4, `--all-track-errors`.

| category | before (HEAD) | after (K2 swapped) | Δ |
|---|---|---|---|
| annular_width | 4.0 | 4.0 | 0 |
| clearance | 499.8 [499-501] | 499.2 [499-501] | 0 (noise) |
| copper_edge_clearance | 15.0 | 15.0 | 0 |
| courtyards_overlap | 14.0 | 14.0 | 0 |
| drill_out_of_range | 4.0 | 4.0 | 0 |
| hole_clearance | 109.0 | 109.0 | 0 |
| hole_to_hole | 1.0 | 1.0 | 0 |
| shorting_items | 118.0 | 118.0 | 0 |
| solder_mask_bridge | 69.0 | 69.0 | 0 |
| tracks_crossing | 3.0 | 3.0 | 0 |
| via_diameter | 4.0 | 4.0 | 0 |
| **error total** | **840.8** | **840.2** | **−0.6** |
| holes_co_located (W) | 2.0 | 0.0 | **−2** |
| lib_footprint_issues (W) | 9.0 | 10.0 | **+1** |
| lib_footprint_mismatch (W) | 25.0 | 24.0 | **−1** |
| missing_courtyard (W) | 5.0 | 5.0 | 0 |
| pth_inside_courtyard (W) | 9.0 | 9.0 | 0 |
| silk_* (W) | 199×3 | 199×3 | 0 |
| track_dangling (W) | 29.0 | 29.0 | 0 |
| via_dangling (W) | 4.0 | 4.0 | 0 |
| **warning total** | **680** | **678** | **−2** |

A 120-sample confirmation run on the edited board reproduced every count
(clearance 499.19 avg, observed range 499-501 as documented in the
ceiling's `nondeterministic_error_types`).

Attribution of the three warning deltas, all to the K2 footprint swap:

- **holes_co_located 2 → 0**: the two co-located via/PTH-hole pairs sat on
  K2's G5LE-1 pads (`Via [discharge.k_dis1-nc]` on top of `PTH pad 4 of
  K2`). The new footprint's pads are elsewhere; the pairs are gone. This
  is the swap doing its job.
- **lib_footprint_mismatch 25 → 24**: K2's embedded copy now matches its
  library footprint (the G5LE-1 copy was among the 25 mismatches).
- **lib_footprint_issues 9 → 10**: K2 now references the project `temper`
  library, which this measurement environment reports as "not enabled" —
  the same warning class T1/C6/U7 already generate (7 temper references
  now vs 6 before). Not a new failure class; a consequence of using a
  project-local custom footprint, exactly as the prior resync entries
  recorded for `tank.c_tank3`.

`unconnected_items` (kicad-cli JSON): 390 → 393 (+3). The three new
records are K2's own pad pairs now unrouted — e.g. `PTH pad 1 [PWR_RTN]
of K2` ×2 and `PTH pad 3 [discharge.k_dis1-no] of K2` ×2 — all SAME-NET,
with the traces to the old G5LE-1 pad positions still in place. This is
the expected consequence of a footprint swap (pads move, traces do not);
re-routing K2's connections is the placer/router follow-up, same class as
the `unconnected_items` +6 the 2026-07-29 board regeneration recorded and
proved same-net.

## 4. REQ-SAFE-01 before/after (copper-to-copper)

`temper_placer.requirements.validators.clearance` on the real board
fixture (`packages/temper-placer/tests/requirements/safety/
test_clearance.py::test_temper_board_clearance_compliance`, expected
failing per its docstring until a placement re-solve):

| | before | after |
|---|---|---|
| violations / pairs | 123 / 86 (11 intra) | 122 / 87 (8 intra) |

K2 rows before → after:

| pair | before | after | net |
|---|---|---|---|
| K2 <-> K2 (intra, G5LE-1 coil-to-contact) | 3.559 mm ×3 records | — | **CLEARED** — the RT314012's 12.76 mm internal gap passes both the 12.6 mm reinforced bar and the 6.0 mm clearance minimum |
| U6 <-> K2 | 11.373 mm | 10.625 mm | worse (placement-class) |
| K2 <-> D4 | — | 10.491 mm | NEW (placement-class) |
| K2 <-> R18 | — | 11.379 mm | NEW (placement-class) |

K3 rows unchanged (K3 not swapped): `K3 <-> K3` intra 3.559 ×3, `R12 <-> K3`
3.894 ×3.

The three K2 inter-component pairs (10.5–11.4 mm against the 12.6 mm
reinforced bar for DC_BUS<->LV_CONTROL) are placement-class, not
part-class: the part's own isolation is now correct, but K2's copper at
rot 270 sits closer to D4/R18/U6 than the G5LE-1's did. Like K3's
blocked swap, they need the placer re-solve — they are the same finding
from two directions: **the relay swap is a placement change, and the
placement work is deferred to the placer**, exactly as the handoff
documented for `tank.c_tank3` ("the RT314012's courtyard may change what
fits").

## 5. What was verified and what was not

Verified (measured this session):

- K2's courtyard fit at all four rotations at its origin (§1).
- K3's copper shorts at all four rotations at its origin (§2).
- DRC before/after, N=6 + 120-sample confirmation, project-resolved (§3).
- Every copper item's net resolved BY NAME, unchanged before/after
  (`scripts/check_copper_net_consistency.py`: 2482 items, 0 violations;
  `check_footprint_drift.py`: 169/169 matched, 0 violations;
  `check_domain_partition.py`: 0 crossings; `check_pad_orientation.py`:
  PASS). Board parse via kiutils: 169 footprints both sides.
- REQ-SAFE-01 before/after on the real board (§4).

Not verified / deliberately not done:

- **No K3 placement was chosen.** Finding a position for the RT314012
  near K3's origin is placer work (CP-SAT re-solve + re-route), not a
  hand nudge in this PR. K3 stays on G5LE-1, netlist and board
  consistent, gate-green, blocker documented.
- **No K2/K3 re-routing.** Traces to the old G5LE-1 pad positions remain
  in place; K2's new pads are unrouted (390 → 393 same-net unconnected).
  The router is the follow-up, as with every prior footprint swap.
- **`drc_ceiling.json`** was re-measured (120 samples) and updated in
  this same change with a `_march` entry; the one per-type warning rise
  (lib_footprint_issues 9 → 10) carries the `Ceiling-Approval:` trailer.

## Reproduction

```bash
make netlist
uv run --no-sync python scripts/check_copper_net_consistency.py
uv run --no-sync python scripts/check_footprint_drift.py
uv run --no-sync python scripts/check_domain_partition.py
uv run --no-sync python scripts/check_pad_orientation.py
export PYTHONPATH="$(pwd)/packages/temper-placer/src"
uv run --no-sync python -c "
from pathlib import Path
from temper_placer.validation._drc_api import run_drc
for _ in range(120):
    run_drc(Path('pcb/temper.kicad_pcb'))
"
```
