# Rev A PCB layout and assembly constraints

Canonical board: [`cad/differential-probe.kicad_pcb`](../cad/differential-probe.kicad_pcb). This is a fully routed engineering prototype for the agreed stage-53 probe. It is not a released or voltage-qualified instrument. The circuit and selected electronic parts remain those in the schematic, with slot-compatible capacitor artwork and corrected ADA4817 paste apertures.

## Board and layers

| Item | Implementation |
|---|---|
| Outline | 240 × 120 mm, 3 mm corner chamfers |
| Board | Four copper layers, nominal 1.6 mm, top-side component assembly |
| F.Cu | HV ladders and primary signal/local bypass routing |
| In1.Cu | GND plane in the low-voltage region; no signal tracks |
| In2.Cu | +4.8 V distribution and selected signal routes |
| B.Cu | −4.8 V distribution and selected signal routes |
| Plane boundary | x = 128 mm; HV routing has no underlying planes |
| Signal tracks / vias | Normally 0.25 mm; 0.6 mm via diameter, 0.3 mm drill |
| General clearance | 0.20 mm; explicit HV rules override it |
| Fine-pitch exception | U6 pad-to-pad only: 0.15 mm, matching the selected VSSOP land pattern |
| Slots | Ten non-plated 1.2 × 8 mm cutouts on Edge.Cuts, one beneath each HV capacitor |
| Assembly | 125 circuit footprints, five offboard wire-landing footprints, two HV landings, six mounting holes |

The final fabricator dielectric stackup, laminate CTI, copper weight and finish are not selected. There is no controlled-impedance claim. Preserve the ground reference layer directly below F.Cu; changes to dielectric thickness or copper geometry require renewed compensation/CMRR assessment. The small prototype signal currents do not require heavy copper.

Slots are rectangular design envelopes; a 1.2 mm router gives approximately 0.6 mm internal corner radii. The capacitor lies across the middle of each slot, well away from its ends. Review the fabricator's routed-slot drawing before fabrication; do not replace slots with a silk mark or solder-mask opening. No solder, coating, adhesive or debris may bridge the cutout. Solder mask is not credited as insulation.

## Divider symmetry

The two legs use identical orientation and geometry, translated 70 mm vertically. R1–R12 correspond to R21–R32, C1–C5 to C21–C25, C41–C47 to C51–C57, and the two buffers, clamps, trims and local bypasses are paired. All twenty elevated resistor nodes stay on F.Cu with no vias. The keepouts forbid copper fill beneath the ladders on every layer and forbid hidden-layer tracks/vias there. HV through-hole input pads necessarily retain their own annuli on the other copper layers.

The native-geometry audit compares 30 footprint pairs, 68 electrical-pad pairs and 12 paired ladder/tap/input nets. It checks actual KiCad-exported coordinates, dimensions, layers and track/via geometry. It does not infer symmetry from the placement source or a screenshot.

This is geometric matching of the input sections, not a claim that the whole amplifier has matched parasitics. BUF_P and BUF_N take different routes/layers to U3; the comparator branches and the common reference distribution also differ. Finite shield boundaries, lead position, component tolerance and these downstream paths remain contributors to measured CMRR. The board is intended for calibration and stability/CMRR qualification, not an assumption of 60 dB from layout symmetry alone.

## High-voltage spacing budget

The custom rules in [`differential-probe.kicad_dru`](../cad/differential-probe.kicad_dru) use the **extended ±3 kV per-tip target** to set a prototype spacing budget. They assume the intended distributed R/C voltage sharing in intact legs. These are explicit engineering constraints, not a determination of IEC 61010 measurement category, impulse withstand, pollution degree or certified working voltage.

Each 1 MΩ resistor step is assigned a rank of one, approximately 300 V at a 3 kV tip. For two nodes in the same leg, rank difference sets spacing. For opposite legs, rank **sum** sets spacing, allowing opposite input polarities. For a ladder node versus any low-voltage net, its rank sets spacing. The low-voltage circuit is treated as near earth relative to kilovolts; its several-volt excursion is covered by the physical margins, not a separate insulation class.

| Pair | Design voltage used | Minimum air clearance | Minimum PCB creepage |
|---|---:|---:|---:|
| Adjacent resistor nodes | 300 V | 1 mm | 2 mm |
| Across a compensated section | 600 V | 2 mm | 4 mm |
| Full tip to low-voltage/earth net | 3 kV | 10 mm | 20 mm |
| Opposite tips at ±3 kV | 6 kV | 20 mm | 40 mm |

The 6 kV opposing-tip geometry does not extend the **differential measuring range** beyond the agreed 3 kV target. Output range, tip-to-earth voltage and insulation spacing are separate limits.

The selected resistor pads have 4.70 mm straight separation within each resistor. The 1812 capacitor pads have only 2.70 mm straight separation, so the routed slot is necessary to meet the 4 mm PCB-surface rule. Native KiCad DRC checks the routed outline, rather than treating the slot as extra air clearance. Component-body surface paths and lead soldering are not certified by the PCB-only creepage calculation; inspect them as part of the assembly qualification.

No insulation credit is taken for a coating, a floating scope, an input lead's unspecified jacket, or intact voltage sharing after an internal divider component fails. Transient voltage distribution and single-component failures require separate analysis/testing. The existing qualification plan covers the intended external tank/fault measurements; this board does not establish a safety-rated single-fault instrument.

## Shield and mounting

