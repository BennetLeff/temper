# Rev B compact PCB handoff

The canonical routed board is `cad/differential-probe.kicad_pcb`. Final size is **240 × 84 mm**, versus Rev A's 240 × 120 mm: **30% less PCB area**. This includes the added compensation trimmers and ×5 stage. It does not claim half the enclosure volume; shield setbacks and panel/battery packaging still determine the enclosure.

The divider resistor rows are y = 20 and 55 mm, a 35 mm translation. Their HV, tap, low-leg bank, clamp and buffer geometry remains matched. Custom rules now apply the simultaneous limits `|TIP_P| ≤ 3 kV`, `|TIP_N| ≤ 3 kV`, and `|TIP_P − TIP_N| ≤ 3 kV`. Across opposite legs, the maximum voltage for ranks a,b is `300 V × max(a,b)`, rather than their sum. Full opposing tips therefore require 10 mm air clearance / 20 mm PCB creepage under this prototype budget. **6 kV opposing-tip survival is no longer claimed.** Intact distributed voltage sharing is still an assumption; neither DRC nor the new rule arithmetic establishes an instrument safety rating.

`tools/check_pcb.rs` independently maximizes the linear node-voltage difference over all six vertices of the allowed tip-voltage hexagon, for every pair of ranks. Native opposing-tip fixtures verify both directions: a 20.5 mm copper-edge gap passes the new rules (and would fail the old 40 mm creepage requirement), while an 8 mm gap fails both air and surface constraints. Existing too-close-ground and missing-slot negative controls also pass their assertions.

The layout places the fixed ×2 subtractor U3 at (163,38), rotated 180°, and the ×5 stage U12 at (188,25). Rotation puts the subtractor input order in the correct physical order for two F.Cu wanted feeds. Native F.Cu shortest-path extraction reports **53.135 / 53.135 mm** from U1.6 to R61.1 and U2.6 to R62.1, respectively. The following resistor-to-U3 input traces have matching geometry by reflection. This controls one source of mismatch; component, shield, reference and distributed capacitance still require CMRR calibration.

U3's two-resistor feedback chain is local below the IC and returns directly on B.Cu. U12's feedback output return is also direct. R100 and R101, both 49.9 Ω, sit next to U3 at (154,34) and (154,45); the longer ×5-input and output-selector routes occur after those isolation resistors. SW1 is at (210,28), entirely outside amplifier feedback. R103 provides the selected-node DC return. The amplifier input keepouts follow the actual input side of rotated U3 and the added U12. In1.Cu remains an uninterrupted ground reference outside these intentional input voids; there are no hidden planes under the HV ladders.

Final mechanical positions, mm from the top-left board origin:

| Item | Position |
|---|---|
| CT1 tool axis | (138,38) |
| CT2 tool axis | (138,73) |
| H1 grounded M3 | (135,6) |
| H2 grounded M3 | (234,6) |
| H3 grounded M3 | (147,78) |
| H4 grounded M3 | (234,78) |
| H5 insulating support | (7,7) |
| H6 insulating support | (7,77) |

The trimmer courtyard is 7.5 × 7 mm; its rendered maximum body is 6.2 mm diameter and 5 mm high. H3 was moved away from CT2. A suggested 3 mm lid tool hole and insulated shaft no larger than 2.5 mm must be mechanically registered to each axis, with depth control and the shield's stated HV setback preserved. These are enclosure assembly constraints, not a completed housing design. Washer and lead envelopes must stay within the layout notes' mounting restrictions.

Final verification:

- 148 physical footprints; 365 unique physical electrical-pin mappings agree with the schematic and explicit offboard landings, including duplicate tactile-switch pads.
- 31 paired footprints / 70 paired pads have identical geometry under the 35 mm translation; 12 ladder/tap/input net pairs have identical native copper geometry.
- Three native KiCad 10.0.4 DRC runs on the same final board bytes each report **zero violations and zero unconnected items**. See `validation/pcb-drc-1.json` through `pcb-drc-3.json` and `pcb-drc-repeatability.txt`.
- The board, rules, project and netlist hashes are in `validation/pcb-sha256.txt`.
- All four copper layers and the 3D assembly were reviewed. The fixed trimmer models are now visible and clear of the DC trimmers and mounts. The PDF and render include the final resistor moves. There is no enclosure or wiring model.
- `tools/layout.rs` uses final Rev B coordinates directly; its obsolete Rev A cell-shift indirection was removed. Placement/reference/copper TSV outputs were checked byte-identical through that source cleanup.

No CMRR, bandwidth, stability, high-voltage, thermal or recovery bench test has run. The 70 MHz stages and their real load/switch/cable still need the stated low-voltage stability tests. The compact board and fixed shield need compensation together.
