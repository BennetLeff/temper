# Active rectifier and fused-bank construction candidate

2026-09-18. Implements the selected circuit from [CLOSEOUT](../CLOSEOUT.md).
**CAD construction checkpoint; acceptance incomplete. Do not fabricate or power
from this checkpoint.** The existing Rust power-entry contract rejects the new
entry. Fuse/clip fit and Q1–Q5 qualification remain open. This is not a validated
campaign run or a protection-coordination result.

## Implemented

- TEA2209T/1 (U1), four IPW60R017C7 (U55–U58), two 220 nF
  C0805C224K5RACTU bootstrap capacitors and 2.2 µF C0805C225K5RACTU VCC
  bypass. Four 10 Ω RC1206FR-0710RL gate-resistor tuning positions.
- Upper MOSFET drains at rectifier positive, upper sources/lower drains at
  L/R, lower sources and TEA GND on the **rectifier side** of U12. COMP_POL
  is low; COMP and HVS pins are explicitly NC. Gate disable is not mains
  disconnection. The TO-247 drain tabs are not all at the same potential:
  any shared heatsink needs an engineered electrical isolation arrangement.
- Proposed F2, Mersen A70QS50-14F, represented as U66 to preserve the source
  compiler's reference identities. `BOOST_DIODE_POSITIVE` connects U10.K,
  local C40 and the feedback divider; U66 separates that net from all four
  bulk capacitors, output and bulk bleeders. There is no copper bypass.
- Deliberate refinement of CLOSEOUT §3: feedback remains **diode-side** so
  opening F2 does not remove feedback from the still line-fed converter.
  This does not prove stable operation or acceptable opening transients.
  The local 470 nF remains unfused; the fused bank is nominally 2240 µF
  (~179.2 J at 400 V), not a maximum energy bound. U12/F1 still do not sense
  or interrupt the internal bank/U10/U9 loop. No shutdown credit is added.
- Preserved the passive shunt-repair board and most of its copper. This
  spacious experiment adds an 80 mm side area: **310 × 210 mm**, two layers,
  1.6 mm finished stack, 70 µm copper per side. It is not the final enclosure
  layout, a compact integration result, or a verified current-capacity design.

## Artifacts

- [Authored Atopile](../../../elec/src/power_entry_active_unit.ato).
- [PCB](candidate/section.kicad_pcb), [schematic](candidate/section.kicad_sch),
  [project](candidate/section.kicad_pro).
- [3D preview](renders/board-3d.png), [copper](renders/copper.pdf),
  [schematic PDF](renders/schematic.pdf). The 3D preview omits F2/clips,
  heatsinks and several inherited custom-part bodies; it cannot verify assembly fit.
- [BOM](bom.csv), [fuse mechanical review](MECHANICAL.md),
  [validation report](VALIDATION.md), [replay instructions](REPRODUCE.md).

## What remains

1. Extend the **concrete unit contract** to represent this circuit, including
   all active-bridge high-voltage nets, F2 and diode-side feedback. Run the
   existing electrical/current/clearance/manufacturing checks on it with
   actual operating-current assignments. The current passive fixture cannot
   qualify this replacement. Do not alias the new source as the old one.
   No generic harness/schema work is requested.
2. Resolve the F2 clip drawing/fit and Mersen/holder application review;
   finalize the land pattern and rerun construction checks. Selected slot
   allowances and clip spacing are prototype assumptions.
3. Complete Q1–Q5: fuse coordination, surge, common mode, bootstrap/gate
   operation, startup/control behavior and installed cooling. No tests were
   run on physical hardware; no procurement or fabrication order was placed.

The native minimum-clearance DRC is not a high-voltage spacing or ampacity
qualification. Existing model/thermal results retain their original board
identities and are not rebound to this candidate.
