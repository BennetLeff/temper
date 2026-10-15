# Candidate 33 adoption checks: DECISIONS 39 "Before adoption" items 1–3 (2026-10-14)

Six-layer board native21s33 (board 710c0a45, `runs-native21/s33/b2`) against the four-layer board of record s32
(2fb346dc, `runs-native21/s32/b2`).

| item | method | s32 (4 L) | s33 (6 L) | verdict |
|---|---|---|---|---|
| 1. commutation loops | FEM (round-17 coarse reference) | not run | not run | **DEFERRED**: six layers not adopted on price. FEM only if a stack-envelope route (JLC "No requirement" stack) is reopened. Campaign prepared, mesh gates pass (§1) |
| 2. ZVS dead-time margin, leg A (worst corner, 340 ns) | D2 as-built deck + board sw-node C (screen) | 151.1 ns; ZVS from 11.65 A | 150.6 ns; ZVS from 11.73 A | PASS, change −0.5 ns / +0.08 A |
| 2. same, leg B | as above | 149.6 ns; ZVS from 11.73 A | 150.0 ns; ZVS from 11.65 A | PASS, change +0.4 ns / −0.08 A |
| 2. board worst leg (340 ns) | | 149.6 ns (leg B) | 150.0 ns (leg B) | not worse |
| 3. `emi_min_margin_dB` | s19b model, unmodified, on each board's copper | 10.5 dB (10.479) | 10.5 dB (10.479) | PASS, no change |

"Screen" means the plane-pair capacitance or inductance formula. "FEM" means the Elmer / Hypre AMS extraction.
No FEM was run for this note.

## 1. FEM commutation-loop re-extraction: DEFERRED

**Status.** Not run. The JLC Gerber quote (2026-10-14) prices six layers on the pinned JLC061622-1080A at $19.11
per board at 500, including a $1,466.39 stackup fee ($2.93 per board). Four layers on the pinned JLC041622-7628
cost $17.28. That trips DECISIONS 39's reversal clause, so six layers is not adopted as modelled. FEM is needed
only if a stack-envelope route (JLC "No requirement" stack) is reopened. The remote box (tailscale `earth`) was also
offline at the time (last seen 4 days earlier; ssh timed out). The Mac's Elmer (`~/.local/opt/elmer-26.2.1`) has
no Hypre, so the qualified solver is not available locally either.

**What the reference is.** Round 17's 37.6 / 24.5 nH (FINDINGS M11) are the coarse reference (h 1 mm arch, 1.0 mm
edges, 10 mm crop, 12 ranks; `results/matrices/leg{A,B}21-h1-e1p0-m10-n21.matrix.txt`). They were extracted on
**native-21's first routed copper, board 76ec8cca** (`round17/native21-setup/README.md`), not on s32. A
like-for-like comparison therefore needs s32 re-extracted with the same scripts as well as s33.
`fem/fem_compare.py` recomputes the parallel loop, (L11·L22 − M12²)/(L11 + L22 − 2·M12), from those matrices:
37.57 / 24.53 nH. It asserts that value before it reads any new matrix.

**Prepared and checked locally (no solve), so the campaign can be run as is:**
- **The mesher was four-layer only.** `mesh25d_hybrid.py` had a fixed four-layer z table, so on the s33 export
  (which has In3 / In4 copper) it would have dropped In3 / In4 silently and put In1 / In2 at four-layer depths.
  Changes:
  - **Stack override.** `MESH_STACKUP=<stackup json>` now builds the table from the stack file. Unset, the
    committed table is used unchanged. `native-21/stackup.json` reproduces that table exactly
    (`round17/scripts/test_stack_layers.py`, 4 pass).
  - **Unknown layers refused.** Loop-net copper on a layer outside the stack is now refused, not dropped.
  - **`port_loops.py`.** Its closure-end window (z 1.5625–2.4) follows the same stack top.
  - **Neutrality.** gmsh is not deterministic run to run (three default meshes of s32 leg A: 3,436,972 / 3,437,341 /
    3,438,693 tets), so neutrality rests on the table test, not on .msh hashes.
- **Closures re-anchored** (`fem/closures_for_board.py`). Each closure end is moved to its named pad in the target
  export, and the net is checked.
  - Control: on 76ec8cca it reproduces round 17's committed closures exactly (`closures-stage1-moves.json`).
  - On s32 and s33, only R5's ends move: R5.1 (39.135, 10.12) → (38.5, 10.0) and R5.4 (37.865, 15.08) → (38.5, 15.2).
  - The s32 and s33 closures are identical.
