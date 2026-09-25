# Würth 74651173R stud footprint screen

Status: **selected in source-build-05 as a review-only engineering footprint;
native board and physical acceptance OPEN** (2026-09-24).

The frozen `source-build-05` candidate uses **two separate**
[Würth 74651173R REDCUBE THR studs](https://www.we-online.com/components/products/datasheet/74651173R.pdf),
one for `VD_LOCAL` and one for `VB_BANK`. Historical `source-build-04`
used one Phoenix 1017526 four-pin terminal. The
[review-only KiCad footprint](../../libraries/temper.pretty/Wurth_74651173R_ReviewOnly.kicad_mod)
is selected for evaluating the separate-stud layout; it is not a released
fabrication footprint or physical F2 assembly approval.

## Manufacturer land pattern and representation

The Würth datasheet, page 1, specifies four holes on a **5.87 × 5.87 mm square** with **Ø1.85 mm holes** and **Ø3.2 mm solder lands**. Relative to the center of the grid, the footprint places the four centers at `(±2.935, ±2.935)` mm. All four physical posts are one electrical potential, so all four KiCad pads use logical pad number `1`. `source-build-05` has two one-pin instances; the 145-test Rust audit and strict native preflight check their exact VD/VB assignment and repeated-pad mapping. The historical four-pin Phoenix export cannot be silently rebound to these pads.

The nominal land annulus is `(3.2 − 1.85)/2 = 0.675 mm`. The furthest land edge is at `±4.535 mm` on both axes. The `F.Fab` square is 7.0 mm on each side, following the nominal square body dimension in the page-1 drawing. The `F.CrtYd` square extends to `±5.1 mm`, leaving a **0.565 mm nominal margin** beyond the copper land extrema. That courtyard is only a board-placement screen: it does not include a washer, lug, insulation boot, tool swing, wire bend, or strain relief. No 3D model or physical fit has been checked.

## Qualification boundaries

The datasheet states a **1.6–2.0 mm PCB thickness** range, **0.5 N·m tightening torque**, and **50 A maximum at 20 °C** with operating current dependent on the board, cable lug and cable cross section. It recommends reflow soldering and says wave soldering is not applicable. These are part properties and instructions, not an installed current or fault rating for the F2 assembly.

Before physical release, define the lug, cable, insulation, washer/nut stack,
fastening and strain relief; verify body and tool clearance in 3D and on a
sample; qualify pad/PTH/copper temperature and mechanical torque on the
chosen stackup; establish working-voltage, creepage and clearance between
the two exposed studs and to other conductors; and establish the F2
prospective fault and let-through waveform. The datasheet does not provide
an installed insulation approval or a DC short-time withstand basis for the
assembled path. Keep those gates open.

## Digital verification receipt

`kicad-cli 10.0.4 fp export svg --footprint Wurth_74651173R_ReviewOnly --layers F.Cu,F.SilkS,F.Fab,F.CrtYd` parsed and exported the footprint on 2026-09-24. The SVG lists four circular copper pads at the expected 5.87 mm center spacing. This verifies KiCad syntax and nominal pad placement. Native board DRC, solder-mask/annulus manufacturing review, visual 3D inspection and physical assembly tests are **NOT RUN**.
