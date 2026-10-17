# Task 04, second simulation round — topology blocked

**Verdict: BLOCKED for board current and temperature results.** The four
starter-solver defects reported in the [first round](../README.md) are fixed:
all seven current analytic self-tests pass, including 0.5811 mΩ through-via and
2.8996 mΩ unequal-source cases. The complete kit smoke test passes 16/16.
The corrected solver is SHA-256
`349faeacc92e7466acf26ffdf877684211083a6cef0590417d7480c22356c5c2`.

At the required 0.25 mm pitch, the solver joins neighbouring cell centres
without checking whether the edge between them crosses noncopper. A synthetic
pair of strips with a 0.20 mm gap is incorrectly accepted as a 0.1307 mΩ
conduction path. This is present on the **actual native-13 board**: two BUS_P
vias at `(68.5, 54.8)` and `(68.5, 56.6)` mm have 1.6 mm outer diameter
and 0.8 mm drill diameter,
leaving a 0.20 mm gap on F.Cu and In1.Cu. The grid joins cells at
`(68.344932, 55.575)` and `(68.344932, 55.825)` mm. Their midpoint is in the
gap, and the exact KiCad polygons place the endpoints in separate physical
copper components on those layers. Two raster edges do this on each layer.
The vias connect elsewhere through the In2.Cu BUS_P plane, but the artificial
F.Cu/In1.Cu shortcuts alter resistance and via current sharing.

The [raster audit](outputs/raster_topology.json) counts **70** adjacent graph
edges whose midpoint crosses a real copper void across the seven power nets
and four layers; **four** of those cross separate physical components (the
BUS_P pair above). The others include drill-hole crossings. This is a
necessary-condition audit; it does not prove that the remaining graph edges
are all physically valid. It uses actual pad and filled-zone polygons from
KiCad, track widths, and drilled voids. Native-13 board SHA-256:
`8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`.

There is a second modeling gap at drilled contacts. The centre of a plated
through-hole pad or via is a void in each copper sheet. The specified
pad-centre injection and `add_via()` call use that point as a sheet node;
the kit cannot do this while retaining a physical annulus. Q2.2, Q5.2,
C38.1–C41.1 and the BUS_P via above all fail the exact-copper centre check
in the audit. They need a distributed contact around the annulus, with barrel
conductance attached to those contact cells. Filling the drill with copper
would make the network artificially conductive.

These are **exact structural** findings about board geometry and a
**simulation-instrument** finding about the raster graph. They are not
measured electrical or thermal results. This round reports no native-13 path
resistance, loss, via current, current-density peak, or Joule temperature
rise. Task 03's `board_heat_sources.json` is also absent, so total board
temperature remains open independently of the solver repair.

The next solver revision should preserve polygon holes when adding layers,
retain only graph edges whose full cell-centre segment and shared face lie in
copper, represent drilled annuli and barrel contacts, then
pass the specified 0.5/0.25/0.125 mm resistance-convergence check on a board
net. The Joule-only thermal model still needs its analytic heated-strip check
before applying the 20 °C criterion. No shared kit or board files were edited
in this round.

## Reproduce

From `zapote/power-stage-120v/`, with KiCad 10's Python and Miniforge Python:

```sh
/Users/bennet/Miniforge3/bin/python3 validation-plan/sim-kit/smoke_test.py
/Users/bennet/Miniforge3/bin/python3 validation-plan/sim-kit/04-current/sheet_solver.py --selftest
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 validation-results/04-board-current-thermal/round2/scripts/extract_power_copper.py native-13/section.kicad_pcb validation-results/04-board-current-thermal/round2/inputs/power_copper.json.gz
/Users/bennet/Miniforge3/bin/python3 validation-results/04-board-current-thermal/round2/scripts/audit_raster_topology.py validation-results/04-board-current-thermal/round2/inputs/power_copper.json.gz validation-results/04-board-current-thermal/round2/outputs/raster_topology.json
```

The committed raw input is [power_copper.json.gz](inputs/power_copper.json.gz)
and the run receipts are in [outputs](outputs). The extractor's input is the
committed board and it records that board's hash. The prior failed-solver
evidence remains intact in the parent folder.
