# Rev38 placement anchors for review

**Status: proposed coordinates only, 2026-09-24.** This note maps the
user-approved 360 × 250 mm planning envelope to actual references in frozen
`source-build-06`. It does not release footprint poses, a routed board,
mounting holes, an insulation system, or an assembly. Coordinates use the
component-side datum in `BOARD-MECHANICAL-ENVELOPE.md`: upper-left board
corner `(0, 0)`, `x` right, `y` down, millimetres. Angle is the KiCad
footprint orientation in degrees. References and source paths were checked
against `source-build-06/build/default.net` (SHA-256
`913a0bf51726cb756af2384aea3ac2c949c405f612b345aedbae7ef4c0d79796`).
The source receipt is
`a164f33463b42748eefd4474be5f225077e191eae2378448eccad69b932b3d36`.

## First-pass anchors

These are approximate origin positions to test in a native board. They
reuse some diagnostic poses and move no source pins. Bounding dimensions
mentioned below come from the temporary KiCad 10 board, whose existing
footprints remain under review. A dimension from that board is a collision
screen, not an enclosure or electrical clearance.

| Reference | Source instance / function | Proposed `(x, y, angle)` | Placement reason and next check |
| --- | --- | --- | --- |
| U238 | `ac_input.board_input`, fused L/N/PE terminal | `(27, 42, 0)` | Left wire-entry zone. Its present body/graphics bounding box reaches about `x 22–51`; confirm clamp access, conductor exit direction, PE termination and off-board F1 harness. |
| U240 | `ac_input.aux_branch`, AUX branch terminal | `(28, 153, 0)` | Separate left-side branch termination. Verify the off-board branch protection, conductor exit, loop routing and separation from fused mains entry. |
| U239 | `ac_input.cmc` | `(65, 63, 0)` | Near U238 while allowing the present roughly 51 × 29 mm envelope. Verify line/load pin direction, CMC field coupling and X/Y capacitor paths. |
| U242 | `ac_input.ntc` | `(91, 111, 0)` | Below CMC, before the relay/rectifier approach. Check hot-body spacing and bypass loop. |
| U243 | `ac_input.bypass` relay | `(112, 145, 0)` | At the input/PFC boundary; check contact routing, coil separation and cover height. |
| U223 | `pfc_power.bridge` | `(95, 42, 0)` | Adjacent to the conditioned AC path and left of the inductor. Verify bridge pin order, tab/heatsink and rectified-current return. |
| U224 | `pfc_power.l_boost` | `(180, 74, 0)` | The installed footprint is about 97 × 97 mm, spanning approximately `x 132–229, y 26–123` at this pose. Reserve field, airflow, mounting and service space; do not route sensitive control under it without review. |
| U136 | `driver.stw`, PFC boost switch | `(190, 132, 0)` | South of the inductor, near boost driver. The TO-247 outline omits heatsink and attachment space. |
| U225 | `pfc_power.d_boost` | `(211, 132, 0)` | Near switch and local reservoir; TO-247 tab/cathode and heatsink isolation require physical review. |
| U241 | `ac_input.raw_aux`, IRM-20-24 | `(25, 190, 0)` | Lower-left HOT supply zone. The temporary board body/graphics reach about `x 21–74, y 186–214`; confirm the 24 mm height, AC input pin orientation, thermal environment and branch lead access. |
| U229 | `pfc_power.local_c`, 22 µF film | `(182, 154, 0)` | Local VD reservoir near U225 and U227. This shifts it about 4 mm right of the diagnostic shelf pose to give the adjacent bank more room; recheck the actual courtyard, solder access, high-current loop and vent path. |
| U230 | `pfc_power.hf_c`, 0.47 µF film | `(180, 185, 0)` | Local high-frequency path; pad polarity/net assignment and loop inductance determine its final location. |
| U231, U232 | `pfc_power.bulk1/2`, 560 µF each | `(112, 171, 0)`, `(150, 171, 0)` | First row of 35 mm diameter snap-in capacitors. Their temporary bounding boxes are roughly 37 mm wide; this leaves only about 1 mm between graphics at these origins. Increase pitch after vent, sleeve, solder and tolerance review. |
| U233, U234 | `pfc_power.bulk3/4`, 560 µF each | `(112, 212, 0)`, `(153, 212, 0)` | Second row. Check bottom-edge margin, capacitor vent and the proposed `(180, 238)` support point before either is fixed. |
| U227 | `pfc_power.f2_vd_stud`, `VD_LOCAL` | `(214, 185, 0)` | First of two separate Würth studs. Reserve a lug and insulated cable path toward the off-board F2 holder within the HOT region. |
| U228 | `pfc_power.f2_vb_stud`, `VB_BANK` | `(214, 220, 0)` | Second stud, 35 mm nominal origin spacing from U227. Exposed metal, lugs, insulation boots, fastener tool swing and actual F2-open voltage set the required separation. The 35 mm is not an accepted clearance. |
| U1 | `receiver.iso_protocol`, ISO7741F DWW | `(252, 65, 180)` | Cross the `x 235–270` corridor with HOT pads on the left and SELV pads on the right, as verified from the temporary board pad nets. |
| U44 | `receiver.iso_feedback`, ISO6742F DWW | `(252, 105, 180)` | Same side assignment as U1; 40 mm nominal center spacing leaves a region for separate inspection of each constructed path. |
| U287 | `source_mcu.controller_port`, 16-contact Micro-Fit | `(315, 90, 0)` | Right-side SELV zone. The current footprint reaches about `x 311–340`; review vertical mating access, keyed mate, harness bend, strain relief and unplug access in the real enclosure. |

