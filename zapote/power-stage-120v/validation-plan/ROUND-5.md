# Validation round 5: board inductance, then the switching verdict

Execution update, 2026-09-28: see the [round-5 handback](../validation-results/round5-coordination/README.md). D1 remains software-blocked, the bench procedure is delivered, both raw-evidence releases are published, and the related-board rebuild premise was withdrawn for the audited candidate hashes. The procedures below remain the acceptance contract; a blocked report does not complete their dependent solves.

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules (§2), [ROUND-4.md](ROUND-4.md) and the
[round-4 execution record](../validation-results/round4-coordination/README.md)
first. Written 2026-09-28 against PR #1615 at the commit that adds this file.

## What changed since round 4

- **The board is native-17** (`native-17/verification/README.md`). Native-15
  had 23 plated pads without outer lands; native-17 fixes that with a
  deliberate pad-layer policy and five small reroutes. Placement is
  unchanged.
- **Copper export:** use `tools/export_power_copper.py` (`FlashLayer`-aware,
  refuses a PTH pad without outer lands). The round-4 D1 exporter is pinned
  to native-15 and must not be used as is.
- **Task 04 is re-extracted on native-17**
  (`validation-results/04-board-current-thermal/round4/README.md`). SW_B's
  resistance rose about 8 % (peak 12.6 A/mm); other nets are within 1.7 %.
- **A candidate fab package exists**
  (`validation-results/08-manufacturing-package/native-17/README.md`), with an
  independent Gerber review. Not released.

The owner's round-4 decisions stand: A and D proceed, C is evaluation only,
B is held.

## The critical path

D1 blocks everything else in the switching work: D2's diagnostic
counterfactuals, the board-inductance C1 rerun, and C2's final loss
comparison. Round 4 tried a whole-leg 0.125 mm field solve and stopped on
meshing: 1,327 narrow links and eight barrel spokes dropped, crop edges
cutting planes, about a million nodes at 0.0625 mm. **This round narrows the
question** to what the switching deck actually needs.

```
R5-D1  commutation-cell and gate-loop extraction (native-17)
   |
   +--> R5-D2  724 V diagnosis on extracted L, then the switching grid
   +--> R5-C1  ZVS thresholds on extracted L
             |
             +--> R5-C2  final 348/450 ns loss comparison

R5-B   bench plan (parallel; no dependency)
```

Run R5-D1 and R5-B in parallel; the rest follows D1.

---

## R5-D1: extract only what the deck needs

> **Superseded 2026-09-28 by [D1-FEM.md](D1-FEM.md).** The FastHenry
> raster method below stopped twice on meshing. D1-FEM extracts the same
> inductances from KiCad's 3-D copper with a conformal finite-element
> mesh (gmsh) and solver (Palace), with component-located ports. Kept for
> the record.

**Deliverable:** for each leg, a coupled R+jωL matrix over **eight ports**
(corrected 2026-09-28: the first version said six and listed one gate loop,
but each leg has a high-side and a low-side gate circuit):
1. local bus capacitors → high-side drain. The two local capacitors
   (C38/C39 or C40/C41) are one port with their BUS_P pads tied, since they
   are in parallel; report the current split between them from the solve;
2. high-side source → low-side drain (switch node);
3. low-side source → R5 (with the shared return);
4. R5 → local capacitor return pads (tied as in port 1);
5. high-side gate drive: driver output → gate resistor → gate pin;
6. high-side gate return: source pin → driver high-side ground;
7. low-side gate drive: driver output → gate resistor → gate pin;
8. low-side gate return: source pin → driver low-side ground.

Gate resistors, MOSFET packages, capacitors and drivers are external
components: the copper model ends at their pads and must not short them.

Deliver it as `spice_coupled.inc` (L and K statements) plus the matrix JSON,
at 1, 10 and 30 MHz.

**Method.**

1. **Input.** Export native-17 with `tools/export_power_copper.py`
   (all power and gate nets). Record the board hash. Build FastHenry2 from
   the recipe in `round3-coordination/decision-review/README.md`, and use
   **`sigma=5.8e4` with `.units mm`** (round 4 found the 1000× unit error).
   Rerun the round-4 wire and plane-pair fixtures and require them to pass
   before anything else.
2. **Mesh without dropping connections.** Use a native-contained segment
   mesh as round 4 did, with one change: **no copper link may be omitted**.
   Where a fitted width falls below the solver's practical minimum, give it
   a *narrower* width than the copper (at least 20 µm, recorded). This tends
   to raise an isolated self inductance, but it does **not** bound every
   coupled term or the switching waveform (round-5 review), so report every
   such link and treat the result as an approximation. Every emitted element must lie inside native copper; check it.
3. **Crop by convergence, not by eye.** Start with a crop equal to the
   bounding box of the six ports' pads plus a margin M. Solve at
   M = 5, 10, 20 and 40 mm. Stop when every self term and every mutual term
   above 10 % of its self changes by ≤ 5 % between the last two margins.
   Where a crop cuts a plane, attach the cut edge to the local return with a
   port-free boundary (open circuit); report which planes are cut at the
   accepted margin.
