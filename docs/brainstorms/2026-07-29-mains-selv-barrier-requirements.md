---
date: 2026-07-29
topic: mains-selv-barrier
focus: Consolidate the 76 REQ-SAFE-01 clearance/creepage violations and the missing MAINS_SELV_ISOLATION_BARRIER keepout into one requirements document a human can design against -- fix-class every violation, and test (not assume) whether the keepout resolves the clearance failures.
origin: Task brief citing packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance (76 violations) and scripts/check_isolation_keepout.py (0 keepout zones); prior work docs/evidence/2026-07-28-barrier-constrained-placement.md, docs/evidence/2026-07-29-hv-footprint-copper-shorts-requirements.md
status: research-only, no code/board changes made (pcb/temper.kicad_pcb and pcb/libs/** are read-only for this task); every violation fix-classified, relationship between (a) and (b) tested and answered NO with a CP-SAT infeasibility proof, human-blocking items enumerated
actors: test_clearance.py (REQ-SAFE-01), scripts/check_isolation_keepout.py, scripts/check_copper_net_consistency.py, elec/domain_manifest.yaml, temper_placer.requirements.validators.clearance, temper_placer.placer.cp_sat.isolation_barrier, PCB footprint author (human)
---

# Requirements: Mains<->SELV Barrier -- Consolidated Violation Picture and Fix Classification

## Summary

76 REQ-SAFE-01 violations (33 unique component pairs) and the missing
`MAINS_SELV_ISOLATION_BARRIER` keepout are **the same underlying defect
measured two ways**, and the relationship between them is now proven, not
assumed: **placing the required 8mm keepout would NOT resolve the 33
violating pairs.** A rigorous prior investigation
(`docs/evidence/2026-07-28-barrier-constrained-placement.md`) already ran
CP-SAT with the barrier as a hard constraint and got `INFEASIBLE` in ~23s --
not a placement-search failure, a **proof**: several isolator components'
own package geometry cannot reach 8mm HV-to-SELV pad separation on *any*
placement or rotation. This document reproduces that isolator-infeasibility
finding fresh, against today's exact (not the prior investigation's cruder)
pad-geometry model, and independently confirms it by convex-hull analysis:
HV-domain and SELV-domain pads currently occupy **96-98% overlapping**
regions of the board (84/97 HV pads sit inside the SELV pads' convex hull;
191/221 SELV pads sit inside the HV pads' convex hull) -- there is no line,
of any orientation, that separates the two domains on the current placement.

Of the 33 violating pairs:

- **21 pairs (64%)** are genuine placement violations between two ordinarily
  movable components -- fix-class **Placement**, with direct precedent that
  a domain-clearance-aware CP-SAT re-solve already took an equivalent
  boundary set from a nonzero violation count to zero once before.
- **5 pairs (15%, all "intra-footprint")** are the isolator components
  themselves (`C6` Y-cap, `K2`/`K3` discharge relays, `U3` optocoupler, `U7`
  gate driver) -- their own primary-to-secondary pad spacing is short of
  8.0mm by a fixed, placement-independent amount (0.75mm to 4.8mm). Fix-class
  **Footprint / component selection**, and this is also exactly the set that
  makes the keepout barrier provably impossible to draw.
- **7 pairs (21%, all involving `C27`)** are not a real HV/SELV boundary
  crossing at all: `C27`'s compiled-netlist net assignment
  (`SW_NODE`/`tank.c_tank1-p2`, a tank capacitor) does not match its actual
  PCB pad nets (`I_SENSE`/`gnd`, `ct_sense.c_filter`) -- a reference-
  designator/netlist-sync defect already caught by a separate, pre-existing,
  currently-failing gate (`scripts/check_copper_net_consistency.py`, 10
  pad-mismatch violations). Fix-class **Reclassification-equivalent**,
  blocked on that resync, not on this task.

**What's blocked on a human**, precisely: (1) source or approve replacement
parts/footprints for 4 of the 5 footprint-intrinsic isolators (a wider-pitch
Y-capacitor, a reinforced-isolation relay family for the two discharge
relays, and applying an already-specified-but-unapplied 400-mil DIP-6
footprint swap for the optocoupler); (2) decide the UCC21550 gate-driver
footprint's fate (short by only 0.75mm -- may be fixable within the package
family, needs datasheet-level review, not a guess); (3) fix the
`check_copper_net_consistency.py` resync defect before the 7 `C27` pairs can
be re-evaluated at all -- and note the real tank capacitor (netlist ref
`C27`) has **no verified physical position** on the board right now, an
unsafe-direction coverage gap, not merely an unsafe-looking one; (4) approve
a fresh CP-SAT domain-clearance re-solve (copper-aware, not the stale
origin-based model) for the 21 genuine placement pairs; (5) resolve a
requirement-figure grounding gap between `HIGH_VOLTAGE_CLEARANCE_SPEC.md`'s
own tables and the actual governing code constants (see Sec 4).

---

## Problem Frame

### Reproduction

```
git fetch origin && git checkout -b <branch> origin/main
uv sync --all-packages
make netlist            # produces elec/build/default.net; test skips without it
uv run pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s
```

Run fresh for this document (2026-07-29, clean `origin/main` worktree,
`a247227d` base): **76 violations across 33 pairs, 11 of 76 records
intra-footprint** -- matches the task brief's count exactly. Coverage:
158/168 components classified (94.0%), 54/162 compiled nets. Creepage model:
board has 0 `Edge.Cuts` cutouts, so creepage == clearance exactly (no
slot-aware surface pathing needed). `scripts/check_isolation_keepout.py`
independently confirms 0 keepout zones on the board, 97 HV pads / 221 SELV
pads classified from `elec/domain_manifest.yaml`.

### On the "56 -> 76" note in the task brief

Verified, not assumed: the count moved 56 (pre-`2382e168`) -> 76
(post-`2382e168`) because `2382e168` ("fix(io): rotate pad bodies with their
footprint") corrected pad body rotation, which the clearance checker's own
copper-to-copper measurement (landed `2026-07-28`, see
`docs/evidence/2026-07-28-clearance-copper-to-copper.md`) depends on for
every non-axis-aligned pad. `pcb/temper.kicad_pcb` did not change between
those two measurements in any way that added real risk -- the checker
simply stopped under-measuring rotated pads. **This is a truth correction,
confirmed**, in the same direction the checker's own history already
established (origin-to-origin -> copper-to-copper was the same kind of
correction, 9 records -> 56 records, for the identical reason: the old model
was optimistic in the unsafe direction).

### Board state at time of measurement

Both hand-built-footprint fixes from `docs/evidence/2026-07-29-intra-
component-shorts-root-cause.md` are **already applied to the committed
board** (verified by reading the board file directly, not assumed from the
evidence docs): `K1` pads 13/14 are on `layers "F.Fab"` (zero copper, matching
`docs/evidence/2026-07-29-board-regeneration-corrected-footprints.md`'s
"60 -> 0 intra-component shorts" regeneration), and `R30` pad 2 sits at
`(13 0)` -- the corrected 13.0mm pitch, not the old defective 5.0mm. `K1`
therefore no longer appears anywhere in the 33-pair table below: with its
contact pads carrying no copper, it has no HV-classified *copper* for the
checker to measure. This is why the isolator set this document's Sec 3
analyzes is 5 components, not the 8 (`C6, K1, K2, K3, PS1, T1, U3, U7`)
enumerated by the prior barrier investigation -- `K1` electrically dropped
out and `PS1`/`T1` independently pass (see Sec 3).

---

## 1. The Complete Violation Table

76 records over 33 pairs, exactly as reproduced above (`DC_BUS<->LV_CONTROL`
boundary throughout -- this is the only boundary the legacy 10-net check set
exercises; see the fixture's own docstring on why that set is not yet the
full 54-net manifest). `insul` = insulation type checked (`basic`/
`reinforced`); a pair can and does appear multiple times (once per
applicable insulation type x metric combination it fails).

```
pair             boundary               insul       metric        meas     req    short  model
----------------------------------------------------------------------------------------------
C17<->R32        DC_BUS<->LV_CONTROL    reinforced  creepage     0.905     8.0    7.095  copper; unbroken-surface (exact: geodesic == straight line)
C27<->D1         DC_BUS<->LV_CONTROL    reinforced  creepage     1.505     8.0    6.495  copper; unbroken-surface (exact: geodesic == straight line)
C27<->R25        DC_BUS<->LV_CONTROL    reinforced  creepage     1.510     8.0    6.490  copper; unbroken-surface (exact: geodesic == straight line)
C27<->R66        DC_BUS<->LV_CONTROL    reinforced  creepage     1.530     8.0    6.470  copper; unbroken-surface (exact: geodesic == straight line)
C22<->L2         DC_BUS<->LV_CONTROL    reinforced  creepage     1.969     8.0    6.031  copper; unbroken-surface (exact: geodesic == straight line)
C27<->C15        DC_BUS<->LV_CONTROL    reinforced  creepage     1.992     8.0    6.008  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R32        DC_BUS<->LV_CONTROL    reinforced  creepage     2.612     8.0    5.388  copper; unbroken-surface (exact: geodesic == straight line)
C17<->R32        DC_BUS<->LV_CONTROL    reinforced  clearance    0.905     6.0    5.095  copper
R30<->R1         DC_BUS<->LV_CONTROL    reinforced  creepage     2.953     8.0    5.047  copper; unbroken-surface (exact: geodesic == straight line)
C6 (intra)       DC_BUS<->LV_CONTROL    reinforced  creepage     3.200     8.0    4.800  copper; unbroken-surface (exact: geodesic == straight line)
C17<->R26        DC_BUS<->LV_CONTROL    reinforced  creepage     3.325     8.0    4.675  copper; unbroken-surface (exact: geodesic == straight line)
C27<->D1         DC_BUS<->LV_CONTROL    reinforced  clearance    1.505     6.0    4.495  copper
C27<->R25        DC_BUS<->LV_CONTROL    reinforced  clearance    1.510     6.0    4.490  copper
C27<->R66        DC_BUS<->LV_CONTROL    reinforced  clearance    1.530     6.0    4.470  copper
K2 (intra)       DC_BUS<->LV_CONTROL    reinforced  creepage     3.559     8.0    4.441  copper; unbroken-surface (exact: geodesic == straight line)
K3 (intra)       DC_BUS<->LV_CONTROL    reinforced  creepage     3.559     8.0    4.441  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R54        DC_BUS<->LV_CONTROL    reinforced  creepage     3.666     8.0    4.334  copper; unbroken-surface (exact: geodesic == straight line)
R30<->U13        DC_BUS<->LV_CONTROL    reinforced  creepage     3.794     8.0    4.206  copper; unbroken-surface (exact: geodesic == straight line)
C22<->L2         DC_BUS<->LV_CONTROL    reinforced  clearance    1.969     6.0    4.031  copper
C27<->C15        DC_BUS<->LV_CONTROL    reinforced  clearance    1.992     6.0    4.008  copper
C17<->U13        DC_BUS<->LV_CONTROL    reinforced  creepage     4.023     8.0    3.977  copper; unbroken-surface (exact: geodesic == straight line)
C22<->U15        DC_BUS<->LV_CONTROL    reinforced  creepage     4.594     8.0    3.406  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R32        DC_BUS<->LV_CONTROL    reinforced  clearance    2.612     6.0    3.388  copper
R30<->R73        DC_BUS<->LV_CONTROL    reinforced  creepage     4.616     8.0    3.384  copper; unbroken-surface (exact: geodesic == straight line)
C17<->R32        DC_BUS<->LV_CONTROL    basic       creepage     0.905     4.0    3.095  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R1         DC_BUS<->LV_CONTROL    reinforced  clearance    2.953     6.0    3.047  copper
C6 (intra)       DC_BUS<->LV_CONTROL    reinforced  clearance    3.200     6.0    2.800  copper
C22<->C16        DC_BUS<->LV_CONTROL    reinforced  creepage     5.293     8.0    2.707  copper; unbroken-surface (exact: geodesic == straight line)
C17<->R26        DC_BUS<->LV_CONTROL    reinforced  clearance    3.325     6.0    2.675  copper
R30<->R46        DC_BUS<->LV_CONTROL    reinforced  creepage     5.406     8.0    2.594  copper; unbroken-surface (exact: geodesic == straight line)
C27<->D1         DC_BUS<->LV_CONTROL    basic       creepage     1.505     4.0    2.495  copper; unbroken-surface (exact: geodesic == straight line)
C27<->R25        DC_BUS<->LV_CONTROL    basic       creepage     1.510     4.0    2.490  copper; unbroken-surface (exact: geodesic == straight line)
C27<->R66        DC_BUS<->LV_CONTROL    basic       creepage     1.530     4.0    2.470  copper; unbroken-surface (exact: geodesic == straight line)
K2 (intra)       DC_BUS<->LV_CONTROL    reinforced  clearance    3.559     6.0    2.441  copper
K3 (intra)       DC_BUS<->LV_CONTROL    reinforced  clearance    3.559     6.0    2.441  copper
R30<->R54        DC_BUS<->LV_CONTROL    reinforced  clearance    3.666     6.0    2.334  copper
R30<->U13        DC_BUS<->LV_CONTROL    reinforced  clearance    3.794     6.0    2.206  copper
R30<->R26        DC_BUS<->LV_CONTROL    reinforced  creepage     5.835     8.0    2.165  copper; unbroken-surface (exact: geodesic == straight line)
C27<->TP2        DC_BUS<->LV_CONTROL    reinforced  creepage     5.895     8.0    2.105  copper; unbroken-surface (exact: geodesic == straight line)
C17<->R32        DC_BUS<->LV_CONTROL    basic       clearance    0.905     3.0    2.095  copper
C22<->L2         DC_BUS<->LV_CONTROL    basic       creepage     1.969     4.0    2.031  copper; unbroken-surface (exact: geodesic == straight line)
C27<->C15        DC_BUS<->LV_CONTROL    basic       creepage     1.992     4.0    2.008  copper; unbroken-surface (exact: geodesic == straight line)
U3 (intra)       DC_BUS<->LV_CONTROL    reinforced  creepage     6.020     8.0    1.980  copper; unbroken-surface (exact: geodesic == straight line)
C17<->U13        DC_BUS<->LV_CONTROL    reinforced  clearance    4.023     6.0    1.977  copper
C27<->C35        DC_BUS<->LV_CONTROL    reinforced  creepage     6.068     8.0    1.932  copper; unbroken-surface (exact: geodesic == straight line)
C27<->C34        DC_BUS<->LV_CONTROL    reinforced  creepage     6.330     8.0    1.670  copper; unbroken-surface (exact: geodesic == straight line)
R30<->C30        DC_BUS<->LV_CONTROL    reinforced  creepage     6.367     8.0    1.633  copper; unbroken-surface (exact: geodesic == straight line)
C27<->D1         DC_BUS<->LV_CONTROL    basic       clearance    1.505     3.0    1.495  copper
C27<->R25        DC_BUS<->LV_CONTROL    basic       clearance    1.510     3.0    1.490  copper
C17<->R73        DC_BUS<->LV_CONTROL    reinforced  creepage     6.515     8.0    1.485  copper; unbroken-surface (exact: geodesic == straight line)
C27<->R66        DC_BUS<->LV_CONTROL    basic       clearance    1.530     3.0    1.470  copper
C22<->U15        DC_BUS<->LV_CONTROL    reinforced  clearance    4.594     6.0    1.406  copper
R30<->R32        DC_BUS<->LV_CONTROL    basic       creepage     2.612     4.0    1.388  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R73        DC_BUS<->LV_CONTROL    reinforced  clearance    4.616     6.0    1.384  copper
C17<->R54        DC_BUS<->LV_CONTROL    reinforced  creepage     6.657     8.0    1.343  copper; unbroken-surface (exact: geodesic == straight line)
C22<->R77        DC_BUS<->LV_CONTROL    reinforced  creepage     6.721     8.0    1.279  copper; unbroken-surface (exact: geodesic == straight line)
C22<->C12        DC_BUS<->LV_CONTROL    reinforced  creepage     6.742     8.0    1.258  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R1         DC_BUS<->LV_CONTROL    basic       creepage     2.953     4.0    1.047  copper; unbroken-surface (exact: geodesic == straight line)
C22<->L2         DC_BUS<->LV_CONTROL    basic       clearance    1.969     3.0    1.031  copper
C27<->C15        DC_BUS<->LV_CONTROL    basic       clearance    1.992     3.0    1.008  copper
C6 (intra)       DC_BUS<->LV_CONTROL    basic       creepage     3.200     4.0    0.800  copper; unbroken-surface (exact: geodesic == straight line)
U7 (intra)       DC_BUS<->LV_CONTROL    reinforced  creepage     7.250     8.0    0.750  copper; unbroken-surface (exact: geodesic == straight line)
C22<->C16        DC_BUS<->LV_CONTROL    reinforced  clearance    5.293     6.0    0.707  copper
C17<->R26        DC_BUS<->LV_CONTROL    basic       creepage     3.325     4.0    0.675  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R46        DC_BUS<->LV_CONTROL    reinforced  clearance    5.406     6.0    0.594  copper
K2 (intra)       DC_BUS<->LV_CONTROL    basic       creepage     3.559     4.0    0.441  copper; unbroken-surface (exact: geodesic == straight line)
K3 (intra)       DC_BUS<->LV_CONTROL    basic       creepage     3.559     4.0    0.441  copper; unbroken-surface (exact: geodesic == straight line)
C22<->C37        DC_BUS<->LV_CONTROL    reinforced  creepage     7.599     8.0    0.401  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R32        DC_BUS<->LV_CONTROL    basic       clearance    2.612     3.0    0.388  copper
R30<->R54        DC_BUS<->LV_CONTROL    basic       creepage     3.666     4.0    0.334  copper; unbroken-surface (exact: geodesic == straight line)
R30<->U13        DC_BUS<->LV_CONTROL    basic       creepage     3.794     4.0    0.206  copper; unbroken-surface (exact: geodesic == straight line)
R30<->R26        DC_BUS<->LV_CONTROL    reinforced  clearance    5.835     6.0    0.165  copper
T1<->U27         DC_BUS<->LV_CONTROL    reinforced  creepage     7.850     8.0    0.150  copper; unbroken-surface (exact: geodesic == straight line)
C23<->U27        DC_BUS<->LV_CONTROL    reinforced  creepage     7.895     8.0    0.105  copper; unbroken-surface (exact: geodesic == straight line)
C27<->TP2        DC_BUS<->LV_CONTROL    reinforced  clearance    5.895     6.0    0.105  copper
R30<->R1         DC_BUS<->LV_CONTROL    basic       clearance    2.953     3.0    0.047  copper
```

Closest-copper identification per pair (which two pads the measurement is
actually between -- net name in parentheses):

```
C17.2(hb.gate_hs.driver-p2) <-> R32.1(+3V3)          C27.2(gnd) <-> D1.1(power_in.bypass_relay-coil1)
C27.1(I_SENSE) <-> R25.1(PWM_HS)                     C27.2(gnd) <-> R66.1(+3V3)
C22.2(hb.gate_hs.driver-p2) <-> L2.2(+3V3)           C27.2(gnd) <-> C15.1(+15V)
R30.1(tank.c_tank1-p2) <-> R32.1(+3V3)               R30.1(tank.c_tank1-p2) <-> R1.1(+15V)
C6.1(PWR_RTN) <-> C6.2(gnd)                          C17.1(hb.gate_hs.driver-p1-1) <-> R26.1(PWM_LS)
K2.1(PWR_RTN) <-> K2.2(discharge.k_dis1-coil1)       K3.1(DC_BUS_RTN) <-> K3.2(discharge.k_dis2-coil1)
R30.1(tank.c_tank1-p2) <-> R54.2(gnd)                R30.1(tank.c_tank1-p2) <-> U13.3(gnd)
C17.1(hb.gate_hs.driver-p1-1) <-> U13.3(gnd)         C22.1(hb.gate_hs.driver-p1-1) <-> U15.4(RTD_HW_FAULT)
R30.2(tank-out) <-> R73.1(+3V3)                      C22.1(hb.gate_hs.driver-p1-1) <-> C16.1(+15V)
R30.2(tank-out) <-> R46.2(gnd)                       R30.1(tank.c_tank1-p2) <-> R26.1(PWM_LS)
C27.1(I_SENSE) <-> TP2.1(SHUTDOWN)                   U3.2(PWR_RTN) <-> U3.5(gnd)
C27.2(gnd) <-> C35.2(gnd)                            C27.2(gnd) <-> C34.2(gnd)
R30.1(tank.c_tank1-p2) <-> C30.2(gnd)                C17.2(hb.gate_hs.driver-p2) <-> R73.1(+3V3)
C17.1(hb.gate_hs.driver-p1-1) <-> R54.2(gnd)         C22.1(hb.gate_hs.driver-p1-1) <-> R77.1(+3V3)
C22.1(hb.gate_hs.driver-p1-1) <-> C12.1(+3V3)        U7.9(DC_BUS_RTN) <-> U7.8(+3V3)
C22.1(hb.gate_hs.driver-p1-1) <-> C37.2(gnd)         T1.2(PWR_RTN) <-> U27.4(PWM_HS)
C23.1(+15V_LS) <-> U27.38(V_BUS_SENSE)
```

33 unique pairs = 5 intra-footprint (`C6, K2, K3, U3, U7`, 11 records) + 28
inter-component (65 records). Of the 28 inter-component pairs, 7 involve
`C27`.

---

## 2. Fix-Class Classification (every pair)

### Group A -- Reclassification-equivalent (7 pairs): all `C27<->X`

`C27<->D1`, `C27<->R25`, `C27<->R66`, `C27<->C15`, `C27<->TP2`, `C27<->C35`,
`C27<->C34`.

**Not a genuine HV/SELV boundary crossing as currently measured.** Verified
directly, not inferred: `elec/build/default.net` assigns ref `C27` to nets
`SW_NODE` (pin 1) and `tank.c_tank1-p2` (pin 2) -- both declared HV, this is
one leg of the resonant-tank capacitor bank (`ResonantTank.c_tank1`). The
**committed PCB's own footprint** labeled `C27`, however
(`pcb/temper.kicad_pcb`), has `Sheetpath "ct_sense.c_filter"`, a 0603
current-sense filter cap, with pads on nets `I_SENSE` (unclassified) and
`gnd` (declared SELV) -- neither of which is `SW_NODE` or
`tank.c_tank1-p2`. These are two different physical components sharing one
reference designator between the compiled netlist and the board: a
resync/reference-designator drift, the same class of defect
`docs/evidence/2026-07-27-pcb-netlist-resync.md` previously fixed for 78/149
refs.

This is **not a new finding invented for this document** -- it is already
caught by a dedicated, pre-existing, currently-failing gate:

```
uv run --no-sync python3 scripts/check_copper_net_consistency.py
=== VIOLATIONS: 10 ===
  [pad-mismatch]
    C27 pad 1: board has net 'I_SENSE', compiled netlist declares 'SW_NODE' for this pin
    C27 pad 2: board has net 'gnd', compiled netlist declares 'tank.c_tank1-p2' for this pin
    C28 pad 1: board has net 'vcc', compiled netlist declares 'I_SENSE' for this pin
    C29 pad 1: board has net '+3V3', compiled netlist declares 'vcc' for this pin
    C30 pad 1: board has net 'vcc', compiled netlist declares '+3V3' for this pin
    C33 pad 1: board has net '+3V3', compiled netlist declares 'vcc' for this pin
    C34 pad 1: board has net 'vcc', compiled netlist declares '+3V3' for this pin
    C35 pad 1: board has net 'V_BUS_SENSE', compiled netlist declares 'vcc' for this pin
    C36 pad 1: board has net '+3V3', compiled netlist declares 'V_BUS_SENSE' for this pin
    C39 pad 1: board has net 'en', compiled netlist declares '+3V3' for this pin
```

(Gate introduced by commit `af91e10a`, "add copper-net consistency gate" --
already on `origin/main`, already failing there; this document did not
introduce it. Reproduce on a clean checkout to confirm before attributing.)

This is a chain of small decoupling/filter caps (`C27`-`C39`) whose ref
designators appear to have drifted by roughly one position relative to the
compiled netlist across a run of components in the CT-sense/OVP-ADC-filter
area. Of the 10 mismatched refs, only `C27`'s mismatch changes its **domain**
classification (`DC_BUS` -> effectively unclassified/`SELV`, once corrected)
-- `C30`, `C34`, `C35` each have a second pad whose net (`gnd`) is unaffected
by the mismatch, so their SELV classification is domain-invariant despite
also appearing in the pad-mismatch list (verified by cross-checking both
pads of each, not assumed from the single flagged pad).

**Practical effect on this document's 33-pair table**: the 7 `C27<->X`
records are measuring the real, physical location of an SELV decoupling
capacitor against its SELV/unclassified-net neighbors -- correctly measuring
*something*, but not what the checker's `DC_BUS<->LV_CONTROL` label claims.
**Worse, in the unsafe direction**: the *real* tank capacitor that the
compiled netlist calls `C27` (400V-rated, per `elec/domain_manifest.yaml`'s
own tank-net commentary) has **no reference designator on the board whose
copper the checker is actually measuring** -- its true clearance to nearby
SELV components is currently unverified by this test, not merely
mismeasured. This is a coverage gap, not a false alarm.

**Fix-class: Reclassification-equivalent, blocked on `scripts/
check_copper_net_consistency.py`'s resync defect (`scripts/
resync_pcb_netlist.py` or equivalent), not on this task.** These 7 pairs
must be re-evaluated from scratch after the resync lands -- they cannot be
placement- or footprint-fixed as currently labeled, because the label itself
is wrong.

### Group B -- Footprint / component selection (5 pairs, all intra-footprint)

`C6 (intra)`, `K2 (intra)`, `K3 (intra)`, `U3 (intra)`, `U7 (intra)`.

Every one of these is a component `elec/domain_manifest.yaml` explicitly
declares an **isolator** (primary/secondary or coil/contacts pin groups on
one physical part), verified against the board's own footprint identity for
each (not assumed from the ref alone):

| Ref | Footprint (from `pcb/temper.kicad_pcb`) | Manifest role | Measured (reinforced creepage) | Required | Deficit |
|---|---|---|---:|---:|---:|
| `C6` | `Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm` | `power_in.y_cap_pe`, Y1 EMI/PE-bonding cap | 3.200mm | 8.0mm | 4.800mm |
| `K2` | `Relay_THT:Relay_SPDT_Omron-G5LE-1` | `discharge.k_dis1` | 3.559mm | 8.0mm | 4.441mm |
| `K3` | `Relay_THT:Relay_SPDT_Omron-G5LE-1` | `discharge.k_dis2` | 3.559mm | 8.0mm | 4.441mm |
| `U3` | `Package_DIP:DIP-6_W7.62mm` (300-mil) | `power_in.zcd_opto`, H11L1 | 6.020mm | 8.0mm | 1.980mm |
| `U7` | `lib:SOIC16W_Isolated` | `hb.gate_hs.driver`, UCC21550 | 7.250mm | 8.0mm | 0.750mm |

These figures are **not placement-dependent** -- confirmed by a rigorous
prior investigation (`docs/evidence/2026-07-28-barrier-constrained-placement.md`)
that ran CP-SAT with an 8.5mm barrier corridor as a **hard constraint**
across all 4 axis-aligned rotations and got `INFEASIBLE` in ~23s, with the
solver's own `SufficientAssumptionsForInfeasibility` naming
`isolator_straddle_C6` and the accompanying by-hand per-isolator analysis
independently confirming `C6/K2/K3/U3/U7` (of 8 isolators checked then) as
each, individually, geometrically incapable of the required separation --
*regardless of where they are placed or how they are rotated*. That
investigation used a cruder pad-radius model
(`max(pad.size.X, pad.size.Y)/2`, a full bounding circle) than the one this
test and the current `scripts/check_isolation_keepout.py` both now use
(`pad_bounding_radius`, the exact rotation-invariant circumscribing model
from `docs/evidence/2026-07-28-pad-geometry-model-fix.md`) -- so its exact
mm figures are stale for two of the eight (`K1` since removed from the HV
copper set entirely, see Problem Frame; `T1` the CT, which the exact model
now measures at 9.100mm, clearing 8.0mm -- a real, positive change, not
hidden here). **The `C6/K2/K3/U3/U7` figures above, however, are today's
exact-model numbers, independently reproduced by this document's own fresh
test run** -- the barrier investigation's qualitative conclusion for these
five holds under the current, more precise model, not just the old one.

Per-component fix path (grounded, not invented):

- **`C6`**: footprint's own `descr` in the barrier investigation calls it a
  "Stub for safety capacitor... Created to resolve netlist reference" --
  not a sourced part. A Y1-rated safety capacitor with a wider lead pitch
  (P7.5mm/P10mm packages are common in this exact application) would
  directly close the 4.8mm gap. **Component sourcing decision, not
  invented here.**
- **`K2`/`K3`**: Omron G5LE-1 is a general-purpose PCB relay; its COM-
  contact-to-coil-pin layout is a manufacturer-fixed ~3.5-5mm dimension, not
  independently rated for reinforced isolation. Needs a relay family
  designed for reinforced/safety isolation between coil and contacts (same
  category of fix `HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 9.2 gestures at with
  its "Isolation_barrier" DRU rule, applied here to a relay instead of a
  gate driver). **Component sourcing decision.**
- **`U3`**: the fix is **already specified and already in `elec/src`**, just
  not yet propagated to the board. `elec/src/components.ato:549` already
  declares `footprint = "Package_DIP:DIP-6_W10.16mm"` (400-mil) with
  `mpn = "H11L1TVM"`, sourced and verified per
  `docs/evidence/2026-07-28-tank-cap-and-isolator-footprints.md` ("the
  400-mil one gives 8.560mm"). The committed board still carries the old
  300-mil footprint. **This is a board-regeneration task, not a new design
  decision** -- closing it does not require sourcing anything new.
- **`U7`**: short by only 0.75mm on a footprint already named
  `SOIC16W_Isolated` -- i.e. already a widened variant. Whether this
  specific 0.75mm can be recovered within the same package family (a small
  pad-position adjustment) or requires a different device needs a TI
  UCC21550 datasheet-level layout review (Sec 6.3 of
  `HIGH_VOLTAGE_CLEARANCE_SPEC.md` cites "1.0mm minimum clearance between
  primary and secondary pins" per the datasheet's own Figure 34 -- a
  different metric than this 8.0mm creepage figure, not a substitute for
  it). **Not resolved here — no dimension is invented for it.**

**Fix-class: Footprint / component-selection for all 5.** These are also,
not coincidentally, the components whose infeasibility already proved (Sec
3) that the keepout barrier cannot currently be drawn.

### Group C -- Placement (21 pairs)

`C17<->R32`, `C22<->L2`, `R30<->R32`, `R30<->R1`, `C17<->R26`, `R30<->R54`,
`R30<->U13`, `C17<->U13`, `C22<->U15`, `R30<->R73`, `C22<->C16`,
`R30<->R46`, `R30<->R26`, `R30<->C30`, `C17<->R73`, `C17<->R54`,
`C22<->R77`, `C22<->C12`, `C22<->C37`, `T1<->U27`, `C23<->U27`.

None of these components is a declared isolator, none carries a
manufacturer-fixed spacing constraint, and none is corrupted by the `C27`-
class resync defect (each ref's declared-domain nets were cross-checked
against its actual PCB pad nets for this document; only `C27`'s mismatch
changes a domain verdict -- see Group A). Every pair here is two ordinarily
movable components that are simply too close on the current placement.
Deficits range from trivial (`R30<->R1` basic clearance, 0.047mm short;
`C27<->TP2` reinforced clearance, 0.105mm; `T1<->U27` reinforced creepage,
0.150mm) to substantial (`C17<->R32`, 7.095mm short of reinforced creepage
-- the worst violation on the board).

**Precedent that room exists**: `docs/evidence/2026-07-27-domain-clearance-
constraint.md` and `docs/evidence/2026-07-27-clearance-resolve-full-
coverage.md` document a CP-SAT re-solve, using a domain-clearance constraint
generator (`temper_placer.placer.cp_sat.domain_clearance`) built on this
exact `IEC60335_REQUIREMENTS`/`VoltageDomain` matrix, that took an
equivalent (then narrower, 10-net) violation set from 22 -> 0 (and later a
wider, 47-net set from 17 -> 0), status `optimal`. That re-solve used
origin-to-origin distance, since superseded by the copper-to-copper
measurement that reintroduced these 21 (among the 33) pairs -- the
re-solve's *packing feasibility* is not invalidated by that measurement
change, only its *margin accounting* is: the constraint generator needs to
add each component's own copper-reach as extra margin (or encode pad-to-pad
distance directly) and be re-run. This is a mechanical, previously-
demonstrated-successful operation, not a new capability.

**Fix-class: Placement**, pending a copper-aware re-solve of
`domain_clearance.py`'s constraint generator. Whether every one of these 21
pairs individually clears after such a re-solve is not proven here (that
would require actually running the solver, which this task's read-only
constraint on `pcb/`/`pcb/libs/**` forecloses) -- stated as an explicit
assumption with a falsifier in Sec 5.

---

## 3. The Relationship Between (a) and (b) -- Tested, Not Assumed

**Would placing the required `MAINS_SELV_ISOLATION_BARRIER` keepout resolve
the 33 pairs? No -- for the current placement and current component set, it
cannot be placed at all.**

### 3.1 Prior proof (CP-SAT, hard barrier constraint)

`docs/evidence/2026-07-28-barrier-constrained-placement.md` implemented the
barrier as a hard CP-SAT constraint
(`temper_placer.placer.cp_sat.isolation_barrier`) and ran it against the
real board at 8.5mm corridor width (0.5mm above the gate's 8.0mm minimum, in
the safe direction), both vertical and horizontal orientation:

```
Status: infeasible          (both orientations, ~23.2-23.4s each)
UNSAT core: isolator_straddle_C6
```

Confirmed independent of solver search: a control run at
`corridor_width_mm=1.0` (deliberately below any real safety requirement)
shows `C6/K1/T1/U3/U7` all become feasible at 1mm (their real gaps, ~3-38mm,
clear it trivially) while `K2/K3` remain infeasible even at 1.0mm -- proving
the discharge relays' pinout is a hard, width-independent geometric fact,
not an 8mm-specific artifact.

### 3.2 This document's independent reproduction (fresh, today's exact model)

Group B above independently reproduces the same qualitative conclusion using
today's exact pad-geometry model (not the prior investigation's cruder one):
5 of the current isolator set (`C6, K2, K3, U3, U7`) still cannot reach
8.0mm internal HV-to-SELV separation on their own committed footprint,
by 0.75-4.8mm, on *any* placement (the deficit is a property of the pad
positions relative to the footprint's own origin, invariant under
translation/rotation of the whole footprint). Any single one of these five
already makes a bisecting keepout impossible: a barrier that bisects the
board into exactly two regions (`scripts/check_isolation_keepout.py`'s Check
4) requires every HV pad on one side and every SELV pad on the other: an
isolator whose HV pad and SELV pad sit 3.2-7.25mm apart, both **on the same
physical footprint**, cannot have an 8mm-wide barrier pass between them
without the barrier itself overlapping the footprint (which Check 5, no
copper intrusion, forbids for both the pad and, if traced, its footprint's
courtyard).

### 3.3 Independent geometric corroboration (this document, convex-hull check)

Beyond the isolator-specific proof, this document computed the convex hull
of all 97 HV-classified pads and all 221 SELV-classified pads on the current
placement directly from `pcb/temper.kicad_pcb` and `elec/domain_manifest.yaml`
(script: pad extraction + `shapely` convex hull, reproducible from the
pad-position logic already in `scripts/check_isolation_keepout.py`):

```
HV pads: 97   SELV pads: 221
HV  bounding range:   X [21.45, 170.18]  Y [21.23, 252.48]
SELV bounding range:  X [21.00, 170.68]  Y [21.25, 252.75]
Board outline bbox:   X [20.00, 172.00]  Y [20.00, 254.00]   (152mm x 234mm)

HV convex hull area:    33812.6 mm^2
SELV convex hull area:  32940.5 mm^2
Intersection area:      32465.7 mm^2  (96.0% of HV hull, 98.6% of SELV hull)
HV pads inside SELV convex hull:   84 / 97
SELV pads inside HV convex hull:  191 / 221
```

HV and SELV pads occupy essentially the **entire board footprint**, not two
separable regions -- unlike the aspirational two-column layout
`HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 2.2's ASCII diagram depicts (that
diagram also states a "100mm x 150mm" board; the real board is
152mm x 234mm -- a second, unrelated documentation/reality mismatch, noted
but out of scope to resolve here). No straight line of any orientation
separates the two domains on the current placement; this is consistent
with, not merely alongside, the CP-SAT `INFEASIBLE` proof in Sec 3.1-3.2 --
both are measuring the same underlying fact from different angles.

### 3.4 Verdict

**A keepout resolves zero of the 33 pairs as things stand**, because it
cannot be placed at all without first replacing the isolator components in
Group B. This is the critical finding the task brief asked to check
honestly: **the board needs component/footprint changes and, separately, a
placement re-solve -- not a zone drawn on the existing layout.** Once Group
B's footprint issues are resolved (new parts sourced/applied) and a fresh
copper-aware CP-SAT domain-clearance re-solve (Group C) produces a placement
where HV and SELV components *are* separable, a `isolation_barrier=`-
constrained re-solve (the machinery already exists, per Sec 3.1) becomes the
correct next step to actually draw the keepout -- and, by construction,
would then also resolve every Group C pair simultaneously, since a
bisecting barrier subsumes pairwise domain separation. Group A (the `C27`
resync defect) is orthogonal to all of this -- it must be fixed regardless
of the barrier, or its 7 pairs remain uninterpretable.

---

## 4. Requirement-Figure Grounding

Every figure used above traces to a citation. One genuine gap, surfaced
here rather than silently resolved by picking a number:

- **The governing clearance/creepage figures** (`6.0mm` reinforced
  clearance / `8.0mm` reinforced creepage / `10.0mm` design, at the
  `DC_BUS<->LV_CONTROL` boundary) come from
  `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:180-211`
  (`IEC60335_REQUIREMENTS`), the dict `test_clearance.py` actually enforces
  -- these are the numbers behind every violation in Sec 1.
- **`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`** Sec 4.2/5.2 gives a
  *different* figure for the same boundary at 400V: reinforced clearance
  min **5.0mm** (design 8.0mm), reinforced creepage min **10.0mm** (design
  12.0mm) -- not 6.0/8.0/10.0. `clearance.py`'s `IEC60335_REQUIREMENTS`
  carries no citation comment of its own beyond "IEC 60335-2-6 Requirements
  Matrix," so which of the two is the intended authority, or how they
  should reconcile against IEC 60664-1 Table F.2 at 400V directly, is
  **not resolved by this document** -- flagged for human sign-off (Sec 6),
  not guessed. Both sources agree the boundary needs *reinforced*
  insulation; they disagree on the exact millimeter figure.
- **The 8.0mm keepout width** (`scripts/check_isolation_keepout.py`,
  `MIN_BARRIER_WIDTH_MM`) independently derives to the same **8.0mm** as
  `clearance.py`'s reinforced-creepage figure for this boundary --
  reassuring cross-validation between two independently-derived figures in
  the repo, though the keepout script's own docstring flags its derivation
  as "UNVERIFIED-at-primary" (IEC 60335-1 Table 16 / IEC 60664-1 are
  paywalled; reconstructed from secondary/industry sources), same
  epistemic status `HIGH_VOLTAGE_CLEARANCE_SPEC.md` and
  `elec/domain_manifest.yaml`'s own OVP-01 writeup already carry for their
  figures.
- **Clearance vs. creepage**: kept distinct throughout (Sec 1's table has
  separate `clearance`/`metric` rows). The board has 0 `Edge.Cuts` cutouts
  (confirmed by direct measurement, printed every test run), so creepage
  equals clearance exactly here -- not an approximation, a geometric fact
  for an unbroken surface (the surface geodesic between two coplanar points
  *is* the straight line). This would stop holding the moment an isolation
  slot is milled into the board, which none of this document's
  recommendations require.

---

## Requirements

**Data integrity (blocking, Group A)**
- R1. `scripts/check_copper_net_consistency.py`'s 10 pad-mismatch
  violations (led by `C27`) must be resolved -- via
  `scripts/resync_pcb_netlist.py` or equivalent -- before the 7 `C27<->X`
  clearance records can be re-evaluated. Until then they must not be
  treated as either "fixed" or "confirmed real" placement/footprint
  violations.
- R2. After the resync, the real tank capacitor (netlist ref `C27`,
  `SW_NODE`/`tank.c_tank1-p2`) must be re-verified for HV-to-SELV clearance
  at its correct physical position -- its true separation is currently
  unmeasured, not merely mismeasured.

**Component/footprint sourcing (blocking, Group B)**
- R3. `C6`: source a Y1-rated safety capacitor footprint with lead pitch
  wide enough to clear the governing reinforced-creepage figure (Sec 4) --
  the current footprint is an explicitly-flagged placeholder ("Stub...
  Created to resolve netlist reference"), not a sourced part.
- R4. `K2`/`K3`: source a discharge-relay family independently rated for
  reinforced coil-to-contact isolation, replacing the general-purpose Omron
  G5LE-1. Same part for both (`discharge.k_dis1`/`discharge.k_dis2`).
- R5. `U3`: propagate the already-specified `Package_DIP:DIP-6_W10.16mm`
  / `H11L1TVM` footprint (already in `elec/src/components.ato:549`) into
  `pcb/temper.kicad_pcb`'s embedded footprint copy. No new sourcing
  decision required -- this is a regeneration task.
- R6. `U7`: obtain a TI UCC21550 datasheet-level layout determination on
  whether the existing `SOIC16W_Isolated` footprint family can recover the
  remaining 0.75mm, or whether a different device is required.

**Placement (Group C)**
- R7. Re-run `temper_placer.placer.cp_sat.domain_clearance`'s constraint
  generator with copper-aware margins (accounting for each component's own
  pad extent, not origin-to-origin) against the current 54-net manifest
  classification, and re-solve. Precedent (Sec 2, Group C) that this
  converges to 0 violations on an equivalent boundary set exists; it is not
  guaranteed to converge again under the stricter copper-aware model for
  every one of the 21 pairs (see Dependencies/Assumptions).

**Barrier (subsumes Group C once R3-R6 land)**
- R8. Only after R3-R6 close (isolator components/footprints replaced or
  regenerated) does a `isolation_barrier=`-constrained CP-SAT re-solve
  become worth attempting. Running it earlier reproduces the same
  `INFEASIBLE` result Sec 3.1 already proved.

**Grounding (blocking, Sec 4)**
- R9. Reconcile `clearance.py`'s `IEC60335_REQUIREMENTS` (6.0/8.0/10.0mm)
  against `HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 4.2/5.2 (5.0/10.0/8.0/12.0mm)
  for the `DC_BUS<->LV_CONTROL` reinforced boundary -- determine which is
  authoritative, or derive both from IEC 60664-1 Table F.2 directly, before
  treating either figure as final.

---

## Success Criteria

- A human reading this document can act on R1-R9 without re-deriving any of
  Sec 1-4 from scratch: every violation is fix-classified with its
  reasoning shown, not just listed.
- The relationship between the 76 clearance violations and the missing
  keepout is understood as **proven infeasible-as-is**, not "probably
  related" -- citing the CP-SAT proof (Sec 3.1), its fresh reproduction
  (Sec 3.2), and independent convex-hull corroboration (Sec 3.3), not
  assertion.
- Nobody mistakes the Group A (`C27`) pairs for genuine placement or
  footprint defects -- they are a data-integrity defect with a different,
  already-existing remediation path (R1-R2).

---

## Scope Boundaries

- `pcb/temper.kicad_pcb` and `pcb/libs/**` were not modified -- read-only
  per task instruction. All geometry claims in Sec 3.3 were computed by
  reading the committed board, never writing to it.
- No CP-SAT solve was re-run by this document (Sec 3.1's proof and Sec
  2/Group C's precedent are both cited from prior, already-completed,
  already-committed investigations, not reproduced by executing the solver
  here) -- reproducing them would require the same read-write access this
  task's hard constraints forbid.
- `test_clearance.py` was not modified. It is reporting true findings, per
  task instruction.
- The `HIGH_VOLTAGE_CLEARANCE_SPEC.md` vs. `clearance.py` figure
  discrepancy (Sec 4, R9) is reported, not resolved -- resolving it means
  either editing repo-wide safety constants or the spec document, both
  out of scope for a read-only analysis pass.
- The `check_copper_net_consistency.py` resync defect (R1) is reported,
  not fixed -- it is a pre-existing, independently-tracked gate failure,
  not something this task's scope covers fixing.

---

## Key Decisions

- **Treat the `C27` mismatch as a distinct fix-class (Reclassification-
  equivalent), not folded into Placement or Footprint.** Its root cause
  (netlist/PCB ref-designator drift) is neither "move the part" nor
  "change the footprint" -- treating it as either would produce a false
  sense that fixing it is a normal placement/footprint task, when it is
  actually blocked on separate tooling (R1).
- **Cite the prior CP-SAT infeasibility proof rather than re-deriving it
  from a synthetic model.** `docs/evidence/2026-07-28-barrier-constrained-
  placement.md` already did this rigorously (hard CP-SAT constraint,
  `INFEASIBLE`, named UNSAT core, per-isolator table); re-deriving it here
  with a hand-built heuristic would be strictly weaker evidence for the
  same conclusion. This document's own convex-hull check (Sec 3.3) is
  presented as corroboration, not as the primary proof.
- **Flag the fresh vs. stale pad-geometry-model distinction explicitly**
  (Sec 2, Group B) rather than silently reusing the barrier investigation's
  older numbers. `T1` genuinely passes now (9.100mm) under the exact model;
  presenting it as still-infeasible would misdirect a human toward fixing a
  component that no longer needs fixing.

---

## Dependencies / Assumptions

1. **Assumption:** the `IEC60335_REQUIREMENTS` figures in `clearance.py`
   (6.0/8.0/10.0mm) are the correct governing values, not
   `HIGH_VOLTAGE_CLEARANCE_SPEC.md`'s (5.0/10.0/8.0/12.0mm).
   **Falsifier:** a primary-IEC-60664-1-Table-F.2 lookup at 400V,
   reinforced insulation, pollution degree 2, shows the spec document's
   figures are correct and `clearance.py`'s constants need correcting --
   if so, every "required" figure in Sec 1's table shifts and some of the
   21 Group C pairs' classification (currently-passing basic-only vs.
   currently-failing reinforced) could change.
2. **Assumption:** the 21 Group C pairs are placement-fixable (room exists
   somewhere on the board once a copper-aware re-solve runs).
   **Falsifier:** running `temper_placer.placer.cp_sat.domain_clearance`'s
   constraint generator with copper-aware margins against the real board
   returns `INFEASIBLE` (or `optimal` with residual violations) for any
   subset of these 21 -- if so, that subset needs re-classifying as
   Footprint or Topology, not Placement, and this document's Sec 2/Group C
   classification for that subset is wrong.
3. **Assumption:** only `C27`'s pad-mismatch (of the 10
   `check_copper_net_consistency.py` violations) changes a domain
   classification relevant to the 33-pair table; `C30`/`C34`/`C35`'s
   mismatches do not.
   **Falsifier:** re-deriving `C30`/`C34`/`C35`'s domain membership using
   their compiled-netlist-declared nets rather than their real PCB pad nets
   changes their classification from SELV to something else -- checked
   directly in this pass (both pads of each were compared) and did not
   hold, but a future net-name change could invalidate this.
4. **Assumption:** `U7`'s 0.75mm shortfall is recoverable within the
   `SOIC16W_Isolated` footprint family without a part change.
   **Falsifier:** a UCC21550 datasheet-level review (R6) finds the current
   footprint is already at its physically defensible minimum pad spacing
   for that package -- in which case `U7` needs the same "different part"
   treatment as `C6`/`K2`/`K3`, not a footprint tweak.
5. **Assumption:** the board's stated dimensions in
   `HIGH_VOLTAGE_CLEARANCE_SPEC.md` (100mm x 150mm) are simply stale
   documentation, not evidence of a different intended board outline.
   **Falsifier:** a human confirms the spec's dimensions reflect an
   intended future board revision rather than a drafting artifact -- this
   was not otherwise investigated (out of scope) and is stated only as an
   observed inconsistency, not resolved either way.

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R9][User decision] Which figure set governs the
  `DC_BUS<->LV_CONTROL` reinforced boundary: `clearance.py`'s
  6.0/8.0/10.0mm or `HIGH_VOLTAGE_CLEARANCE_SPEC.md`'s 5.0/10.0/8.0/12.0mm?
  Both are secondary-sourced (IEC 60335-1/60664-1 primary text is
  paywalled); a primary-standard lookup or an explicit "we standardize on
  X, spec doc corrected" decision is needed before Sec 1's numbers can be
  called final rather than provisional.
- [Affects R3/R4][User decision] Approve (or reject) sourcing new parts for
  `C6` (wider-pitch Y-cap) and `K2`/`K3` (reinforced-isolation relay
  family) -- these are BOM/cost/lead-time decisions this document cannot
  make.
- [Affects R6][Needs research] TI UCC21550 datasheet layout review: can
  `U7`'s footprint recover 0.75mm within the same package, or is a
  different device required?

### Deferred to Planning

- [Affects R1/R2][Technical] Run `scripts/resync_pcb_netlist.py` (or
  diagnose why the prior 2026-07-27 resync did not catch this specific
  `C27`-area drift) and re-derive the 7 Group A pairs' true classification
  and clearance figures afterward.
- [Affects R5][Technical] Regenerate `pcb/temper.kicad_pcb`'s `U3`
  footprint from the already-updated `elec/src/components.ato` source --
  mechanical, not a new decision.
- [Affects R7][Technical] Update `temper_placer.placer.cp_sat.
  domain_clearance`'s constraint generator to use copper-aware margins
  (matching what `clearance.py` now measures) instead of origin-to-origin,
  then re-solve against the current 54-net manifest classification.
- [Affects R8][Technical] Once R3-R6 land, re-run the
  `isolation_barrier=`-constrained CP-SAT solve
  (`temper_placer.placer.cp_sat.isolation_barrier`, already implemented
  per `docs/evidence/2026-07-28-barrier-constrained-placement.md`) to
  confirm feasibility and produce the actual `MAINS_SELV_ISOLATION_BARRIER`
  zone.
