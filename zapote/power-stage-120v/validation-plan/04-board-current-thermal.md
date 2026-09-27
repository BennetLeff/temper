# 04 — Board current density and copper temperature

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first. This task needs task 03's `board_heat_sources.json`. Without it,
run the copper self-heating part alone and mark the result partial.

## Goal

Replace the IPC-2221 width screens with a real solution of how current spreads
through all four copper layers and the vias, then estimate the resulting
copper temperature rise. The current screens are in
`native-09/verification/README.md` and `native-06/verification/power-review.md`.

The questions are:

- **Distribution:** Where does the current actually flow in BUS_P, HV_RET,
  LEG_RET, SW_A, SW_B and RES_A?
- **Hot spots:** What's the peak current density, and where are the hot spots?
- **Vias:** How much current does each via in each bank carry? The power
  review says via sharing is unknown.
- **Temperature:** What's the board temperature rise at full power, including
  component heat from task 03?

Evidence class: **simulation/model-based**. The physical test that confirms it
is IR-camera or thermocouple temperature rise at full power.

## Inputs

- Board `native-09/section.kicad_pcb`, and a copper census from
  `tools/copper_dump.py`.
- Copper thickness from `stackup.json`: 70 µm outer and **61 µm inner**
  (JLCPCB finished). Resistivity of copper is 1.68e-8 Ω·m at 20 °C with a
  +0.393 %/°C coefficient.
- Via plating: JLCPCB's 18 µm average (`FAB-JLCPCB.md`). Also run 12 µm as a
  pessimistic case.
- Current injection points and magnitudes:

| Net | Current enters/leaves at | Current |
| --- | --- | --- |
| `bus_p` | Western bus neck to the legs: C5/C6/J-links on the west to Q2.2/Q5.2 and C38–C41 | 15 A DC-equivalent rectifier replenishment, plus the HF commutation share (19 A assumed in the power review; take task 05's value if available) |
| `hv_ret` / `leg_ret` | Q3.3/Q6.3 sources → R5 pads 1/4 → bus caps and the west | Same as `bus_p` (return) |
| `sw_a`, `sw_b`, `res_a`, `coil_feed` | Q pins → T1 / C21–C23 / J2 / J5 | Tank current, 18.7 A rms |

Get the connection points from pad references in the census; don't guess
coordinates.

## Method

Install nothing new unless you must. The primary method uses numpy and scipy,
which are installed. The two existing single-layer solvers in
`native-06/verification/power-probes/final49-bus-sheet.py` and
`final49-hv-sheet.py` are the starting point: extend them to all four layers.

1. **Rasterize** each net's filled copper on each layer to a grid:
   0.25 mm, or 0.2 mm if memory allows. Use shapely `covers` as the existing
   script does, or a faster rasterizer (e.g. `rasterio.features` or
   matplotlib `Path.contains_points`).
2. **Build the resistor network:**
   - Each cell connects to its 4 neighbours on the same layer with conductance
     `σ·t` (sheet conductance, per square).
   - Each via connects the cells it overlaps on every copper layer it touches,
     with its barrel resistance `ρ·h/(π·((d/2+t)² − (d/2)²))`.
   - Through-hole pads are treated like vias.
3. **Solve** for the potentials with scipy `spsolve`. Inject the currents at
   the pads and set one sink as the voltage reference. For the AC tank
   current, a DC solve gives the resistive spreading only; note that skin and
   proximity effect at 35 kHz raise AC resistance. At 70 µm the skin depth at
   35 kHz is ~0.35 mm, so the layers are thinner than a skin depth and DC is a
   reasonable first approximation. Say this in the report.
4. **Outputs of the electrical solve:**
   - current-density map per layer (PNG)
   - top 20 hot cells
   - current in every via of each bank
   - total path resistance and I²R loss per net
5. **Thermal:**
   - Build a 2.5-D finite-difference model of the board as a stack of
     conducting layers: copper in-plane conductivity 390 W/m·K, FR-4
     0.3 W/m·K in-plane and through-plane.
   - Heat sources: the Joule heat from step 4, plus task 03's
     component heat at the footprint locations.
   - Boundary: convection h = 10 W/m²K (natural) on both faces, and a case with
     h = 25 W/m²K (light forced air). The heatsink-mounted parts dump their
     heat to the heatsink, not the board. Model only their lead/pad heat, and
     state this.
   - Output the temperature map, the maximum rise, and its location.
6. **Optional cross-check:** repeat one net with Elmer FEM (install via the
   official Elmer packages; stop if that fails twice) or a single-layer
   analytic check (a uniform strip of known width) to prove the solver is
   right.

## Validation of your solver (required)

Before the real board, verify the code on two cases with known answers:

- a uniform strip 10 mm × 50 mm, one layer: R = ρ·L/(w·t)
- two layers joined by one via at each end: the parallel combination

Include these as `scripts/test_solver.py`. Both must match the analytic
answer within 2 %.

## Acceptance criteria

| Check | Pass |
| --- | --- |
| Solver self-tests | Within 2 % |
| Peak copper temperature rise (Joule only) | ≤ 20 °C above local board temperature (the same basis as the IPC screen) |
| Peak board temperature (Joule + components, natural convection, 50 °C ambient) | Report it. **FAIL** if any part's local board temperature exceeds its rating: the R5 shunt, electrolytic-free film capacitors near hot copper, the ISO7710/UCC21550 ambient rating |
| Via current | Report the maximum per-via current and the via temperature rise. Flag any via > 3 A (a flag, not a fail; there's no rated limit) |
| Consistency | Compare with the IPC screen ratios in `native-09/verification/README.md`. Explain large disagreements |

## Deliverables

In `validation-results/04-board-current-thermal/`:

- `README.md`
- `scripts/` (the solver, test, and plots)
- `outputs/current_density_<layer>.png`
- `outputs/via_currents.json`
- `outputs/temperature.png`
- `outputs/summary.json`

## Pitfalls

- Filled-zone polygons in the census can contain holes. The earlier review
  found the dump's polygon approximation fills holes. Check this with
  `native-06/verification/power-probes/copper_zones_with_holes.py` run under
  KiCad Python, and subtract the holes.
- Different nets on the same layer must never share cells. Rasterize per net.
- Memory: a 240 × 160 mm board at 0.2 mm on 4 layers is ~3.8 M nodes, and
  sparse solves at that size may be slow. Solve only the region of each power
  net, or use 0.25–0.3 mm.
