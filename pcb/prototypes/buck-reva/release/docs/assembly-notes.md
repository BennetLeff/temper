# Buck Rev A assembly notes — frozen revision A

These notes are bound to the frozen board and final export manifest. Use the
assembly drawing with this note; no hardware has been assembled or powered.

## Population and sequence

- Populate U3, L2, C9, C10, C11, C12, C13, R16 and R17 (nine SMT parts; no DNP).
- J1 and J2 are Würth Elektronik 691253500002, 2-position 5.08 mm vertical
  top-entry terminals. They are excluded from SMT placement and hand-soldered
  after SMT inspection. J1.1 = VIN, J1.2 = GND; J2.1 = 3V3, J2.2 = GND.
- TP1 VIN, TP2 GND, TP3 VOUT and TP4 GND are bare copper probe pads and are
  not purchased. There is no TP5 and no populated SW probe.
- Reflow or hand-place ordinary SMT parts first. Hand-solder the nine
  unfilled via-in-pad joints and J1/J2, then inspect under magnification for
  solder starvation, bridges and connector seating. Record any rework as a
  new assembly identity.

## Coordinates and inspection

- `positions-smt.csv` is the generic top-side SMT placement file. The full
  position file is retained for reconciliation; `tht-manual-list.csv` is the
  authoritative manual-install list.
- Units are mm, with the KiCad project origin and emitted board-side/rotation
  fields. Spot-check U3 pin 1, L2 orientation, J1/J2 pin-1 markers and the
  polarity/labels on the assembly drawing before soldering.
- Verify connector wire entry is vertical/top-entry and verify the final silk
  map: J1 VIN/GND, J2 3V3/GND, TP1/TP2 input and TP3/TP4 output.

The package is suitable for manual prototype assembly after an explicit order
decision. It does not claim a generic automated reflow process is qualified.
