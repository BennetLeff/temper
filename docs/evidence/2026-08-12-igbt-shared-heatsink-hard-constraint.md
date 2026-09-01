<!-- provenance: commit=e542aea35f749abb51c1ce72101000d26fb629c7 dirty=UNKNOWN -->

# Making the shared-heatsink requirement a hard placement constraint

The two TO-247 IGBTs sit 90 degrees apart in rotation on the committed
board while the BOM costs one shared heatsink for both. This makes that
requirement a constraint the solver enforces, in both backends, and shows
it rejecting the board as committed.

## What was encoded, and which constraint types

`packages/temper-placer/src/temper_placer/placer/cp_sat/heatsink_colocation.py`.
**No new constraint type.** Three wire types, all already registered in
both backends:

| Requirement | Type | Pumpkin | OR-Tools |
|---|---|---|---|
| identical rotation | `fixed_rotation` x2, same value | `main.rs:558` | `model.py:344` `add_fixed_rotation` |
| near-zero perpendicular offset | `aligned` | `main.rs:399` | `handlers/aligned.py:22` |
| both packages on one face | `adjacent`, `edge_to_edge` | `main.rs:358` | `handlers/adjacent.py:22` |

Reuse was not only cheaper. Pumpkin `exit(2)`s on an unregistered type
(`main.rs:621-627`) while OR-Tools warns and continues
(`_encoder_core.py:327-334`), so a type added to one backend and missed in
the other under-constrains silently. Reuse also means the pinned engine
binary is untouched: modifying `main.rs` would require a rebuild into the
shared `CARGO_TARGET_DIR`, which would break
`scripts/verify_pumpkin_engine.py` for every other worktree on this
machine until each re-pinned.

It is reachable from the production entry point as
`solve_placement(..., heatsink_colocation=<rot 0..3>)`
(`_encoder_solve.py`), the same opt-in shape `isolation_barrier` already
uses and posted at the same point in the sequence. Opt-in, and an explicit
rotation rather than a bool, because the wire vocabulary can only pin a
rotation, not equate two.

**Nothing in `_constraint_types/` was reusable.** `thermal.py`'s
`ThermalConstraint`/`ThermalProperties` model spacing, edge preference and
per-component dissipation; neither carries a co-location group, a heatsink
identity, or any rotation field. There is no unwired thermal-grouping
model to connect.

### The one thing the vocabulary cannot say

The physical requirement is `rot[U5] == rot[U6]` -- four equally valid
assignments. No wire type expresses variable-to-variable rotation
equality; `fixed_rotation` pins to a literal. The module follows the
pattern `isolation_barrier.py` already established for exactly this
(`_best_rotation_for_barrier` at line 389, then
`Add(cvars.rot_ref == rot_value)` at line 631): choose a common rotation,
pin both, and let the caller enumerate the alternatives. All four were
enumerated below; all four solve.

Pinning is stronger than physics requires but not arbitrary in effect:
HS1's device pattern is drilled by us, not the vendor ("drill/tap M3
pattern for 2x TO-247 + 2x TO-220",
`docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md:109`),
and no chassis drawing exists that would privilege an orientation, so all
four common rotations describe equally buildable assemblies.

## Tolerances: what was derived and what was not

**Derived -- separation, 87.2mm.** `MAX_COLOCATED_GAP_MM = 120.0 - 2 x 16.4`.

- 120.0mm: HS1's smallest published dimension. `docs/hardware/BOM.md:542`
  and `docs/plans/2026-07-16-001-...:109` both give the envelope as
  "120 x 125 x 135.8mm" and nothing more. **Which of the three is the
  mounting face is not established by anything in this repo** -- there is
  no Wakefield-Vette datasheet under `datasheets/`, independently noted at
  `docs/hardware/PART_STRESS_AUDIT.md:338`. The smallest was taken, so the
  bound is the tightest the data supports rather than the most permissive.
- 16.4mm: measured off the committed board, not a datasheet. The
  `Package_TO_SOT_THT:TO-247-3_Vertical` F.CrtYd rect is
  `(-2.75, -2.58) -> (13.65, 2.95)` (`pcb/temper.kicad_pcb:7982`), and
  `parse_kicad_pcb` reports `bounds = (16.4, 5.9)`. The TO-247 body is
  narrower than its courtyard (15.875mm nominal), so this overstates the
  face each device consumes -- again the conservative direction.

This bound is real and loose. It does not by itself reject the committed
board (the measured edge-to-edge gaps are ~63-65mm, inside 87.2mm). It is
reported as derived-and-loose rather than tightened by invention; the two
TO-220 rectifiers share the same face and have to fit in that gap.

**Not derived -- the 1.0mm alignment tolerance.** Carried across from
`thermal_management.yaml:30` unchanged, neither tightened nor loosened,
and labelled a declaration in the source. What could be established:

