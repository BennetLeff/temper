# Revised placement and routing review — native-05/native-06

Status: work in progress, 2026-09-26. The owner approved the 240 × 160 mm
outline and four layers. The revised placement still needs D4 review after
routing and verification finish. This file is not an approval or a fabrication
release. The earlier review is preserved in
[native-04/PLACEMENT-REVIEW.md](native-04/PLACEMENT-REVIEW.md).

![Current placement](native-05/placement-preview.png)

The electrical source remains 114 components and 75 nets. Native-05 is the
source-generated placement; native-06 is the active routed candidate. Routing
is explicit and reproducible from the JSON batches under `routes/`.

## Changes from the approved native-04 placement

- The power stage, controller island and tank bank move right to use the extra
  20 mm of board width. Mains remains on the left, coil terminals on the right,
  and the shared heatsink along the top edge.
- The line filter, bridge, auxiliary supplies, left bulk capacitor and removable
  rectifier links are rearranged. Link straps now run vertically near the top
  left, with bench leads leaving the left edge when the straps are removed.
- The bus-divider/over-voltage cluster and HOT regulator move into the western
  routing area. C24 and C26 exchange positions so each bypass sits by its own
  supply pin.
- R25 moves 0.7 mm left to keep its routed escape away from the provisional
  coil-terminal lug envelope.
- The over-current comparator and its nine supporting parts move 46 mm left
  and 11 mm upward, beside the HOT regulator. This removes their via wall from
  the SW_B power corridor. The longer shunt sense pair needs noise testing;
  its two conductors are routed together from R5's Kelvin pads.
- D1 moves into the gap below the capacitor row, at KiCad anchor (131.5, 40.0).
  Its through-hole pads no longer obstruct the bus and tank-return corridors.
  The bootstrap capacitors remain beside their driver.
- The proposed stackup has four 70 µm copper layers and nominal 1.6 mm overall
  thickness. Fabricator acceptance and finished minimum copper/plating remain
  open.

Gate resistors remain at the MOSFET gates. Leg A's high-side drive now has an
explicit nearby SW_A return. Local bus capacitors return through HV_RET and
R5 current pads 1/4; the control pickup stays on Kelvin pad 2, with the opposing
sense on pad 3. The R5 internal connection is discussed in [ROUTING.md](ROUTING.md).

## Review evidence

The final board must have current, hash-bound source/MPN/pad parity, filled-board
stackup, native DRC, all-layer barrier, terminal-hardware and power-path checks.
Intermediate clean DRC reports are not acceptance: native DRC alone does not
check the provisional 8 mm plan-view barrier between different copper layers.
Results will be recorded here when the remaining route and barrier fixes are
integrated. See [ROUTING.md](ROUTING.md) for copper arrangement and pending gates.

The terminal strap dimensions and lug envelopes remain provisional until
measured hardware replaces them. J1 wire-entry orientation, enclosure fit,
airflow, certification-lab review, Coilcraft insulation evidence and the RCA
teardown remain open. Physical overshoot/clamp, protection, thermal, leakage,
hipot and EMI tests have not run.
