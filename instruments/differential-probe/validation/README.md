# Validation scope

`make all` completed with KiCad 10.0.4 on 2026-10-20.

- ERC: 0 errors, 0 warnings under the installed KiCad defaults. The report lists the default ignored categories: single-use global labels, four-way junctions, SPICE model issues and footprint-filter matching. No per-violation waivers were added to this project.
- Exported XML netlist: 364 pins in 88 connectivity groups match the authoring intent, including NC pins. This checks wire/label serialization; agreement with generated intent alone does not prove circuit correctness.
- Selected critical datasheet pin and polarity assertions passed separately from placement generation.
- All 140 symbols have exact MPN fields. The 135 board footprints have matching pad-number sets; five parts are explicitly offboard. The former two DNP compensation positions are removed; both new fine trimmers are populated.
- Divider ratio, trim corners, nominal filter pole, rail setpoints and overload thresholds were calculated, not measured. See `checks.txt`.
- All three PDF sheets were inspected visually through multiple placement revisions. Checks covered readable references/values, supply direction, passive chains, block boundaries, feedback and clamp connectivity, and the final title blocks. SVG exports are supplied alongside the PDF.

## Nominal low-voltage simulation

`make simulate` uses the archived, unmodified TI OPA810 Rev A model with ngspice PSpice compatibility. It predicts 5.55 MHz wide / 5.09 MHz fine bandwidth and exercises unused fine-stage saturation while observing the wide path. The fixture uses ideal supplies and buffered input sources; HV divider/buffer response, physical coupling, clamps and switch transitions are excluded. The model reports clipping slightly outside its supply rails, so those clip levels are not physical predictions. See `spice/results.txt` and the detailed [circuit record](../docs/circuit-revb.md).

## PCB verification

`make pcb-check` completed with KiCad 10.0.4 on 2026-10-20. The saved board has 148 physical footprints, including explicit wire landings and six mounting holes. All 365 unique physical electrical-pin mappings match the exported schematic or the documented offboard landing map. Duplicate switch pads were checked individually. Circuit values, selected footprint names and DNP states match the schematic.

- Native DRC: three runs on the identical board each report zero violations and zero unconnected items with `--all-track-errors` and the generated voltage-dependent clearance/creepage rules. No per-item exclusions are present. Default ignored categories remain recorded in `pcb-drc.json`: missing courtyard, track endpoint centering on vias, tuning-profile geometry, footprint filters and component/pad type matching. Missing courtyard is relevant to the custom wire landings; their wire/strain-relief envelopes are assembly constraints, not validated component courtyards.
- Native geometry: 31 paired footprints / 70 electrical pad pairs have identical dimensions, orientation and positions after a 35 mm translation. Twelve paired divider/tap/input nets have identical track/via geometry. All elevated ladder nodes remain on F.Cu without vias. The two buffer-output-to-input-resistor paths are both 53.135 mm on F.Cu.
- Negative controls: adding a GND trace with 1.875 mm spacing to TIP_P triggers the 10 mm air-clearance rule; removing the C1 slot triggers the 4 mm surface-creepage rule at 2.70 mm. An isolated opposing-tip fixture with 20.5 mm edge spacing passes the revised 10 mm air / 20 mm surface rules; an 8 mm fixture fails both. This demonstrates that both rule types are active and exercises the compact envelope. The malformed fixtures are confined to ignored `build/drc-oracle/`.
- Voltage-envelope arithmetic: every pair of node ranks is maximized independently over the allowed input hexagon; opposite-leg spacing uses the larger rank and excludes 6 kV opposing-tip operation.
- Visual review: all four copper layers, assembly/silkscreen and the 3D component render. The shield, wiring and panel parts are not present in the 3D assembly.

See `pcb-checks.txt`, `pcb-drc.json`, the three `pcb-drc-1.json` through `pcb-drc-3.json` repeat reports and `pcb-drc-repeatability.txt`, `pcb-drc-oracle.txt` and `pcb-sha256.txt`. The hashes identify the board, project, custom rules and schematic netlist used for the recorded checks. `pcb-pads.tsv`, `pcb-footprints.tsv` and `pcb-tracks.tsv` are exported from the saved native board, rather than copied from the authoring source.

The checks establish the recorded PCB geometry and connectivity. They do not establish analogue stability, CMRR, noise, bandwidth, component-body insulation, a qualified voltage/CAT rating, production process suitability or measurement uncertainty. See `../docs/layout.md` for the spacing assumptions and `../docs/qualification.md` for the unexecuted bench plan.

The original scratchpad model is preserved under `../evidence/`. Its SHA-256 is `18167c06852423cbb510e8edf252a72c5f6b13fedd50ea905a778a45271b2735`. It is historical evidence, not a test of the complete schematic.
