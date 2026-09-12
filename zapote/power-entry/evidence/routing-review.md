# Routed PFC construction review

The source22 circuit has 54 physical components and 33 nets. The actual saved
board has 250 straight trace segments, 44 vias and one signal-return zone.
Native11 ERC/DRC and the independent Rust construction findings pass. The
overall result remains INDETERMINATE for unrun hardware qualification.

## Changes made while routing

- Added the missing local 470 nF / 630 V film bypass, TDK B32672P6474K000,
  across the PFC bus beside the MOSFET and boost diode. The inherited
  B32671L6474K000 identity was rejected against TDK's actual ordering table.
  [TDK exact part](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32672P6474K000)
- Replaced five 200 kOhm 1206 feedback resistors with 200 kOhm 2512
  CRCW2512200KFKEG. Their values and nominal bus setpoint are unchanged.
  The larger land pattern provides the required terminal spacing. Vishay
  specifies the 2512 series at 1 W and 500 V, subject to operating conditions.
  [Vishay D/CRCW e3](https://www.vishay.com/docs/20035/dcrcwe3.pdf)
- Revised the local GBU bridge lands from 3.2 mm-wide copper to 3.0 × 3.2 mm
  copper, using oval lands for pins 2–4 and a rectangular pin-1 land. The
  5.08 mm pitch and 1.6 mm holes remain unchanged from the mechanically
  reviewed footprint. Minimum nominal annular copper is 0.7 mm, and adjacent
  land spacing becomes 2.08 mm. This changes the board land pattern; it does
  not certify creepage inside the rectifier package. The local library and
  source manifest bind this override; the global KiCad library was not edited.
- Moved the NTC beside the input filter and separated precharge power paths
  from the controller. Extended the board from 230 × 190 to 230 × 210 mm
  for the PE/Y-capacitor route. This prototype dimension is not an enclosure
  fit claim.
- Connected both physical holes of each relay contact, all fuse terminals,
  both boost-diode anodes, and the shunt's power transitions. The shunt is
  SMD: explicit six-via groups connect each power terminal to the back layer.
- Kept a separate B.Cu signal-return island with an explicit Kelvin return
  from the shunt's bus-minus terminal. The negative sense connection has its
  own route to the filter and clamp. High-current return copper does not use
  the signal island as its series path.

## What was checked

The shared native transport applies only agent-authored polylines and native
footprint edits. It does not plan routes. Native DRC uses `--all-track-errors`,
`--schematic-parity`, `--severity-all`, and the project's actual rules.

Rust compares the compiled source graph, MPNs and physical pad census with the
native export, binds it to the saved PCB bytes, checks the 2-layer physical
stackup, and requires one native copper cluster for each complete source net.
The reusable clearance profile preserves physical layer overlap and includes
pads, traces, vias and zone copper through the existing geometry kernel.

The native and Rust construction floors are 2 mm for any pair involving a
high-voltage net, 6 mm for PE against another net, and 0.2 mm otherwise. All
four elevated intermediate feedback taps are included. No suppression or
lowered floor was used to resolve an intrinsic pad-spacing failure.

Native DRC passed a sense-via gap exactly at its 0.2 mm boundary while Rust's
floating-point calculation returned slightly below it. The layout gained
0.3 mm of additional margin; the Rust threshold was not relaxed. The earlier
native10/Rust10 artifacts preserve that discrepancy.

## Limits of the checkpoint

The 6–8 mm power corridors and explicit narrower terminal necks are layout
choices, not a completed ampacity certificate. Via sharing, finished copper,
local temperature rise, switching-loop inductance, EMI and insulation remain
unqualified. The native 3D render was inspected and shows a thin PCB with the
large choke and bulk capacitors; several component bodies and all required
heatsink/service envelopes are absent. It is not a mechanical fit proof.

The native clearance rule is not a creepage, altitude, pollution-degree or
product-safety assessment. External isolated 15 V bias, precharge/bypass
control, default-off permit, 15 A RMS low-line foldback and active discharge
still need system integration. Powered tests, loaded loop behavior, thermal,
EMC and mains qualification are NOT RUN. This is a routed construction
checkpoint, not a fabrication or powered-operation release.
