# Active rectifier and fused-bank construction candidate

**2026-09-19 review correction:** the authored source is now an experimental
Infineon-bridge integration; `candidate/` remains the older TEA routed board.
They are deliberately different revisions, not source/PCB parity. The new
source/native construction and corrected protection logic are recorded in
[REVIEW-FIXES.md](decisions/f2-open/REVIEW-FIXES.md). Package 2 is incomplete:
no supported diode-side clamp and no complete gate-off timing budget are
established. Do not promote the new construction to routing/freeze using the
older board's reports. The following implementation description and FREEZE
apply only to the retained TEA `candidate/`.

2026-09-18. Implements the selected circuit from [CLOSEOUT](../CLOSEOUT.md).
**CAD construction checkpoint; acceptance incomplete. Do not fabricate or power
from this checkpoint.** The active Rust contract now runs against the saved board. Three TEA package
clearance findings, fuse/clip fit and Q1–Q5 qualification remain open. This is not a validated
campaign run or a protection-coordination result.

**2026-09-19 implementation:** U20 feedback now senses the diode side of F2
through authored source, compiled netlist, schematic and PCB. The
[current freeze](FREEZE.md) records fresh checks. The
[F2 transient assessment](experiments/f2-open/README.md) finds a conditional
674.7 V excursion with the existing 470 nF even with immediate switch-off;
the wiring correction does not close protection. The
[TEA reference-Gerber comparison](decisions/tea-resolution/reference-gerber/README.md)
provides no supported spacing fix. A limited
[NXP request](decisions/tea-resolution/NXP-MESSAGE.txt) is prepared and unsent.

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
  local U40 and U20 feedback-divider top; U66 separates that net from all four
  bulk capacitors, output and bulk bleeders. There is no copper bypass.
- Current saved feedback is **diode-side**. Opening F2 leaves the controller
  sensing the still line-fed diode-side output. The disconnected bank has no
  separate implemented voltage monitor. Remaining inductor energy, VSENSE
  filtering, controller response and no-load restart still need resolution.
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
- [Current copper](evidence/vsense-diode-side-02/copper.svg),
  [current schematic PDF](evidence/vsense-diode-side-02/section.pdf),
  [historical pre-ECO 3D preview](evidence/rust-integration-01/board-3d.png).
  The 3D preview omits F2/clips,
  heatsinks and several inherited custom-part bodies; it cannot verify assembly fit.
- [BOM](bom.csv), [fuse mechanical review](MECHANICAL.md),
  [validation report](VALIDATION.md), [Rust integration and repairs](RUST-INTEGRATION.md),
  [replay instructions](REPRODUCE.md).

## What remains

1. Resolve three TEA footprint gaps (pads 3–5, 10–12, 14–16): 1.94 mm
   against the retained 2 mm elevated-voltage construction floor. The active
   Rust contract, NC binding, domain and current assignments now run. Routing
   repairs clear nine other spacing findings and all eight determined nominal
   branch-current findings. Surface creepage, pad/barrel capacity and active
   loss/thermal qualification remain open; see [the integration record](RUST-INTEGRATION.md).
2. Resolve the F2 clip drawing/fit and Mersen/holder application review;
   finalize the land pattern and rerun construction checks. Selected slot
   allowances and clip spacing are prototype assumptions.
3. Complete Q1–Q5: fuse coordination, surge, common mode, bootstrap/gate
   operation, startup/control behavior and installed cooling. No tests were
   run on physical hardware; no procurement or fabrication order was placed.

The native minimum-clearance DRC is not a high-voltage spacing or ampacity
qualification. Existing model/thermal results retain their original board
identities and are not rebound to this candidate.
