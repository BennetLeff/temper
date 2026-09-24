# Rev38 section-board insulation basis — unresolved layout input

**Status: candidate screen, not an accepted IEC/UL construction or native
DRC rule set (2026-09-24).** This record is for the Rev38 source-to-PFC
section board. The cooker inverter and its legacy midpoint are outside this
board. A default KiCad DRC pass cannot close this gate.

## Scope and governing assumptions

- Installation proposal: 108–132 V ac, 15 A rms, general residential cooker.
  The product classification remains to be selected: IEC 60335-2-6 covers
  stationary hobs, while IEC 60335-2-9 covers portable cooking appliances.
  Both use IEC 60335-1 as the general appliance standard; neither has been
  signed off as the product's certification basis.
- Use overvoltage category II and pollution degree 3 for the layout screen.
  The existing cooker construction is vented and has no earned sealed,
  pollution-degree-2 compartment. This is the project's recorded PD3
  decision in `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`,
  not a claim that a Rev38 enclosure has been qualified.
- Treat every SELV-to-HOT crossing, including isolators, Y capacitors,
  connector-adjacent copper, and any other galvanic path, as a reinforced
  insulation candidate. The existing cooker ESP is the SELV command source;
  its ground/PE reference does not turn HOT0 into SELV.
- FR-4 material group IIIa is the existing project screen; actual laminate
  CTI and board construction remain to be specified. The values below are
  taken from the project's recovered IEC 60335-1 Table 17 in
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.1. The current IEC edition,
  particular standard, national adoption, and certification interpretation
  still require a product-safety review.

## Voltage-row decision

The PFC controller screen in
`../ARCHITECTURE-REDUCTION.md` gives 389.615 V nominal and **409.307 V
maximum static regulation**. The latter is a possible operating voltage,
not merely a brief fault spike. Therefore the legacy cooker's >250–400 V
Table 17 row cannot be copied to the Rev38 bank barrier. With 409.307 V dc,
the project's >400–500 V row gives **8.0 mm basic / 16.0 mm reinforced
creepage at PD3 for Group IIIa/IIIb board material**. A separately
qualified **Group I package surface** reads 6.3 mm basic / **12.6 mm
reinforced** in that row. Do not impose the FR-4 column on the package or
credit the package's CTI to the surrounding board. No interpolation or rounding
409.307 V down to 400 V is permitted. Any regulated, ripple, startup, or
fault voltage above 500 V would require another row and a new decision.

This is a provisional *layout floor*, not an accepted maximum voltage:
`VD_LOCAL` may differ from `VB_BANK` across F2, and the independently
derated VD, VB, switch and diode limits, ripple, overshoot, and fault
waveforms are still open in `timing-analysis.md`. The 22 µF VD local
reservoir and 2,240 µF VB bank are distinct components on opposite sides
of F2.

| Pair / path | Proposed insulation treatment | Working-voltage input | Rev38 layout status |
| --- | --- | --- | --- |
| AC L/N to SELV or accessible SELV-connected copper | Reinforced candidate | 132 V ac input plus installation transients; use the applicable appliance table's RMS/impulse method | Numeric creepage and clearance pending selected product standard and surge basis. Do not borrow the bank's DC row without analysis. |
| VB_BANK or VD_LOCAL to SELV | Reinforced candidate | At least 409.307 V dc static on the controlled bank; VD fault/ripple ceiling unaccepted | 16.0 mm PD3 creepage on Group IIIa/IIIb FR-4; 12.6 mm on a separately qualified Group I package surface in the same row. Air clearance, solid insulation and overshoot require separate derivation. |
| HOT logic/AUX/gate nets to SELV | Reinforced candidate | Common-mode potential follows HOT0 and AC/DC stage state | Apply the worst crossing voltage, including the bank where coupled or reachable. Pin-group and conductive-path review pending. |
| VD_LOCAL to VB_BANK across F2 | Functional / fault separation candidate | F2 open-circuit voltage and transient not yet bounded | No released creepage/clearance. The 1017526 terminal's own rating does not prove PCB solder-land spacing. |
| AC L/N to HOT0, rectified nodes, or other HOT conductors | Functional/basic classification pending fault and accessible-part analysis | 132 V ac and rectified/surge states | Numeric rules pending; 15 A copper, fault current, and F1 coordination are separate gates. |
| Within SELV or within one HOT control group | Functional candidate | Actual maximum differential per net pair | Normal electrical clearance and manufacturability still required; no blanket safety-barrier exemption. |

## Component obstruction and release condition

The joined source selects `ISO7741FDWR` and `ISO7742FDWR`. TI's ISO774x
DW datasheet specifies **>8 mm external package creepage and clearance**,
and Group I package material. The project's provisional PD3 >400–500 V
Group I reinforced-creepage screen is **12.6 mm**, so the selected DW
package has no demonstrated margin even before solder lands and nearby
copper are checked. A PCB rule cannot make an intrinsic package path
longer. Do not mark U7 native DRC or insulation PASS merely by spacing the
rest of the board. A qualified wider package may be feasible: TI lists
>14.5 mm external creepage for ISO774x-Q1 DWW variants, which would exceed
the provisional **package** screen, but its exact channel direction,
fail-low option, approval, pin map, pad geometry and adjacent Group IIIa
board path must be rechecked before substitution. A reviewed slot/path
interpretation is another possibility. The Y1 capacitor,
relay, AUX supply, controller connector, and any other crossing require
the same path-by-path check.

Before creating `native/section.kicad_dru`, the integration owner must:

1. Select the product standard and edition, insulation grade and applicable
   working-voltage/impulse method with product-safety review.
2. Bound VD and VB working/ripple/overshoot and the F2-open state, and record
   the worst potential for each net/pin group on both sides of the barrier.
3. Choose devices and board construction whose complete external paths can
   meet the resulting creepage, clearance, and solid-insulation requirements.
4. Encode every classified net pair in the native KiCad rules and run an
   executable source/netclass-to-rule coverage check with a deliberate
   reduced-rule mutation. A default-rule ERC/DRC pass is insufficient.
5. Review the actual routed board, component bodies, slots, coatings,
   solder lands and assembly tolerances. Hipot and physical construction
   qualification remain NOT RUN under this plan's digital deliverable.

No `section.kicad_dru` is emitted from this candidate table because the
voltage and component decisions above are unresolved. This is an explicit
U7 digital blocker, not an accepted rule omission.

## Source trail

- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.1 and
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3.3:
  recovered IEC 60335-1 Table 17 rows and PD3 Group IIIa/IIIb and Group I
  values.
- `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`: PD3 decision
  for the vented cooker construction and OVC II appliance basis.
- `docs/evidence/2026-08-12-hv-clearance-adequacy.md`: separate clearance
  derivation; the old cooker's clearance table is flagged as unsourced.
- [IEC 60335-1:2020](https://webstore.iec.ch/en/publication/61880),
  [IEC 60335-2-6:2024](https://webstore.iec.ch/en/publication/99834), and
  [IEC 60335-2-9:2019](https://webstore.iec.ch/en/publication/61318):
  official scope records; full current clause/table review remains open.
- [TI ISO774x DW data sheet](https://www.ti.com/lit/ds/symlink/iso7741.pdf):
  selected package external insulation geometry.
