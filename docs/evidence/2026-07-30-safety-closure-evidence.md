---
date: 2026-07-30
topic: safety-closure-evidence
status: measured-open-decisions
provenance:
  measured_at_commit: 4fd1fb6f5301e82ab4d24ebc3beb305b24e7024f
  base_commit: bb7592755
  branch: codex/safety-closure
  dirty: false
  note: "Measurements were re-run after rebasing onto bb7592755; tracked tree was clean at measurement time; make netlist created ignored elec/build and .venv artifacts."
  follow_up_source_commit: fb5dbf5d5
  follow_up_note: "ADC top-resistor power_rating metadata corrected from 0.1W to 0.25W; netlist and domain gate rerun successfully; no PCB geometry changed."
---

# Safety-closure evidence pass

This is an evidence record, not a safety approval. It records the current
measurements and the decisions still required before changing the board or
citing the electrical claims externally.

## Executive result

| Area | Current result | Decision/status |
|---|---|---|
| ADC protective-impedance divider | 959.314 µA worst case at the declared +170 V half-bus, with ±1% resistor tolerance and two top resistors shorted; 1.407× below the 1.35 mA limit | The ~1.4× figure is valid only for the declared +170 V operating assumption; it is not a 400 V absolute-bus claim |
| Domain topology | 0 domain crossings, 0 isolator breaches, 0 protective-impedance chain defects | Construction gate passes; this does not prove physical PCB creepage |
| REQ-SAFE-01 | 123 clearance/creepage violations across 86 pairs, plus 6 unclassified proximity findings | Open; placement and architecture work remain |
| Physical mains↔SELV keepout | 0 keepout zones; required named barrier absent | Open and human design-blocking |
| `tank.c_tank3` | Source/netlist/PCB identity agrees as C27; footprint staged at `(20.0, 272.75)` outside the board | Open placement decision |
| DRC ceiling | Provenance fresh; current single run 865 errors / 680 warnings, ceilings 875 / 680 | Ceiling file is not stale against the current board; no ceiling edit made here |

## 1. ADC divider margin

### Committed construction

The source at the time of the measurement recorded below declared
`r_adc_top1/2/3 = 169 kΩ ±1%`, `r_adc_bot = 10 kΩ ±1%`, and
`power_rating = 0.1 W` for each top resistor. The three top resistors are in
series from `+170V_BUS` to `V_BUS_SENSE`; the bottom resistor returns the sense
node to `gnd`.

The source also defines the crossing as a +170 V half-bus, while the system
defines a 340 V nominal/full bus and a 400 V absolute full-bus limit. Those are
not interchangeable assumptions.

### Recalculation

The deliberately stricter two-top-resistors-short condition leaves one top
resistor and the bottom resistor. Maximising current with the declared ±1%
tolerances gives:

```
Rtop_remaining = 169 kΩ × 0.99 = 167.31 kΩ
Rbottom        = 10 kΩ × 0.99   =   9.90 kΩ
Rfault         = 177.21 kΩ
I170V          = 170 V / 177.21 kΩ = 959.314 µA
```

Using the existing 1.35 mA limit (`0.75 mA/kW × 1.8 kW`, subject to the
standard-source caveat already recorded in the manifest):

| Half-bus assumption | Double-fault current | Margin to 1.35 mA |
|---:|---:|---:|
| 170 V, declared operating point | 959.314 µA | **1.407×** |
| 180 V, higher operating check | 1,015.744 µA | 1.329× |
| 200 V, implied by 400 V absolute full bus | 1,128.604 µA | 1.196× |

The required one-component fault is less severe: at 170 V, two top resistors
remaining at their minimum gives 493.440 µA, or 2.736× margin.

**Conclusion:** the headline “1.4× double-fault margin” is reproducible as an
approximately 1.4× margin at the declared +170 V half-bus, even after applying
the resistor tolerances. It must not be cited as a margin at the 400 V
absolute full-bus limit; that condition has only 1.196× arithmetic margin.
The protective-impedance standard interpretation, the 1.35 mA limit, the
ESP32 ADC input behaviour on `r_adc_bot` open, and safety-resistor qualification
remain the source's documented `UNVERIFIED` items.

The source fields also deserved a follow-up review: the ADC top parts are
`RC1206FR-07169KL` in 1206 footprints but declared 0.1 W, while the same
RC1206 family used by the comparator divider declared 0.25 W. The follow-up
correction below resolves that metadata discrepancy without changing the
arithmetic or the board.

## 2. Domain and physical-isolation checks

After `make netlist`, the construction gate reported:

```
Checked 54 declared nets across 2 domains (HV, SELV),
10 declared isolators, 2 protective-impedance chains (6 members),
over 162 compiled nets / 169 components.
PASSED -- 0 domain crossings, 0 isolator-barrier breaches,
0 protective-impedance chain defects
```

The physical board gate reported 169 footprints, 521 pads, 99 HV pads, 221
SELV pads, 2,482 copper items, and **0 keepout zones**. The required zone
`MAINS_SELV_ISOLATION_BARRIER` is absent, so the physical mains↔SELV boundary
is not enforced by a board keepout. The construction gate and the physical
keepout gate measure different properties; the first passing does not make the
second pass.

The current architecture is therefore still unresolved:

- PD3 / 12.6 mm remains the operative requirement for the current unsealed,
  vented construction.
- A PD2 / 8.0 mm path is an architectural option only if a genuinely sealed
  compartment and its thermal, cable, connector, and manufacturing arguments
  are designed and approved.
