<!-- provenance: commit=35fba20a20d67c3d68ab90420b88ab814a3a8fa9 dirty=false (branch feat/tank-creepage-placement, worktree /home/bennet/Desktop/temper/.claude/worktrees/tank-creepage-placement, base origin/main @ 565078e54, rebased after origin/main advanced past this branch's original base 58292f8f1). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 -- UNCHANGED throughout (git status clean against it; every write below targets a scratch copy outside the repo tree). Pumpkin engine verified via scripts/verify_pumpkin_engine.py: sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd path=target-shared/release/pumpkin_engine -- NOT rebuilt by this work. kicad-cli 10.0.5 (/home/bennet/.local/bin/kicad-cli) WAS available this session and was used for containment; the creepage-rule-specific DRC comparison is marked outstanding below for a reason stated in Sec 6, not because the tool was missing. Figures for the 6.3mm/10.0mm requirement and the C25 pad2<->discharge.k_dis1-nc 2.2656mm measurement are carried forward from docs/evidence/2026-08-12-hv-hv-creepage-determination.md (PR #1081, branch docs/recover-standards-primary-text) and docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md (PR #1084, branch feat/hv-hv-creepage-enforcement) -- neither is on main; both read first-hand this session, not re-derived. Heatsink co-location composition (Sec 5) borrows packages/temper-placer/src/temper_placer/placer/cp_sat/heatsink_colocation.py from origin/feat/igbt-heatsink-colocation @ 30ccf6ae5 (PR #1082) for a one-off, uncommitted evidence run -- that file is NOT part of this PR's diff. -->

# The tank-node creepage requirement is now a placement constraint. It rejects the committed board (14 real component pairs, two nearly touching at 0.4mm) and it still solves with the isolation barrier's all 8 isolators intact -- but it does NOT, and cannot, reject the DRC's own headline pair, because that pair is a routed trace, not a component.

**Verdict, up front.**

1. **What was built.** `packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py` generates one HARD `separated` constraint (`min_distance_mm=10.0`, the PD3/as-built figure) per (tank-node component, other-HighVoltage component) pair -- **168 pairs** between the 4 components on `tank.c_tank1-p2` (`C25`, `C26`, `C27`, `R30`) and the 42 other components carrying a `HighVoltage`-classified net. No new wire type: `separated` is already registered in both the OR-Tools handler (`handlers/separated.py`) and the Pumpkin engine (`main.rs:308`). Exposed opt-in as `solve_placement(tank_creepage={"margin_mm": 10.0})`, the same shape `isolation_barrier` and (unmerged) `heatsink_colocation` use.

2. **What it guarantees, precisely.** `separated` bounds *component bounding boxes*, not copper. Reusing `domain_clearance.py`'s proven lemma (box-to-box Chebyshev separation at margin M implies every pad-copper point of A is >= M from every pad-copper point of B, given the box-containment invariant `_calculate_footprint_bounds` already establishes), this constraint guarantees: **every pad of every tank-node component is >= 10.0mm (straight-line) from every pad of every other classified-HV component's own footprint.** On a flat board surface with no intervening slot that is the same quantity kicad-cli's creepage check measures for a genuine pad-to-pad pair.

3. **What it does NOT guarantee -- measured, not asserted.** The DRC violation that motivated this work (`docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md` Sec 5.1) is **C25 pad 2 vs a routed TRACK of `discharge.k_dis1-nc`, 2.2656mm**. That track is not a component. Measured directly: the box-to-box gap between C25 and `K2` (the nearest `discharge.k_dis1-nc`-owning component) is **already 10.8mm** on the committed board -- it clears this constraint's own 10.0mm bound with no solver help at all. The trace swings close to C25 on its way somewhere else, a routing-stage degree of freedom no placement-time, component-box constraint can see or bound. This is not a defect in the encoding; it is the honest boundary of what a placement constraint, built from `separated`, can promise (AGENTS.md R24's "classified approximation error").

