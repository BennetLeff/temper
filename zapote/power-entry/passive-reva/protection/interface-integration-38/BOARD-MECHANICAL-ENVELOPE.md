# Rev38 standalone section-board envelope for review

**Status: user-approved planning envelope, 2026-09-24.** This is a
dimensioned starting point for the source-to-PFC Rev38 section, not a
released outline, placement, stackup, insulation schedule, or native board.
No existing cooker enclosure or mounting drawing was supplied for this
section. The existing cooker ESP remains the command source through the
16-contact SELV port; the cooker inverter is outside this board.

## Proposed datum and occupied regions

View from the component side. Use the upper-left board corner as `(0, 0)`;
`x` increases right and `y` increases down. Propose a **360 × 250 mm**
rectangular PCB as a deliberately generous *planning envelope*. The user
approved using this size for reviewed placement; it is not a manufacturer
requirement or a fit check. `outline.json` records this rectangle for the
native candidate, but does not approve mounting or routing.

| Region, mm | Intended contents | Access and separation to review |
| --- | --- | --- |
| `x 20–95, y 25–125` | Fused L/N/PE board entry, EMI/CMC, NTC, relay and rectifier approach | Wire entry from left edge; terminal torque, conductor bend and the off-board F1 harness need enclosure clearance. Keep PE connection and Y1 path explicit. |
| `x 20–95, y 135–225` | Off-board AUX branch entry, IRM-20-24 and first HOT supply stages | Branch loop and any cover remain accessible from left/bottom; this output is HOT after its return joins HOT0. |
| `x 95–235, y 25–135` | PFC inductor, bridge, boost switch/diode, gate driver and HOT protection | Reserve heatsink, airflow, switching-current loop and probe access; do not place the TO-247 cathode tab against an unreviewed conductive structure. |
| `x 95–235, y 135–225` | VD film reservoir, four VB bulk capacitors, bleeders and two F2 board studs | Give the VD and VB studs separate insulated cable routes toward the off-board US141 holder. Keep bulk-cap vents and service access clear. |
| `x 235–270, y 18–232` | SELV/HOT isolation corridor | Reserve this whole strip from ordinary copper and mounting hardware. The two DWW isolators cross here only after a slot/laminate/clearance construction is accepted. |
| `x 270–340, y 20–230` | SELV source control, watchdog and 16-contact cooker port | Put the port toward the right edge with keying, return contacts, harness bend and unplug access checked against the enclosure. No HOT test point may enter this region. |

These rectangles are **placement zones**, not footprint poses. Components
that bridge zones, connector overhangs and large heatsinks require a 3D
mechanical review before any coordinate is frozen. In particular the
manufacturer's [IRM-20-24 data](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF)
give a 52.4 × 27.2 × 24 mm module body, and the selected four VB capacitors
use 35 mm diameter packages; actual courtyard, vent and mounting space are
larger than their electrical pad patterns. The two
[Würth 74651173R studs](https://www.we-online.com/components/products/datasheet/74651173R.pdf)
have a 5.87 mm four-hole grid, but the lug, washer, insulation boot, cable
bend and tool swing are not in their review-only KiCad courtyard.

Candidate insulating-standoff centers are `(12,12)`, `(180,12)`,
`(348,12)`, `(12,238)`, `(180,238)`, `(348,238)` mm, for a six-point support
screen. These are **not** approved drill holes or chassis connections. Mount
diameter, board-to-enclosure height, washer keepout, vibration support and
whether any fastener can become accessible or grounded need a mechanical
decision. No hole is added to the Atopile source or native board yet.

## Electrical and test constraints on placement

- The provisional >400–500 V, PD3 Group IIIa **board** screen is 16.0 mm
  reinforced creepage across SELV/HOT; separately qualified Group I package
  surfaces use a 12.6 mm candidate screen. The selected DWW land pattern
  leaves **15.2 mm nominal opposed-pad copper gap**, so this envelope alone
  cannot satisfy the 16.0 mm board surface screen. A reviewed slot, Group I
  laminate construction, or another accepted path is needed. Air clearance,
  working-voltage overshoot and the product-standard schedule remain open.
- Keep the two F2 studs separately named `VD_LOCAL` and `VB_BANK`. Their
  center spacing, exposed lug geometry and cable routing must be chosen from
  the actual F2-open voltage and fault-energy envelope. The stud's 50 A at
  20 °C figure is not a PTH, copper, cable or DC fault-pulse approval.
- The present native generator's six copper-layer declarations come from a
  donor skeleton. No Rev38 laminate CTI, finished thickness, copper weights,
  thermal-via rules or current-path cross sections have been released.
  A candidate **1.8 mm nominal** board thickness would put a controlled
  1.7–1.9 mm finished range within the stud's published 1.6–2.0 mm board
  range; confirm connector and fabrication compatibility before selecting it.
- Reserve access for separate fault-injection and measured endpoints in
  `bench-capture.md`: source/HOT watchdog and rail edges, START/PERMIT/RUN,
  driver EN, loaded gate and PFC current. The source currently contains no
  explicit test-point instances. Add selected test points to Atopile and the
  exact pin audit before placing them; do not substitute unlabeled copper
  probes in a safety claim.

## Review decisions before native placement

1. Check whether the approved 360 × 250 mm planning board and six proposed
   support points fit the actual cooker enclosure, fan/air path, covers,
   service access and shock protection. Revise `outline.json` if the real
   mechanical envelope requires a different size. The support points are
   still proposals, not approved holes.
2. Fix connector orientation and cable exits for AC/PE, AUX branch, F2 holder
   and SELV port, including strain relief, torque and insulation boots.
3. Select the appliance standard/edition and insulation construction,
   including laminate CTI, slot geometry, air clearance, mounting hardware
   and maximum VD/VB waveforms. Convert it to net-pair rules and a rule
   coverage test; the provisional creepage values do not approve DRC.
4. Select a fabricator stackup and copper/current/thermal design, then
   determine heatsink mounting, high-current copper, PTH and capacitor vent
   clearances. Establish test-point locations and safe probe approach.
5. Place the edge anchors and HOT/SELV crossing first in a native KiCad
   candidate. Only after that review should every source reference receive
   an exact pose; route and run ERC/DRC, source/native
   parity and stackup gates on the saved board.

Until these decisions are closed, the planning `outline.json` and any
generated `poses.json` yield a diagnostic skeleton rather than the plan's
reviewed U7 deliverable.