- No keepout or component placement has been added by this evidence pass.

## 3. REQ-SAFE-01 current measurement

Command:

```
uv run --no-sync pytest \
  packages/temper-placer/tests/requirements/safety/test_clearance.py::\
  TestClearanceIntegration::test_temper_board_clearance_compliance -q
```

The test fails with **123 REQ-SAFE-01 clearance/creepage violations across 86
pairs**, and separately reports **6 unclassified components** closer than the
largest 12.6 mm IEC margin to declared-HV components:

| Unclassified component | Copper distance | HV neighbour |
|---|---:|---|
| R42 | 8.570 mm | R5 |
| R34 | 8.645 mm | R5 |
| R40 | 8.705 mm | R5 |
| R45 | 9.681 mm | R5 |
| C10 | 10.420 mm | C25 |
| R64 | 10.661 mm | U2 |

The first violating pair is `C17↔R32` at 0.905 mm against 12.6 mm
reinforced creepage. The report includes 11 intra-footprint records, which
cannot be corrected by translating a component. It also includes placement
violations whose resolution would require a board re-layout and re-route.

The evidence does not collapse all 123 records into a single proposed fix:
the next design step must preserve the distinction between movable placement
findings, intrinsic package geometry, unclassified coverage, and violations
that depend on the selected isolation architecture.

## 4. `tank.c_tank3` reconciliation

Source and generated artifacts agree:

- `elec/src/modules.ato`: `tank.c_tank3`, 100 nF polypropylene, CDE
  `942C16P1K-F`, 1600 V, custom axial footprint.
- Fresh `make netlist`: `tank.c_tank3` maps to designator **C27**.
- Fresh netlist connectivity: C27 pin 1 is on `SW_NODE`; C27 pin 2 is on
  `tank.c_tank1-p2`, shared with C25, C26, and R30.
- PCB: reference C27 and sheetpath `tank.c_tank3` use the same custom
  footprint and the same two net assignments.

The physical state is not final. The PCB footprint origin is `(20.0, 272.75)`
with the board edge ending at approximately y=254 mm. Its courtyard extends
to y=284.25 mm and x=18.45 mm, so it is a staging footprint outside the board
outline, not a manufacturable placement. The tank capacitor placement remains
a human board-design decision.

## 5. DRC ceiling status

`scripts/check_measurement_provenance.py` reports the current
`drc_ceiling.json#boards.temper` record **fresh**: its recorded board hash
matches `pcb/temper.kicad_pcb`. The approval gate also reports no ceiling raise
between `origin/main` and this evidence branch.

The repository DRC checker, using the generated KiCad rules file and the local
KiCad 10.0.4 backend, reports:

```
PASS: temper: DRC 866/875 errors, 680/680 warnings within ceiling
```

A direct `run_drc()` sample from the same board returned 865 errors and 680
warnings, with these per-type counts:

```text
errors:   annular_width 4, clearance 499, copper_edge_clearance 15,
          courtyards_overlap 14, creepage 32, drill_out_of_range 4,
          hole_clearance 102, hole_to_hole 1, shorting_items 118,
          solder_mask_bridge 69, tracks_crossing 3, via_diameter 4
warnings: holes_co_located 2, lib_footprint_issues 9,
          lib_footprint_mismatch 25, missing_courtyard 5,
          pth_inside_courtyard 9, silk_edge_clearance 199,
          silk_over_copper 199, silk_overlap 199, track_dangling 29,
          via_dangling 4
```

The current committed ceilings are 875 errors and 680 warnings. This pass did
not change the ceiling file and therefore did not add a `Ceiling-Approval:`
trailer. The earlier “stale on two axes” condition is not present against the
current board hash; the current open issue is debt within the ceiling, not
stale provenance.

## Remaining owner decisions

1. Select the isolation architecture: earn a sealed PD2 compartment, or keep
   the current construction on the PD3 / 12.6 mm path and redesign the board
   accordingly.
2. Approve a real placement for C27 / `tank.c_tank3` and then re-run the
   copper, keepout, DRC, and netlist gates in the same board-changing change.
3. Decide whether to correct the ADC top-resistor power metadata and whether
   the protective-impedance claim will be externally cited only for +170 V
   nominal operation or also for a higher bus condition.
4. Fix the 123 REQ-SAFE-01 findings through an approved placement/package/
   architecture plan; do not reduce the requirement or add exemptions to make
   the count disappear.

## Follow-up: ADC top-resistor metadata correction

The three `RC1206FR-07169KL` top resistors now declare `power_rating = 0.25W`,
matching the datasheet-backed RC1206 family record and the identical
`r_div_top1/2/3` declarations. No value, voltage rating, footprint, topology,
board geometry, safety threshold, or DRC ceiling changed.

Validation on the follow-up branch:

- `make netlist` completed successfully; all Atopile assertions passed.
- The regenerated netlist retained R56/R57/R58 as the three ADC top parts,
  with the expected 1206 footprint and `RC1206FR-07169KL` BOM grouping.
- The domain partition gate passed: 0 domain crossings, 0 isolator-barrier
  breaches, and 0 protective-impedance chain defects across 54 declared nets.
- The original ADC arithmetic and its +170 V operating-envelope caveat are
  unchanged; the metadata correction only prevents a future rating check from
  treating the 1206 parts as 100 mW parts.

<!-- provenance: commit=5794d22f7ec4fa63291715a7b0526c2f01c5591f dirty=false -->
