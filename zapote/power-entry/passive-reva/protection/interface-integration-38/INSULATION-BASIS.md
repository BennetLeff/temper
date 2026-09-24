# Rev38 section-board insulation basis — unresolved layout input

**Status: candidate screen, not an accepted IEC/UL construction or native
DRC rule set (2026-09-24).** This record is for the Rev38 source-to-PFC
section board. The cooker inverter and its legacy midpoint are outside this
board. A default KiCad DRC pass cannot close this gate.

## Scope and governing assumptions

- Installation proposal: 108–132 V ac, 15 A rms, general residential cooker.
  The recorded detachable-cord, plug-in countertop construction makes
  **IEC 60335-2-9 the leading particular-standard candidate**: IEC lists
  portable cookers, hotplates and induction wok hotplates in its scope.
  IEC 60335-2-6 is the stationary-appliance alternative if the intended
  installation changes. IEC 60335-1 supplies the general requirements.
  A product-safety review must still select the exact edition, national
  adoption and applicable clauses; scope fit alone does not approve the
  insulation table or a Rev38 construction.
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
rest of the board.

### Exact wider-package screen (not a source substitution)

TI's 2026-02 package-option addendum lists the active, production
`ISO7741FQDWWRQ1` (3 forward / 1 reverse, fail-low) in DWW-16. It lists
`ISO7742FQDWRQ1` only in DW-16: the family's DWW insulation table does
**not** establish that a fail-low, 2/2 ISO7742 DWW can actually be ordered.
For the second 2/2 device, TI lists active, production
`ISO6742FQDWWRQ1`. Its datasheet specifies fail-low outputs, the same 2/2
signal pin positions as the selected ISO7742FDWR, Group I package material
and >14.5 mm external package creepage and clearance. It supports the
candidate 3.3 V SELV / 5 V HOT rails. `ISO7741FQDWWRQ1` plus
`ISO6742FQDWWRQ1` is an exact wider-package pair for review, **not** a
drop-in insulation approval or a changed Rev38 BOM.
Both TI insulation tables state **pollution degree 2** for their component
certifications. Their >14.5 mm physical path and Group I CTI do not by
themselves certify use in the proposed PD3 appliance construction. That
application needs an accepted enclosure or component-insulation argument.

The DWW datasheet's *optimized* land-pattern examples give only
14.5–15.2 mm between opposed pads. Its ordinary DW package example is
smaller still; **the DWW footprint must be used**. On the project's
provisional Group IIIa FR-4 screen, even the optimized DWW examples do not
themselves demonstrate the 16.0 mm reinforced **board** creepage. A reviewed
slot, qualified Group I laminate, or another constructed path may be needed.
The physical path must be measured from the closest exposed solder or copper
edge, including solder spread, vias, planes and nearby unrelated nets, not
from package body or pad centers. A solder-mask bridge is not credited as
solid insulation without a specifically qualified construction.

The ISO6742F specifies up to 0.3 µs from **input** VCC falling below 1.2 V
to its default output, while ISO7741F uses a 1.7 V threshold. Actual time
through the intermediate rail region is unbounded here. The ISO6742 also
specifies up to 300 µs from undervoltage lockout to valid data on startup.
These are device conditions, not an installed response bound. Retain local
default-low loads and qualify the actual rail sequence. The alternate
`ISO7841FDWWR`/`ISO7842FDWWR` pair has a 9 µs maximum input-power-loss
default delay at its specified threshold, so it is not a timing-equivalent
substitution. The provisional `ISO7741_DWW16.kicad_mod` under
`elec/qualification` has unsuitable candidate pad geometry; a native DWW
footprint needs a new official-land-pattern and assembled-copper review.
Before changing the source, compare both candidates' enable/power-loss
behavior, input/output drive, supply budget, timing, pad-to-pad path, exact
footprint and certification scope on the joined circuit. The product safety
review must still establish the applicable appliance requirement.

The Y1 capacitor, relay, AUX supply, controller connector, and any other
crossing require the same path-by-path check.

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

### Inputs to an executable native rule and coverage check

The 16.0 mm FR-4 / 12.6 mm Group I figures above are a conservative
**creepage candidate screen for the >400–500 V row only**. They are not
blanket clearance values, full appliance rules, or an accepted safety basis.
The integration owner needs the following reviewable inputs before a rule
file can make a meaningful claim:

1. A signed product-standard/edition and insulation schedule, including
   OVC/PD, accessible-part and protective-earth assumptions, rated impulse,
   working voltage per crossing, material CTI, altitude, clearance, creepage
   and solid-insulation treatment. The portable-cooker scope points to
   IEC 60335-2-9; the present recovered Table 17 screen is not a substitute
   for checking its applicable clauses against the chosen IEC 60335-1 edition.
2. The frozen joined-source netlist identity and an exhaustive map of its
   nets to SELV, AC, HOT control, VD and VB potentials. For each required
   pair, record insulation class, normal and fault differential, transient
   method, required air and surface distances, and any permitted exception.
   HOT0, an isolator ground and a ground symbol are not enough to infer a
   pair's maximum differential.
3. Exact approved MPNs, package drawings and native pad geometry for both
   isolators and every other crossing; terminal hole/land geometry; laminate
   CTI and stackup; minimum manufactured slot width and copper-to-slot
   tolerance; solder, coating and enclosure assumptions. For a component,
   evaluate both its certified intrinsic barrier **and** its exposed
   terminal-to-terminal package path. For the PCB, measure the shortest
   assembled copper/solder path around openings and along all exposed
   surfaces. Neither side inherits the other's material group.
4. A deterministic net-to-rule coverage receipt against the same source and
   board hashes. It must enumerate every required pair and show which rule
   enforces it, then deliberately lower or remove one required rule and
   demonstrate failure. A second negative control must bridge HOT and SELV
   copper in the native board. The checks must fail on missing/unclassified
   nets rather than silently assign a permissive default.

No routed-board DRC result can replace review of the package, solder-joint,
slot, coating and enclosure paths, or establish the missing physical test
evidence.

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
- [TI ISO774x-Q1 package-option addendum and insulation table](https://www.ti.com/lit/gpn/ISO7742-Q1):
  exact DWW orderability of ISO7741F and absence of ISO7742F DWW from
  the listed orderable parts; DWW package geometry and Group I material.
- [TI ISO6742-Q1 data sheet and orderable addendum](https://www.ti.com/lit/gpn/iso6742-q1):
  exact `ISO6742FQDWWRQ1` status, 2/2 pin map, fail-low behavior,
  package path, optimized land pattern and partial-power timing.
- [TI ISO7842F data sheet](https://www.ti.com/lit/ds/symlink/iso7842.pdf):
  slower alternative pair and its conditional power-loss default delay.