- **Mesh gates** (`fem/mesh_gates.sh`, campaign.py's exact mesher arguments for `--cases 1:1.0`; `fem/mesh-gates/`).
  All four meshes pass: no inner far-field triangles, zero port leakage, every port a closed loop, and every closure
  end on the main body.

  | mesh | tets | gates |
  |---|---|---|
  | s32 A21 | 3,437,341 | pass |
  | s32 B21 | 3,305,580 | pass |
  | s33 A21 (six-layer stack) | 3,895,197 | pass |
  | s33 B21 (six-layer stack) | 3,402,535 | pass |
- **Run (if reopened):** `fem/chain_c33.sh` (sync steps in its header): s32 then s33, legs A21 / B21, one case at a
  time with the field-file cleanup. Then `fem_compare.py s32-A=… s32-B=… s33-A=… s33-B=…`. If either s33 loop is
  above s32's, re-run `round17/d2/f6_legs.py` (F6 at −1.6 V, PMEG, 27 / 100 / 150 °C, decision and startup cases)
  on the new matrices.

**Screen only (c33 PHASE-A, not FEM).** The plane-pair term falls by 1.28 nH (leg A) and 0.74 nH (leg B). The
F-to-plane via terms fall from 0.240 / 0.715 to 0.092 / 0.355 nH. Package, ESL and pin terms are not modelled.

## 2. Switch-node capacitance against the ZVS dead-time margin: PASS

**How the project judges ZVS** (round17/d2 `grid.py`, c25-driver `d2_c25.py`). It uses the D2 single-transition deck,
whose criterion is that the incoming device's die VDS is ≤ 5 % of VBUS at its on command.
- The as-built deck is c25 `results/dtband/F6.cir` (sha 55a2058f…): F6, PMEG, −1.6 V off level, 2EDR8259 output
  resistances, Rg 8.2 Ω.
- It runs on the native-21 leg matrices legA21 / legB21-h0-s9b2-n21.
- **The deck has no board switch-node capacitance.** It has the 1 nF snubber per FET (C12 / C13 / C19 / C20,
  1 kV) and the vendor model's Coss, but no copper term.

**Method** (`zvs/zvs_node_c.py`).
- **Board capacitance added.** The plane-pair screen's sw-node capacitance (`../screens/loop-screen-b2.json`) is
  added as two capacitors, split by the plane each pour faces: sw → 0 (hv_ret / leg_ret) and sw → bus (bus_p).

  | leg | s32 | s33 |
  |---|---|---|
  | A (sw_a) | 78.15 + 12.96 pF | 140.04 + 14.89 pF |
  | B (sw_b) | 2.23 + 209.47 pF | 0 + 157.01 pF |
- **What is measured.** Each case measures t_trans: from the outgoing off command to the incoming die VDS reaching
  5 % VBUS. The transition finishes before the on command, so it does not depend on the dead time. Each case runs
  at DT 600 ns, and margin(DT) = DT − t_trans.
- **ZVS current threshold.** The IL at which t_trans equals the dead time, interpolated in 1/IL from a 3–37 A sweep.
  Every worst-corner threshold is bracketed.
- **Corners.** Both legs and both directions; buses 170 / 198 / 280 V; 2EDR typical output at 27 / 100 / 150 °C,
  and its weak and strong corners at 27 / 150 °C; ESL 10 nH.
- **Dead time.** Two lower edges are checked: the 2EDR window at 49.9 kΩ, 408.3 ns (c25 `dt_window.json`), and the
  audit window's 340 ns. The lower one is the worst case.
- **Size.** 3 boards × 2016 / 3 runs each (no board C, s32, s33).
- **Control.** With the board capacitors at ~0 pF, the deck reproduces 24 committed c25 dtband S1 rows to 0.5 mV
  (`zvs/repro/repro.json`).

**Results** (`zvs/summary.json`). S1 at 37 A has ZVS in 42 / 42 cases per board and leg (c25 dtband's S1 conditions plus 170 V,
with board C added). The worst corner is the 2EDR weak output at 150 °C and 280 V on every board.

| | no board C | s32 | s33 | s33 − s32 |
|---|---|---|---|---|
| leg A worst t_trans at 37 A | 188.20 ns | 188.90 ns | 189.39 ns | +0.49 ns |
| leg A margin at 340 / 408 ns | 151.8 / 220.1 | 151.1 / 219.4 | 150.6 / 218.9 | −0.5 |
| leg A ZVS current threshold at 340 / 408 ns | 11.56 / 9.04 A | 11.65 / 9.11 A | 11.73 / 9.16 A | +0.08 / +0.05 A |
| leg B worst t_trans at 37 A | 188.92 ns | 190.36 ns | 189.98 ns | −0.38 ns |
| leg B margin at 340 / 408 ns | 151.1 / 219.4 | 149.6 / 217.9 | 150.0 / 218.3 | +0.4 |
| leg B ZVS current threshold at 340 / 408 ns | 11.47 / 9.00 A | 11.73 / 9.14 A | 11.65 / 9.09 A | −0.08 / −0.05 A |

- **Sensitivity.** About 7 ps per pF (leg A: +64 pF → +0.49 ns; leg B: −55 pF → −0.38 ns). The board's
  copper is about 3–5 % of the node's charge.
- **One abort out of 2016.** s33 leg B, 100 °C, 198 V, 25 A, dir 0, at t = 1 µs: the load-ramp end, before any
  switching. ngspice reported "timestep too small" at xqh.x1.ox. At a 0.1 ns step it completes: t_trans 206.5 ns,
  ZVS (`zvs/rerun.json`; s32 at that corner: 206.9 ns). It is not on a 37 A row or a threshold bracket.
- **Below about 11.5 A**, S1 is not soft-switched at the 340 ns edge on any board. Light-load ZVS is not claimed
  (c25 README; there is no S3 deck).
- **Verdict.**
  - Leg A loses 0.5 ns of a 151 ns margin; leg B gains 0.4 ns. The board's worst-leg margin goes from 149.6 to 150.0 ns.
  - Read literally, item 39's "ZVS margin … worse than s32's" holds for leg A alone, by 0.3 % of the margin and
    0.08 A of threshold. It does not hold for the board's worst leg.
  - **Not a reason against six layers.**
- **The capacitance is a screen.** The pF values are parallel-plate overlap only: no fringe, no sw tracks. Even
  doubling the screen's s33 − s32 change moves the margin by about 1 ns.

## 3. EMI confirmation: PASS, unchanged

**Method** (`emi/emi_board.py`). The **unmodified** `07-conducted-emi/s19b/emi_s19b.py` is imported, with three
module attributes redirected: the copper dump, the output directory, and the B.Cu fringe depth (s19b hard-codes
1.6 mm). The committed s19b results are not touched. `emi_min_margin_dB` uses scorecard.py's definition: the minimum
margin_dB over `scenarios.nominal`.
- **Control.** On s19b's own copper at 1.6 mm, results.json is equal to the committed one, 10.479 dB
  (`emi/s19b-control/provenance.json`).
- **Depth basis** (DECISIONS 38): the B.Cu underside below the F.Cu top. Four layers: 1.633 mm. Six layers:
  1.658 mm.

| run | B depth | Laplace grid | CPOURA / CPOURB | emi_min_margin_dB |
|---|---|---|---|---|
| s32 at s19b's depth (`emi/s32-d1p600`) | 1.600 | 0.5 mm | 1.4225 / 2.0737 pF | 10.479 |
| **s32, stack** (`emi/s32-d1p633`) | 1.633 | 0.5 mm | 1.4225 / 2.0737 pF | **10.479** |
| **s33, stack** (`emi/s33-d1p658`) | 1.658 | 0.5 mm | 1.4224 / 2.0737 pF | **10.479** |
| s32, stack, fine grid | 1.633 | 0.1 mm | 1.4282 / 2.0759 pF | 10.479 |
| s33, stack, fine grid | 1.658 | 0.1 mm | 1.4271 / 2.0753 pF | 10.479 |

- **The pours are unchanged.** The outer sw pours are the same on s19b, s32 and s33 to 0.05 mm²: sw_a F.Cu
  1702.3 + 24.3 mm² and B.Cu 201.8 mm²; sw_b B.Cu 3307.9 mm². s33 is s32's frozen copper.
- **The depth is below the model's grid.** On the default 0.5 mm grid all three depths fall on z −1.5 mm. On the
  0.1 mm grid they separate (−1.6 / −1.7 mm): the B.Cu fringe moves by 0.5 % (1.619 → 1.611e-14 F/mm) and the
  margin by 0.0001 dB.
- **Not modelled here.** The model has no inner-layer term, so the sw_a capacitance to In1 (screen 78 → 140 pF)
  does not enter it. That capacitance is to hv_ret, which is not PE. Through the bus capacitors it is a differential
  path, not a common-mode one.
- **Not rechecked.** The scorecard's committed 10.5 dB (s19b) stands for both boards.

## Files
- `emi/`: `emi_board.py`, per-run `provenance.json` and the copper summary. Full `results.json` only for the two
  stack-basis runs; the others keep provenance, whose margin is the scorecard number.
- `zvs/`: `zvs_node_c.py` (modes `repro`, `run`, `rerun`), `F6zvs.cir`, `results.json`, `summary.json`,
  `repro/`, `rerun.json`, and the aborted run's log. Vendor models are not committed: c25's hashes are asserted, and
  the files are copied into the ignored `validation-plan/sim-kit/models/vendor/`.
- `fem/`: `closures_for_board.py`, `closures-leg{A,B}-{s32,s33}.json`, the moves files, `mesh_gates.sh`,
  `mesh-gates/`, `chain_c33.sh`, `fem_compare.py`.
- `round17/scripts/`: `mesh25d_hybrid.py` and `port_loops.py` (the `MESH_STACKUP` hook and the unknown-layer
  refusal), and `test_stack_layers.py`.

Reproduce (Mac):

```
python3 -I emi/emi_board.py --copper runs-native21/s33/b2/copper-dump.json --b-depth-mm 1.658 --tag s33 --out OUT
python3 -I zvs/zvs_node_c.py repro && python3 -I zvs/zvs_node_c.py run --workers 8 && python3 -I zvs/zvs_node_c.py rerun
bash fem/mesh_gates.sh s33 A21 runs-native21/s33/b2/native21-all-copper.json.gz SCRATCH
```
