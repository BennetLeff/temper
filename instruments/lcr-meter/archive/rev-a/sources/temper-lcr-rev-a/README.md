# Temper LCR meter — revision A engineering prototype

A complete **single 80 × 65 mm PCB** USB bench impedance instrument for isolated, discharged stage53 components. The board includes the source, analog measurement path, converter, clock, USB interface and power supplies. A computer runs the included Rust CLI; no second evaluation board or user-programmed firmware is required.

**Status:** schematic and routed PCB complete; native KiCad ERC, DRC and schematic parity pass with zero findings. BOM and fabrication outputs are generated and checked. This is an **unbuilt engineering prototype**, not a calibrated or production-qualified instrument. JLCPCB's component orientation preview has not been checked; the CPL includes per-part LCSC EasyEDA orientation corrections, and the final JLC placement preview must still be checked before assembly approval. No order has been placed.

## Start here

- `previews/schematic.pdf` — complete circuit.
- `cad/temper-lcr.kicad_pro` — editable KiCad project, with local symbols/footprints.
- `manufacturing/gerbers/` and `manufacturing/temper-lcr-gerbers.zip` — actual four-layer copper, mask, silk, outline and drill outputs.
- `manufacturing/bom-jlcpcb.csv`, `cpl-jlcpcb.csv` — 45 top-side assembly placements; six headers are hand fitted.
- `manufacturing/bom-complete.csv` — 51 PCB components, exact manufacturer/MPN/LCSC and catalog price snapshot.
- `manufacturing/FABRICATION.md` — stackup, ordering and orientation review requirements.
- `host/README.md` — operation, sweep/calibration commands and software limitations.
- `docs/circuit-review.md`, `docs/bring-up.md`, `docs/cost-and-upgrades.md` — engineering rationale, qualification and costs.
- `validation/` — independent native checks, CAD/BOM parity and limited analog simulation.

## Useful stage53 measurements

| Component/test | Planned use | Limitation |
|---|---|---|
| Coil with/without pan | Complex impedance and equivalent series L/R at 35–60 kHz | Small-signal response only; no power-level loss or saturation prediction |
| Five 100 nF resonant capacitors, separately or as 0.5 µF bank | Capacitance, impedance and relative loss comparisons | ESR accuracy must be established against standards; no milliohm claim |
| 9 µF bus capacitors | Experimental lower-frequency capacitance check around 1–3 kHz | 35–60 kHz impedance is below the intended 5 Ω floor; high-frequency ESR unsupported |
| Chokes and snubber/gate capacitors | Compare winding impedance, L/C and gross faults where the selected range applies | Lift a lead or disconnect parallel paths; no insulation/voltage-rating test |
| 1 mΩ current shunt | Not supported | Requires a separate DC four-wire measurement architecture |

The stage53 identity used for this purpose is `worktrees/runs-native21/s53/c53int/section.kicad_pcb`, SHA256 `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`. This project does not alter or release that power-stage board.

## Architecture and range

AD5933 coherent source/ADC/DFT → AD8606 buffered source and transimpedance measurement → MCP2221A factory USB HID/I²C bridge. External 16 MHz oscillator, 0.198 Vpp nominal source setting, two 3.3 V rails. The measurement terminals have approximately 1.65 V common mode relative to USB ground. Neither DUT terminal is ground. This is a two-terminal instrument with fixture calibration, not a four-wire Kelvin meter.

Fit exactly one jumper with USB unplugged: JP1/r20 5–50 Ω; JP2/r200 50–500 Ω; JP3/r2k 500 Ω–5 kΩ; JP4/r20k 5–50 kΩ. Main qualification band is 10–100 kHz, especially 35–60 kHz. The r20 1–10 kHz extension is experimental because the fixed-clock DFT record contains few cycles. All ranges are design targets pending physical validation.

The integrated ADI converter keeps the source, acquisition and USB interface on one board. This is a new design rather than a TI TIDA-060029 port. It controls cost and complexity, with less room for future bandwidth and independent simultaneous V/I acquisition than a larger discrete instrument. It does not reproduce TI's accuracy claims.

## Reproduction

Electrical/placement truth is `cad/design.json`; explicit routed segments/vias/zones are `cad/routing.json`. `cad/build_cad.py` is a thin native pcbnew adapter, not an electrical inference engine. KiCad 10.0.4 and its installed standard footprint library were used; project-local resolved footprints and symbols are included. Run `cad/rebuild.sh` from this directory with `KICAD_PYTHON` pointing to a Python with pcbnew. Set `RENDER_PYTHON` to an environment containing pygerber2.4.3 and cairosvg2.9.1; install Poppler for pdftoppm. It regenerates CAD, fills zones, fails on native ERC/DRC findings, exports manufacturing files and validates BOM/placement parity. On this macOS host, native KiCad requires normal desktop permissions; the sandbox font subsystem crashes independently of design validity.

Hardware remains untested. Complete the bring-up and third-standard checks before using reported values to accept or reject stage53 parts.