4. **What it DOES reject.** 14 of the 168 real component pairs on the committed board have a box-to-box gap under 10.0mm today -- headlined by `C25<->RV1` and `C27<->U5` at **0.4mm**, bodies nearly touching. The Pumpkin engine confirms this at the solver level: pinning the committed placement with the constraint active reports `infeasible`; the identical pin without it reports `optimal`. Sec 3.

5. **It still solves.** With the mains<->SELV isolation barrier and all 8 committed-board isolators intact (`C6, K1, K2, K3, PS1, T1, U3, U7` -- none relaxed), adding the 168-pair tank-creepage constraint at 10.0mm solves **optimal in 1.29s** (Pumpkin solver time), up from 0.84s without it. Composed additionally with PR #1082's (unmerged) heatsink co-location constraint, the three-way model still solves **optimal in 1.16s**, with 0 tank-creepage violations and all 8 isolators still unrelaxed. Sec 4-5.

6. **DRC comparison: partially outstanding, and the reason is stated rather than skipped.** kicad-cli 10.0.5 *is* available this session (checked first, per instruction) and was used for board-containment verification (PASS, 169/527 pads inside the outline). The creepage-rule-*specific* comparison against 10.0mm is outstanding because the `.kicad_dru` rule that measures it (PR #1084's `HighVoltageTank functional creepage`) is not on `main` or this branch -- kicad-cli's default ruleset does not check HV<->HV creepage at all without it (confirmed: `creepage` does not appear as a violation category in either DRC run below). A full place+route cycle was not run either (Sec 6 explains why it would not have closed this gap anyway). Sec 6.

---

## 1. What was encoded, and which groups

**Group A ("tank refs"), measured from the board (`pcb/temper.kicad_pcb`, read-only):** every component with a pad on `tank.c_tank1-p2` --

| Ref | Other net | Footprint |
|---|---|---|
| `C25` | `SW_NODE` | `temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal` |
| `C26` | `SW_NODE` | same |
| `C27` | `SW_NODE` | same |
| `R30` | `tank-out` | `lib:LitzPad_15A` |

**Group B ("other HV refs"), 42 components:** every OTHER component with a pad on any of the 16 nets `design_rules.TEMPER_NET_ASSIGNMENTS` classifies `"HighVoltage"` -- the exact classification `docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md` Sec 1.1 uses for its own DRU rule's B-side (`B.NetClass == 'HighVoltage'`), so this module protects the same population that rule protects, at component-box granularity instead of copper granularity. Includes the discharge relay net's owning components (`K2`, `R12`, `R19`), the DC bus caps, the CMC winding taps, and 36 others.

**168 pairs = 4 x 42.** Group-A components are excluded from Group B *by construction* (`other_hv_refs(netlist, tank_refs)` subtracts `tank_refs`) -- without the exclusion, C25/C26/C27/R30 would appear on both sides of their own pairs (all four also carry a second `HighVoltage`-classified net) and the tank capacitor bank would be forced >=10mm from itself, fighting the electrical design rather than protecting it.

**Margin: 10.0mm (PD3), not 6.3mm (PD2), per instruction.** PD2 is conditional on a sealed compartment that does not exist on this board (`docs/evidence/2026-08-11-pd2-decision-record.md`); PD3 governs as-built. Both constants are in the module (`HV_TANK_CREEPAGE_PD2_MM` / `HV_TANK_CREEPAGE_PD3_MM`) so a caller can select either; `DEFAULT_TANK_CREEPAGE_MM = HV_TANK_CREEPAGE_PD3_MM`.

**What this cannot fix even in principle: R30's own two pads.** R30 pad 1 (`tank.c_tank1-p2`) and pad 2 (`tank-out`) sit 5.0mm apart against the same requirement (`2026-08-12-hv-hv-creepage-enforcement.md` Sec 5.1) -- a real, second violation the DRU rule found, and an INTRA-footprint one. Every one of a component's own pads moves as one rigid unit under placement; no `SeparatedConstraint` can separate a two-pin part from itself (`domain_clearance.py`'s documented limitation, carried over unchanged, not re-derived). `find_tank_self_pairs()` names all four tank refs explicitly (each also carries a second HV net) and `add_tank_creepage_to_model` logs a `WARNING` naming them on every call, rather than leaving the gap silent.

**Reuse, not a new type.** `separated` is registered in both backends already:

| Backend | Location |
|---|---|
| Pumpkin | `docs/evidence/2026-08-07-pumpkin-engine/src/main.rs:308` |
| OR-Tools | `handlers/separated.py::encode_separated`, dispatched via `ConstraintType.SEPARATED` |

`add_tank_creepage_to_model` calls the registered OR-Tools handler directly (`encode_separated(constraint, model.component_map, model, ctx=None)` -- `ctx` is never touched because every `a`/`b` here is a literal ref already present in `components`, and `resolve_refs` returns on that branch before reading `ctx`). The Pumpkin path emits the identical `{"type": "separated", "a": ..., "b": ..., "min_distance_mm": ...}` dicts `tank_creepage_wire_constraints()` builds. Pumpkin `exit(2)`s on an unregistered constraint type while OR-Tools warns and continues -- reusing an already-dual-registered type means neither backend is silently under-constrained, and the pinned engine binary needed no rebuild (verified below, unchanged).

---

## 2. What it guarantees vs. what creepage measures -- the conservative-bound argument (AGENTS.md R24)

`domain_clearance.py`'s module docstring (unrelated feature, same board, same `separated` handler) already proves the load-bearing lemma: for two components A, B, if the encoding is SAT at margin M via (say) the "A left of B" branch, then for **every** point `p_a` in A's box and `p_b` in B's box, `p_b.x - p_a.x >= M`, hence `Euclidean(p_a, p_b) >= M`. This holds for every point, not just centers -- so it holds for every pad-copper point, *provided* the box actually contains every pad the component places. `_calculate_footprint_bounds` is constructed (and proven, `test_bounds_computed_in_placement_frame_not_raw_anchor`) to guarantee exactly that containment.

**Consequence for this constraint:** SAT at 10.0mm implies straight-line pad-to-pad distance >= 10.0mm between every pad of a tank-node component and every pad of the paired other-HV component. On a flat, unobstructed board surface (no slot or groove between the two points), a straight line is already the shortest path *along the surface* -- so this is the same quantity kicad-cli's creepage check reports for a genuine pad-to-pad pair.

**Where the guarantee stops, quantified:**

| Quantity | What it measures | Value for C25 <-> discharge.k_dis1-nc |
|---|---|---:|
| This constraint's guarantee | box(C25) <-> box(K2), nearest owning component | measured 10.8mm (already clears 10.0mm) |
| kicad-cli's creepage check | C25 pad 2 copper <-> nearest `discharge.k_dis1-nc` copper (a routed track) | **2.2656mm** (PR #1084 Sec 5.1) |

The gap between 10.8mm and 2.2656mm is not encoding slop -- it is a different quantity entirely. The router places traces in a pipeline stage *after* placement, with its own degrees of freedom this constraint has no visibility into; a trace can and does route close to a pad whose owning components are all comfortably far apart. **This constraint is a conservative proxy for pad-to-pad creepage between two components' own footprints. It is silent -- correctly, not by omission -- on pad-to-routed-copper creepage, which needs a routing-aware keepout, not a placement constraint.** Nothing here claims otherwise; the module docstring states this in the same terms.

---

## 3. Proof it rejects the current placement

### 3.1 Component-box violations on the committed board, measured directly

Read straight off `pcb/temper.kicad_pcb` (no solve), using the same box geometry the encoder uses (`comp.bounds`, swapped on odd rotation, centered at `initial_position`):

**At the PD3 figure this constraint enforces (10.0mm): 14 of 168 pairs violate.**

```
C25   <-> RV1    gap=  0.4000mm   w1_1
C27   <-> U5     gap=  0.4000mm   +170V_BUS, SW_NODE, hb.power_loop.q_high-g
C26   <-> D5     gap=  3.5600mm   SW_NODE
R30   <-> R23    gap=  4.0000mm   hb.power_loop.q_high-g
C26   <-> C2     gap=  5.9949mm   +170V_BUS
R30   <-> F1     gap=  6.0000mm   w1_1
C26   <-> R14    gap=  6.0000mm   discharge.k_dis2-nc
C26   <-> R23    gap=  6.0000mm   hb.power_loop.q_high-g
C27   <-> R8     gap=  6.0000mm   zcd
C26   <-> C24    gap=  6.1000mm   +170V_BUS, DC_BUS_RTN
R30   <-> R20    gap=  6.6600mm   discharge.k_dis2-nc
R30   <-> T1     gap=  8.0000mm   tank-out
C25   <-> L1     gap=  8.3800mm   w1_1, w1_2
C27   <-> K1     gap=  9.8100mm   power_in.ntc-no, w1_2
```

At the looser PD2 figure (6.3mm), the same top 10 of these violate (`C25<->RV1` and `C27<->U5` at 0.4mm remain the worst two either way).

**None of these is the DRC's own named pair** (`C25<->discharge.k_dis1-nc`, a track). `C25<->K2` (10.8mm), `C25<->R12` (39.13mm), `C25<->R19` (91.48mm) -- the three `discharge.k_dis1-nc`-owning components -- all clear 10.0mm already, consistent with Sec 2's finding.

### 3.2 Solver-level proof (Pumpkin, not just a pure-Python checker)

`docs/evidence/scripts/2026-08-12-tank-creepage-pumpkin-run.py --pin-current`: pins all 46 relevant refs (4 tank + 42 other-HV) to their committed `(position, rotation)`, in a model carrying ONLY the tank-creepage constraint (no barrier, no netclass/courtyard base) -- isolating this constraint as the one doing the rejecting.

```
[engine] pumpkin_engine sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e ...
committed placement, WITHOUT tank-creepage constraint -> optimal
committed placement, WITH tank-creepage constraint    -> infeasible
VERDICT: the tank-creepage constraint rejects the committed placement
```

The two solves differ by exactly this constraint. `optimal` -> `infeasible` is the solver-level confirmation of Sec 3.1's 14 measured violations.

---

## 4. Does the model still solve, with the isolation barrier intact?

Yes. Engine pin verified first:

```
$ uv run --no-sync python scripts/verify_pumpkin_engine.py
pumpkin_engine identity gate: VERIFIED -- sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e
source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd
```

Board `152x234mm`, 169 components, tau=0.4mm. Base: 9,714 netclass + 6,282 courtyard = 15,996 SEPARATED constraints. Barrier: PD2/8.0mm, horizontal, corridor Y `[113.0, 121.0]`, hv_only=43, selv_only=106, isolators=8, unclassified=12.

**Premise check (per task instruction): all 8 committed-board isolators, none relaxed.** `--relax U6` (the harness's inherited default from the heatsink evidence run) is a no-op here: the derived isolator set is `C6, K1, K2, K3, PS1, T1, U3, U7` -- `U6` is not in it. This matches `docs/evidence/scripts/2026-08-12-heatsink-colocation-pumpkin-run.py`'s own finding that `U6` is an isolator only on the *reconciled* 168-component board, not the committed one. **No isolator was relaxed in any run below.**

| Run | status | solver time | wall |
|---|---|---:|---:|
| barrier only, no tank-creepage constraint | optimal | 844.5ms | 0.99s |
| + tank-creepage, 10.0mm (168 constraints) | optimal | 1291.2ms | 1.47s |

**The baseline row is the point, same as PR #1082's finding for the heatsink constraint.** A fresh solve WITHOUT this constraint, run cleanly with the barrier active, immediately reproduces the same failure mode -- 24 fresh component pairs land under 10.0mm (headlined by `C27<->D5` and `C27<->R24` at 0.4mm, different pairs than the committed board's but the same qualitative outcome). The model had nothing in it that would prevent this before; now it does.

**Post-solve check on the 10.0mm run:** `check_tank_creepage_separation` against the solved placement finds 0 real violations across all 168 pairs. One pair (`C27<->R23`) reports `gap=10.0000mm` at 4-decimal display precision from the engine's rounded JSON output; recomputed from the underlying values it is `9.999999999999993mm` -- floating-point noise from 2-decimal position serialization, not a real shortfall. The solver enforces the bound in exact integer centi-mm units (`units_per_mm=100`), so the true encoded constraint has no such ambiguity.

**Where the tank components land** (barrier + tank-creepage @10.0mm, normalized frame, origin (20,20) subtracted):

| Ref | Position | Rotation |
|---|---|---|
| `C25` | (124.00, 22.05) | 270deg |
| `C26` | (100.44, 31.45) | 270deg |
| `C27` | (77.03, 22.05) | 270deg |
| `R30` | (92.90, 69.50) | 90deg |

---

## 5. Composition with PR #1082's heatsink constraint

Per task instruction ("ideally compose... ; if infeasible, report it"). `heatsink_colocation.py` is **not part of this PR** -- borrowed for one uncommitted evidence run from `origin/feat/igbt-heatsink-colocation @ 30ccf6ae5` (a scratch copy, imported by path, never added to this branch).

```
[base] 9714 netclass + 6282 courtyard = 15996
[barrier] isolators: ['C6', 'K1', 'K2', 'K3', 'PS1', 'T1', 'U3', 'U7']
[tank] 168 tank-creepage constraints at 10.0mm
[heatsink] 4 heatsink co-location constraints (common rot=1)
-> status=optimal wall=1.32s solver=1157.75ms
   U5: (140.29, 10.73) rot=1 (90deg)
   U6: (139.59, 27.6) rot=1 (90deg)
   C25: (76.93, 38.51) rot=2 (180deg)
   C26: (110.38, 22.05) rot=1 (90deg)
   C27: (76.62, 14.71) rot=2 (180deg)
   R30: (110.54, 66.8) rot=3 (270deg)
   tank-creepage post-check: 0 violation(s)
```

**All three constraint sets compose cleanly**: isolation barrier (8 isolators, none relaxed) + tank-creepage (168 pairs @10.0mm, 0 post-solve violations) + heatsink co-location (U5/U6 co-located, common rotation) solve `optimal` in 1.16s solver time -- faster than the tank-creepage-only run in Sec 4, well within noise for a model this size. No infeasibility to report; the task's fallback ("if the two together go infeasible... report it") does not apply here.

---

## 6. DRC comparison

**Board containment: PASS.** The Sec 4 solve (10.0mm, all 169 components), written to a scratch copy via `write_placements_to_pcb` (never touching `pcb/temper.kicad_pcb`):

```
$ uv run --no-sync python scripts/check_board_containment.py --board <scratch>/temper.kicad_pcb
outline (Edge.Cuts) bounds: (20.00, 20.00) - (172.00, 254.00) mm
checked: 169 footprints, 527 pads
Board containment: PASS -- all copper inside the board outline
```

**kicad-cli DRC (default ruleset, `--all-track-errors --format json`, MaximumThreads=1): run, but NOT a meaningful creepage comparison, and that is stated rather than left implicit.**

| | committed board (unchanged) | Sec 4 solve, written back, **not re-routed** |
|---|---:|---:|
| total violations | 1627 | 1799 |
| `creepage` category | **absent from the ruleset** | **absent from the ruleset** |

Two reasons this table is not the comparison the task is really asking for:

1. **`creepage` does not appear as a violation category in either run.** `pcb/temper.kicad_pro` (unmodified, per task instruction) has no `HighVoltageTank` netclass or `.kicad_dru` HV<->HV rule -- that is PR #1084's change, on branch `feat/hv-hv-creepage-enforcement`, not on `main` or this branch. kicad-cli's default DRC genuinely does not check HV<->HV creepage at all without it, so no number in this table can confirm or deny an improvement in the 6.3/10.0mm figure this constraint targets. **This specific comparison is the outstanding item** -- not because kicad-cli is unavailable (it is; checked first, per instruction), but because the rule that would measure it is out of this branch's scope.
2. **The Sec 4 solve was written back WITHOUT re-routing.** Every existing trace stays attached to its old two-terminal geometry while ~all 169 footprints move to new positions -- the delta (1627 -> 1799, dominated by `clearance`, `silk_overlap`/`silk_over_copper`, `shorting_items`, categories identical between the two runs at the type level) is the expected artifact of any placement-only change without a re-route, not a signal about this constraint specifically. A full route (per PR #1082's own precedent, ~7 minutes wall) would still not populate the `creepage` category without PR #1084's rule, so it was not run -- it would cost real time and not close the actual gap.

**What Sec 3-5 already establish stands on its own**: the constraint's own guarantee (component-box pad-to-pad separation) is verified directly against solved coordinates (`check_tank_creepage_separation`, 0 violations at 10.0mm across all three solves), independent of whichever DRC ruleset happens to be wired into `pcb/temper.kicad_pro` on a given branch.

---

## 7. Reproduction

```bash
# 1. Verify the engine pin (stop if this fails)
uv run --no-sync python scripts/verify_pumpkin_engine.py

# 2. Group membership + committed-board violation table
uv run --no-sync python -c "
import sys; sys.path.insert(0, 'packages/temper-placer/src')
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.tank_creepage import (
    tank_creepage_pairs, check_tank_creepage_separation, HV_TANK_CREEPAGE_PD3_MM)
netlist = parse_kicad_pcb(Path('pcb/temper.kicad_pcb'), normalize=False).netlist
positions = {c.ref: tuple(c.initial_position) for c in netlist.components}
rotations = {c.ref: int(c.initial_rotation or 0) for c in netlist.components}
sizes = {c.ref: tuple(c.bounds) for c in netlist.components}
pairs = tank_creepage_pairs(netlist)
v = check_tank_creepage_separation(positions, rotations, sizes, pairs, margin_mm=HV_TANK_CREEPAGE_PD3_MM)
print(len(v), 'of', len(pairs), 'pairs violate at 10.0mm')
"

# 3. Solver-level rejection proof
PYTHONPATH=packages/temper-placer/src python3 \
    docs/evidence/scripts/2026-08-12-tank-creepage-pumpkin-run.py --pin-current --timeout-ms 30000

# 4. Fresh solve with the isolation barrier, all 8 isolators
PYTHONPATH=packages/temper-placer/src python3 \
    docs/evidence/scripts/2026-08-12-tank-creepage-pumpkin-run.py --margin-mm 10.0 --timeout-ms 60000

# 5. Unit tests
uv run --no-sync python -m pytest packages/temper-placer/tests/placer/cp_sat/test_tank_creepage.py -q
```

---

## Files

- Constraint: `packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py`
- Wired into the production entry point: `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py` (`solve_placement(tank_creepage=...)`, `CpSatPlacementResult.tank_creepage_report`)
- Tests: `packages/temper-placer/tests/placer/cp_sat/test_tank_creepage.py`
- Evidence harness: `docs/evidence/scripts/2026-08-12-tank-creepage-pumpkin-run.py`
- This document: `docs/evidence/2026-08-12-tank-creepage-placement.md`
- Carried forward, not re-derived: `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` (PR #1081, Table 18 / 6.3mm-10.0mm), `docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md` (PR #1084, the 2.2656mm measurement and group scoping), `docs/evidence/2026-08-11-pd2-decision-record.md` (PD3 governs as-built), `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py` (the box-containment soundness lemma, reused not re-derived)
- Borrowed for Sec 5 only, NOT part of this PR: `packages/temper-placer/src/temper_placer/placer/cp_sat/heatsink_colocation.py` from `origin/feat/igbt-heatsink-colocation @ 30ccf6ae5` (PR #1082)
- **Not modified:** `pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`, `power_pcb_dataset/drc_ceiling.json`, `elec/**`