4. **Two meshes and thickness.** At the accepted crop, solve two in-plane
   pitches (0.125 and 0.0625 mm, or two that fit memory; at least 2× apart)
   with `nhinc` 1 and 3. The skin depth at 10–30 MHz is 12–21 µm, less than
   the 61–70 µm copper, so `nhinc=1` alone doesn't qualify R. Report the
   change; accept L within 5 %.
5. **Matrix checks.** Symmetry (reciprocity), positive semidefinite R and L,
   passivity across the three frequencies, and the package inductances *not*
   included (the Infineon model has them).
6. **Local-capacitor ESL** stays a separate labelled assumption: the 5–20 nH
   bracket, not part of the copper matrix.

**If step 3 or 4 doesn't converge within memory,** hand back the smallest
converged quantity you have: the loop inductance of port 1+2+3+4 in series
(the commutation loop) and of 5+6 (the gate loop), with the mutual between
them. Even without the full matrix, that pair decides whether false
turn-on is plausible.

**Hand back:** the export and its hash, the FastHenry decks and logs
(raw, ignored by git), the crop and mesh convergence tables, the matrix JSON,
`spice_coupled.inc`, and a README that maps each port to a deck node.

## R5-D2: the 724 V event, then the grid (needs R5-D1)

Follow ROUND-4 §3 D2 exactly, with R5-D1's include. Step 1 decides the cause:
rerun the round-3 case with both devices' currents saved, then one change at
a time (ideal off-gate; common-source mutual removed; local-capacitor ESL
at 5 and 20 nH; the round-3 scalar values to reproduce 723.9 V). Then run the
grid and report every criterion (S1–S4) for the extracted matrix.

Round 4 found the vendor model's internal channel probe includes avalanche
current, and that a delayed finite gate clamp lowered the peak to 598 V. Keep
both in mind when reading the currents.

## R5-C1 and R5-C2 (need R5-D1)

- **C1:** rerun the ZVS-threshold search on both legs with the extracted
  matrix, at the six dead-time corners and the extended low-bus grid
  (ROUND-4 §4 C1). Report the change from the reference-inductance values.
- **C2:** redo the loss comparison with C1's board thresholds, and complete
  what round 4 left conditional: hot (125 °C) diode drop and recovery from the
  datasheet, prior-cycle recovery, low-bus events, and dead-time current
  reversal. Give the verdict round 4 couldn't: does 450 ns lower the total
  switching plus diode loss at every tolerance corner?

## R5-B: bench plan for the first boards (parallel)

The switching questions end on the bench, not in simulation (D1 README,
open item 4). Write the procedure now so the first boards are tested the
same way the models were. Deliver `validation-plan/BENCH-SWITCHING.md`:

1. **Double-pulse test** on one leg, low-side and high-side, at 50, 100 and
   170 V bus, currents up to 37 A, with the board's own 1 nF snubbers and
   3.9 Ω gate resistors fitted.
2. **What to measure, simultaneously:** VDS at the device legs (low-
   inductance probe tip), VGS at the gate and source pins, drain current
   (a Rogowski coil or a current shunt in series), and the bus at C38–C41.
   State probe bandwidth and the tip adapter.
3. **What to compare:** the VDS peak against the 520 V criterion scaled to
   the test voltage, off-device VGS against 3.0 V, and the switching edges
   against R5-D2's waveforms at the same voltage and current.
4. **Knobs, in order, if the off-device gate crosses 3 V or VDS overshoots:**
   gate resistor values (turn-off and turn-on); snubber capacitance; then the
   layout options R5-D2 identifies. List which parts can be changed on the
   assembled board.
5. **Safety:** the procedure runs from a current-limited bench supply
   with the bus bleed verified, a discharge check before handling, and no
   mains connection until the stage has passed at 170 V from the bench
   supply.

## Owner items (not for workers)

| # | Item | Why now |
| --- | --- | --- |
| O4 | JLCPCB: CTI ≥ 175 V guaranteed on the order? | Fab release gate |
| O9 | Qualify LCSC candidates or consignment for 57 BOM lines | [50 identity candidates](../validation-results/round5-coordination/sourcing/README.md); stock, package/assembly qualification and F1 clips remain open |
| O10 | Published: [round 3](../validation-results/round3-coordination/raw-evidence/README.md) and [round 4](../validation-results/round4-coordination/raw-evidence/README.md) | Restore 3,327 / 12,027 verified files from GitHub evidence releases |
| O11 | Blanket rebuild recommendation withdrawn for current RTD, thermal-sense and current-sense candidate hashes | [Native census](../validation-results/round5-coordination/related-board-outer-lands.json): zero missing outer lands; audit any other intended revision separately |
| O1–O3 | Pad and heatsink, CDE capacitor rating, TDK ESL | Still open from round 3 |

## Hand back (every item)

The master plan §4 report template, with the native-17 board hash; scripts
runnable as committed; raw runs under `outputs/runs/` or `extraction/`
(ignored by git) with a manifest; a status line for master plan §5; and for
anything blocked, the missing input and the cheapest way to get it.