`U226` is the off-board F2 assembly-only source instance and must not be
placed on this PCB. F1 is likewise off board in the fused input harness.
The diagnostic shelf placed the X2/MOV/Y1 devices `U244/U245/U246` near
the top-left board edge, outside the intended input zone and near proposed
support hardware. This proposal deliberately leaves them unanchored until
the line/neutral/PE paths and surge or Y1 separation are laid out together.
All other small devices also remain unplaced in this proposal.

## Placement restrictions to carry into native review

- Treat `x 235–270, y 18–232` as an **isolation reservation**, not a
  certified keepout. Only the two selected DWW crossings are proposed there.
  Their opposed-pad copper gap is 15.2 mm nominal, below the provisional
  16.0 mm Group IIIa board-surface screen. No pose can repair that; a
  constructed slot, accepted laminate/material path, or changed land
  pattern and the final insulation schedule are needed. Keep mounting
  hardware, ordinary copper, test points and cable paths out while that
  decision is open.
- Reserve the left-edge approach to U238 and U240 and the right-side
  connector approach to U287 from tall components and support hardware.
  These are access reservations with no released bend-radius dimension.
- Keep both F2 conductors, exposed studs and service tools within the HOT
  region. Their center spacing does not set an electrical minimum. Review
  cable exit, torque, fault pulse, copper/PTH current path, insulation boot
  and hot-to-SELV proximity as one assembly.
- Do not install the six proposed supports at `(12,12)`, `(180,12)`,
  `(348,12)`, `(12,238)`, `(180,238)`, `(348,238)` yet. The `(180,238)`
  point is especially close to U234's current envelope. Hole diameter,
  washer sweep, grounded/accessibility status and board deflection are
  unknown; moving supports may require changing the capacitor bank.
- Keep the U224 magnetic envelope, U136/U225 heatsink sweep, U241 module
  height and U231–U234 capacitor vents as explicit 3D review volumes.
  Current footprint courtyards do not represent all these volumes.

## What would promote an anchor

Verify the actual mating connectors, wire exits, cable and tool sweeps and
the enclosure/support fit; select laminate, stackup and insulation rules;
then place the anchors on a saved native candidate and check the full
footprint geometries in 2D and 3D. Rework coordinates until the complete
295-reference layout has reviewed poses. Source/native pin parity, DRC,
routing, thermal/current qualification and measured fault responses follow
on that joined candidate. This note alone satisfies none of those gates.