- Sil-Pad 400 0.009" (`BOM.md:545`) is 0.2286mm thick in total, so
  0.2286mm is where a *rigidly* mounted pair would consume the whole pad.
- That floor does not apply, because the devices are lead-formed to a
  chassis-mounted sink (`2026-07-16-001-...:118`: "~1kg class: mount to
  chassis, not PCB; devices lead-formed or on a daughter edge"), which
  decouples the tab plane from the PCB pad plane by however much the lead
  form allows. **No lead-form drawing exists in this repo**, so the mapping
  from "mm of PCB centre offset" to "mm of tab coplanarity error" is
  unknown and any figure, 1.0 included, is a declaration.

The violation does not depend on the figure: the board misses by 70.90mm.

**Not encoded -- board-edge proximity.** The mechanical documentation says
the opposite of "the heatsink mounts at a board edge" (chassis part, not
PCB-mounted, per the same line 118), and no in-repo drawing names which
edge. `thermal_management.yaml`'s `side: top, edge: flush` is a
declaration, not a derivation, so it was not promoted.

**What survives every mechanical degree of freedom.** Lead-forming absorbs
millimetres of position; it cannot rotate a device's body 90 degrees
relative to its own lead row. Rotation equality is the part no assembly
tolerance can rescue, and it is exactly the part the board violates.

## Proof it rejects the committed placement

Measured from `pcb/temper.kicad_pcb` (read-only):

```
U5  (at 23.72 233.25 270.0)   line 7969   rotation index 3   box centre (23.72, 238.70)
U6  (at 100.07 159.33 180.0)  line 8008   rotation index 2   box centre (94.62, 159.33)
```

`check_heatsink_colocation` against that placement:

```
VIOLATION [rotation]  (U5, U6) measured=2 limit=1
    tab planes face different directions: U5=270deg, U6=180deg
    -- no single flat face of HS1 can contact both
VIOLATION [alignment] (U5, U6) measured=70.90mm limit=1.0mm
    centre offset perpendicular to the Y mounting axis is 70.90mm
```

Pinned as a regression test, with a guard that fails loudly if the board's
rotations ever change:
`packages/temper-placer/tests/placer/cp_sat/test_heatsink_colocation.py::test_rejects_the_committed_board_placement`.

### Solver-level rejection, both backends

A pure Python checker rejecting a placement is not the same as the solver
rejecting it. Both were run.

Pinning the committed *positions* into the full board model proves nothing
on its own -- U5/U6 are HV-only, so the isolation barrier alone already
rejects them at y=218.7/139.33 against its own `y_end <= 113` bound
(measured: `infeasible` in 0.15s with the heatsink constraint absent). So
the probe isolates the constraint instead: a two-component model, no
barrier, no netclass/courtyard base, pinned to the committed rotations.
The only difference between the two solves is this constraint.

Pumpkin (`docs/evidence/scripts/2026-08-12-heatsink-colocation-pumpkin-run.py --isolate`):

```
committed rotations, WITHOUT heatsink constraint            -> optimal
committed rotations + heatsink constraint (common rot 0)    -> infeasible
committed rotations + heatsink constraint (common rot 1)    -> infeasible
committed rotations + heatsink constraint (common rot 2)    -> infeasible
committed rotations + heatsink constraint (common rot 3)    -> infeasible
```

OR-Tools: same result, `test_ortools_model_rejects_the_committed_rotations`
(INFEASIBLE for all four common values).

## Does the model still solve, with the isolation barrier intact?

Yes, at every common rotation. Engine pin verified first
(`scripts/verify_pumpkin_engine.py`, exit 0, sha256 `7ff153f4...`,
source_commit `5bbf650d47`).

Board `152x234mm`, 169 components, tau=0.4mm. Base: 9,714 netclass +
6,282 courtyard = 15,996 SEPARATED constraints. Barrier: PD2/8.0mm,
horizontal, corridor Y `[113.0, 121.0]`, hv_only=43, selv_only=106,
isolators=8, unclassified=12. **All 8 isolators hard-constrained** --
nothing relaxed.

| Run | status | solver time | U5 | U6 |
|---|---|---:|---|---|
| barrier only, no heatsink constraint | optimal | 0.94s | (3.65, 8.75) rot 1 | (39.64, 38.05) rot 3 |
| + heatsink, common rot 0 | optimal | 1.46s | (98.91, 47.93) rot 0 | (124.84, 48.83) rot 0 |
| + heatsink, common rot 1 | optimal | 1.33s | (3.53, 68.69) rot 1 | (3.51, 50.59) rot 1 |
| + heatsink, common rot 2 | optimal | 1.56s | (98.91, 47.93) rot 2 | (124.84, 48.83) rot 2 |
| + heatsink, common rot 3 | optimal | 1.38s | (3.53, 68.69) rot 3 | (3.51, 50.59) rot 3 |

Positions are box centres in the normalized frame (board origin (20, 20)
subtracted). Rot 0/2 and 1/3 coincide because the box model cannot
distinguish a 180-degree flip -- which is precisely why the *baseline*
row is the finding it is.

### The baseline row is the point

Without this constraint the solver, run cleanly, produced **U5 at 90
degrees and U6 at 270 degrees** -- a fresh unbuildable board, from a
correct solve, in under a second. The committed board's mismatch is not a
one-off historical accident; the model had nothing in it that would
prevent the same outcome again.

### Correction to the premise about joint infeasibility

The task expected the barrier to be near the edge of feasibility, citing
`docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md`'s
"all 8 isolators -> infeasible in 3.17s, relax U6 -> optimal in 2.6s".
That result holds for the board that document measured -- the
**reconciled** 168-component board, which is not on `main` and never
landed. On the **committed** board, `DomainPartition` derives a different
isolator set:

```
committed board:  C6, K1, K2, K3, PS1, T1, U3, U7      (8, all feasible jointly)
reconciled board: C6, K1, K2, K3, PS1, T1, T2, U6      (8, jointly UNSAT)
```

U3 (a stale ZCD opto reconciliation removes) and U7 are isolators here;
T2 (the new OCP-02 current transformer) and U6 are not present/classified
as such. This matches `isolation_barrier.py`'s own docstring for the
pre-reconciliation board. So on the committed board all 8 isolators at
PD2/8.0mm are jointly feasible, and `--relax U6` is a no-op because U6 is
not an isolator here. **The barrier was not relaxed in any run above.**

One shim was needed and is visible in the harness rather than hidden:
`classify_domain_partition` marshals `pin.net` into a pyo3 `str` and
raises `TypeError` on an unconnected pad. The committed board has 5 (K1
x1, U3 x4); the reconciled board the prior evidence used has no U3 at
all. Unconnected pads are on neither HV nor SELV nets, so substituting
`""` reproduces exactly the classification the Rust routine would give.

## Where U5/U6 land, and does it route

The rot-1 solution was written back and routed.

Write-back via `write_placements_to_pcb(..., board_origin=(20, 20))`
(the origin-corrected path from
`docs/evidence/2026-08-11-board-origin-write-path-fix.md`): 169
components updated, 0 skipped, 0 warnings.

```
U5  (at 23.53 94.14 90.0)   box centre (23.53, 88.69)
U6                90.0      box centre (23.51, 70.59)
```

Both at 90 degrees, 0.02mm apart perpendicular to the mounting axis,
18.10mm apart along it -- a row that a single flat face can contact.
Re-parsed from the written file, `check_heatsink_colocation` reports no
violations.

- `scripts/check_board_containment.py`: **PASS**, 169 footprints / 527
  pads, all copper inside the outline. (The prior place-and-reroute
  evidence reported 2 near-edge violations on its board; this one has
  none.)
- `scripts/route_board.py --net-batching`: **completes**, 438.5s wall.
  86/102 nets routed (84.3%), 4,497 segments, 58 vias, 84 zones, 11
  batches, 0 crashes. Pad-level connectivity, the router's own primary
  metric: 55/139 nets fully pad-connected, 16 unrouted.
- Re-parsed from the routed board, U5/U6 are unchanged and the constraint
  still holds.

**Explicitly outstanding, not inferred:**

- **No DRC measurement.** `kicad-cli` is not installed in this
  environment (`which kicad-cli` -> not found), so
  `power_pcb_dataset/drc_ceiling.json`'s clearance/creepage comparison
  could not be made. The prior place-and-reroute experiment found a real
  +113 clearance regression on *its* placement, which is exactly the
  measurement missing here. **No board change should be landed on the
  strength of this document alone.**
- **No matched routing baseline.** The 86/102 figure was not compared
  against routing the committed placement under identical flags in the
  same session, and `--net-batching` was used (for memory safety -- two
  other agents' `route_board.py` runs were live) where the prior evidence
  did not. The claim supported is "the placement routes", not "it routes
  better or worse than before".
- `pcb/temper.kicad_pcb` was **not** modified. Everything above was
  produced into a scratch copy.

## Reconnection to `thermal_management.yaml`

Constraint 1 (`on_side` + `aligned` on `[Q1, Q2]`) is left declared and
now carries a comment naming `heatsink_colocation.py` as where the
enforcement lives, why its `Q1`/`Q2` refs could never carry it (both are
live designators for *different* parts, and
`temper_constraints.references.yaml` refuses the alias on purpose), and
which of its three parts were derived, carried across unchanged, or
deliberately not promoted.