Use a fixed conductive enclosure connected to the BNC shell / scope earth. Make the BNC-to-enclosure bond directly at the output entry, with a short, broad connection. The board GND landings and H1–H4 connect to its uninterrupted low-voltage ground plane. The stitched top/bottom perimeter conductors are additional local bonds; do not send the enclosure's displacement current through the low-leg trim return as its only route to earth.

Keep the lid, floor, side walls, fasteners and any internal shield at least **20 mm from exposed HV conductors**, including soldered lead loops and component terminals. The board silk references HV copper; assembly inspection must include conductors protruding above it. That is an enclosure constraint, not a dimension already provided by a housing model. In particular, the lower capacitor row is only about 15 mm from the board edge: a metal wall at that edge is unacceptable under this constraint. Allow additional wall setback. Use matching lead lengths, insulation, bend radii and fixed routing for both inputs. Do not add individual grounded screens close to ladder nodes without re-evaluating their shunt capacitance.

| Mount | Position, mm from top-left origin | Hardware |
|---|---|---|
| H1 | (135, 6) | GND, plated 3.2 mm hole; M3 bond |
| H2 | (234, 6) | GND, plated 3.2 mm hole; M3 bond |
| H3 | (135, 114) | GND, plated 3.2 mm hole; M3 bond |
| H4 | (234, 114) | GND, plated 3.2 mm hole; M3 bond |
| H5 | (7, 7) | Unplated 3.2 mm hole; insulating support only |
| H6 | (7, 113) | Unplated 3.2 mm hole; insulating support only |

Use insulating screws/standoffs at H5/H6 and keep the grounded base below the stated HV envelope; a metal screw through a nylon spacer would defeat that intent. H1–H4 occupy the low-voltage area. Keep washers within the supplied mounting-pad envelope and clear of RV2. Locate batteries and their holders in the low-voltage region or a separate insulated compartment, not beneath the HV ladders.

## Leads and panel components

`W_HV1` and `W_HV2` are 4 mm solder pads with 1.6 mm plated holes for captive HV leads. They are not a rated connector. The lead insulation, tip assembly, stripped length, strain relief and feedthrough remain mechanical selections. Restrain each lead before its solder joint; external pull must not load the pad or alter calibration geometry.

`W_SW1`, `W_SW2`, `W_BT1`, `W_BT2`, and `W_J3` are wire landings, **not manufacturer footprints for direct component insertion**. Pin numbering matches the corresponding schematic component; see [`layout/landings.tsv`](../layout/landings.tsv). SW2's unused throws 3 and 6 intentionally have no landings. Battery and BNC polarity must be checked against that table before power-up.

Mount the gold-contact range switch immediately above its landings. Aim for no more than 3 mm of unsupported connection and equal lengths for paired contacts; this is not a long panel harness. Its lug pitch differs from the solder-pad pattern, so use short formed links and mechanically register the body independently. Verify body clearance and travel in the enclosure. Range change temporarily changes feedback and is performed with the DUT de-energized. The power switch and batteries may use a longer retained harness within the low-voltage compartment.

Keep the panel BNC close to W_J3; use a short coax connection if it cannot be directly adjacent. Connect its shell to enclosure earth at the panel and to board GND. Use the intended 1 MΩ scope input.

## Footprints and visual review

The ADA4817 footprint has a 2.29 × 2.29 mm exposed pad with four contained 0.9 × 0.9 mm paste apertures at ±0.55 mm. Its standard SOIC-8-EP 3D model represents the package body; the model's underside exposed-pad size is a surrogate, while the PCB pad and paste geometry are authoritative. Do not add unfilled via-in-pad holes without reviewing solder loss and assembly process.

The HV capacitor footprint uses standard 1812 lands and body dimensions, with the body outline moved to F.Fab so it does not print across the slot. C62/C63 retain their DNP state in the board; the assembly PDF crosses them out. Some renderer presets still show their body models, so the BOM/DNP fields govern assembly.

The six-page layer PDF and 3D render were reviewed: divider slots are open, HV regions have no underlying plane fill, low-voltage ground remains connected, and component bodies do not visibly overlap. This does not include a completed enclosure, wires or switch/battery bodies. The 1 GHz ADA4817 stages, switch feedback and comparator loading still require the low-voltage oscillation/stability tests in the qualification plan, including both ranges and the intended cable.

## Verification and regeneration

Recorded with KiCad 10.0.4:

- Schematic ERC: zero violations.
- Native PCB DRC with all track errors and HV rules: zero violations, zero unconnected items, no exclusions.
- Native schematic/PCB connectivity, value, footprint and DNP checks: pass.
- Divider pad and copper symmetry checks: pass.
- Negative clearance control: a GND trace 1.875 mm from TIP_P is rejected by the 10 mm rule.
- Negative creepage control: removing the C1 slot is rejected at 2.70 mm against its 4 mm rule.

Reports and SHA-256 identities are in `validation/`. No high-voltage, CMRR, bandwidth, thermal or recovery test has been executed. [TI's isolation-spacing discussion](https://www.ti.com/lit/pdf/slup419) explains why working voltage alone is insufficient to assign a compliance rating. [The ADA4817 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ADA4817-1_4817-2.pdf) supplies the compact-feedback and input-plane-clearance guidance used here.

`make pcb` regenerates the complete design. `make pcb-check` checks the saved PCB without changing its routing. `make pcb-oracle` creates known-bad fixtures only in ignored `build/`. The layout source is explicit Rust placement and hand-authored tracks; the native Python bridge loads footprints, applies KiCad transforms, fills zones and exports geometry. Manual edits in KiCad are welcome, but reconcile them into `tools/layout.rs` before running `make pcb-generate` again.
