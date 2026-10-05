# R5 pressure boundary and diverse contact experiments

**Decision: a controlled dry engineering fixture, with an open remote gas reference. Sealed autonomous cooking remains NO-GO.** This is a concrete prototype architecture choice, not a supplier-qualified 250°C cartridge. All hardware results are NOT_RUN. No production detector or cooking enablement is implemented.

## Selected pressure interface

Use the stationary optical enclosure proposed in R2; both witness rods remain inside it without sliding rod seals. Route a stationary tube, **1.5 mm ID, 3 mm OD routing envelope, 100 mm developed length**, from the dry gas space to a **10 mL cold plenum**, which is open to a controlled dry bench atmosphere. The tube/plenum is an apparatus interface, not an appliance spill barrier. Do not attach the tube to the sensing island. The 3 mm OD is a CAD allocation, not a selected tube part or pressure rating. A pressure measurement tee at the cartridge end is required in the future fixture.

For computation, the hot cavity is **1 mL**, effective local diaphragm area is **50.2655 mm²** (equivalent Ø8 mm), and cold gas volume is10 mL. These are pressure-model allocations, not measured cavity volume or a molded diaphragm effective area. CAD may provide a plenum with this volume but cannot establish a flexible membrane's effective area. The main seal and inner membrane must have separate measured effective areas before summing their loads. Our calculation screens the local membrane; main-carrier seal force must be included separately in the main spring characterization. Do not transfer the local3mN budget to an unmodeled main diaphragm.

A dry capillary estimate uses `R=128 μ L/(π d⁴)`, assumed gas viscosity3×10⁻⁵ Pa·s, uniform tube diameter and negligible fittings. Flow source is `Q=Vhot/T × dT/dt + A × speed`; signs are aligned for the worst corner. At10 K/s and20 mm/s, initial298.15K, Q=1.03885 mL/s. The selected tube gives **25.08Pa,1.261mN**, below the3mN pressure allocation. The corresponding small-signal gas time constant for11mL is2.62ms. ID1mm gives a factor5.0625 more pressure and fails that corner.

The pressure allocation is **59.683Pa**. At the selected tube's maximum screened flow, the total dry path resistance may be at most5.745×10⁷ Pa·s/m³; the modeled bare tube already consumes2.414×10⁷. Any filter, fittings, vent, fluid slug, condensation and fouling consume the remainder. A10× resistance fault gives12.61mN and fails. Steady results above a few percent of atmospheric pressure require a compressible-flow model; high-fault rows are conservative warning screens, not precision predictions. Source duration also matters; `vent_transient.csv` explicitly shows the linear RC transient. No measured liquid barrier has this resistance allowance yet.

A remote sealed reservoir is **not** an acceptable substitute. At hot250°C/cold25°C with1mL hot gas, a sealed10mL cold reservoir gives **207.24mN**; even100mL gives21.78mN. The exact ideal-gas calculation conserves mass across separate hot/cold volumes. Heating the cold chamber worsens this. Temperature, gas volume and motion changes all belong in the pressure test.

A paired pressure-balanced diaphragm was rejected as the default prototype because the required area match cannot be assumed from CAD. At76.5kPa common differential pressure, a3mN residual requires effective-area mismatch below0.0392mm², **0.0780%** of the modeled area (linearized equivalent diameter mismatch3.12µm). Both membranes also add stiffness, hysteresis, heat leakage and failure paths. A supplier could propose another design, but none has been qualified here.

Pressure equalization does not remove pressure on the wet/top surface:3mN corresponds to only **6.08mm water head** across this area. This fixture is dry-only. A wet state must invalidate it; no implemented liquid detector is claimed.

## Seal part decision and required RFQ inputs

Retain **Kalrez6375 as a compound candidate only**. DuPont publishes275°C maximum service temperature and expressly ties useful performance to seal design/application. No catalog gland, moving membrane, molding process or food-contact claim is selected by that rating. The proposed local stroke remains0.20mm normal/0.25mm stop; main travel1.2mm; cap free capture lift0.20mm must not tear or tension a boundary attached to the cap.

For a next RFQ drawing, identify which component the inner membrane bonds/clamps to. Attaching it to the carrier versus the lifting cap changes effective area, travel and thermal shunt. The present envelope does not resolve that construction. An actual seal assembly cannot be manufactured from an envelope alone. Require supplier-approved membrane/gland dimensions, compression endpoints including thermal mismatch, tolerances, creep/compression set, media compatibility, installation method and complete static electrical/window feedthroughs. Quote hot duty and overshoot from product requirements; those have not been defined. No supplier has been contacted.

A remote hydrophobic vent is a separate future option, not the selected open reference. Gore's tube-mount product page rates the cited product family to125°C; it does not qualify a250°C hot-side vent or this cleaning environment. Relocation needs a verified cold zone, flow curve, liquid entry behavior, solvent/oil compatibility, condensate management and fault response. No membrane part has been selected. Geometry alone cannot convert this dry study into an ingress-qualified product.

## One complete local force budget

| Contribution | Allocation | How it must be demonstrated |
|---|---:|---|
| Pressure residual |3mN|Measured differential pressure × measured effective area, including top liquid pressure and blocked gas path |
| Seal friction/hysteresis |3mN|Hot/cold force-displacement loops with actual installed membrane, aging and contamination |
| All harness/witness parasitics |4mN total|Complete route including covers, strain relief, optional instrumentation and both rods across all strokes |
| Sum of residual terms |10mN|Worst-case signed sum; no component gets the entire budget |
| Linear flexure + membrane + harness stiffness |1.6–2.4N/mm total|Installed slope across temperature/travel, separated from residual hysteresis |
| Optical differential error |15µm|R2 component budget; not a force allocation |

At0.12N minimum actual external force,2.4N/mm maximum stiffness,10mN residual and15µm error, minimum reading30.83µm exceeds25µm by5.83µm. Unloaded maximum21.25µm gives3.75µm margin. These narrow margins still require measurement. A tube calculation is not a total-force-budget pass. Optical heads and windows remain cold, within the selected head's0–50°C non-condensing operating envelope; a cold-volume allocation alone does not demonstrate that temperature.

## Detector decision: diverse bench evidence, no claimed autonomous interlock

Keep R2 differential island/carrier measurement as the **mechanical channel**. Test a retract/release challenge on the external fixture, with **0.4mm verified carrier withdrawal** while heating is inhibited; record independent actuator travel and loaded/unloaded/reloaded optical signals. The proposed sequence only reduces specific faults: rigid seizure and constant fresh readings fail the constructed challenge. It is not an actuator design, a timing guarantee or permission to fit a new actuator to CAD. A compliant jam can unload/reload with the carrier, and fake values correlated with the command can reproduce the healthy history. The executable counterexample prevents calling this a complete detector.

Add a **separate instrumented coupon experiment: AC impedance between the metal cap and a clipped bare-metal pan reference**. Use a temporary pickup welded to a non-contact part of the cap and a separate pan clip; this avoids splitting the cap or placing electrodes in the thermal contact patch before feasibility evidence. The pan clip is external test equipment, not a solution for ordinary user cookware. This variant is separate from the four-lead thermal cartridge: the pickup's weld mass, route force and heat shunt must be measured/modelled before using its thermal results as an unmodified-cartridge result. It is not silently included as a massless CAD electrode.

Candidate measurement recipe is1 and10kHz impedance/phase with low-energy excitation and open/short/load fixture checks. The example gate `|Z|<100Ω and |phase|<20°` is a **study discriminator, not an accepted product threshold**. The bench source, wiring and isolation must be engineered before hardware use. Keysight's published E4980AL capability supports relevant frequency/impedance investigation, but that model is discontinued and this work selects **no purchased instrument or induction-compatible isolation system**. Any existing instrument must be qualified for its configuration. Perform this experiment **with the induction power stage disconnected and unenergized**; no assumed earth-referenced instrument may be attached during induction. Hot tests would need a separate controlled source and qualified isolation procedure. No hardware is run here.

The electrical channel distinguishes many separated-cap jams from conductive bare-metal contact. It is conservative for enamel, oxide or other insulating cookware coatings: a genuine thermal contact may fail electrically. Conductive liquid, metallic debris or a shorted pickup can pass falsely. At1kHz, a10µm dry full-face gap with100pF stray capacitance is high impedance. But a modeled316L-like whisker only5µm diameter and1mm long has35.65Ω while carrying merely2.95×10⁻⁷W/K thermally: it passes the example electrical gate yet supplies negligible thermal contact. Material constants in that counterexample are assumptions, not a qualified whisker material. Adding the electrical gate to the mechanical gate therefore does **not** establish useful heat transfer.

A thermal pulse also cannot alone prove the destination of heat. Equal0.13W/K total conductance to a pan or an unintended wet/body sink gives the same lumped0.21344K response for0.1W,0.1s,C0.04J/K. Bounding parasitic paths and separately measuring pan/cap temperature is necessary. No heater or pulse-power electronics is added to this assembly.

### Fault coverage matrix

| Fault/state | Mechanical differential | Retract challenge | Pan-cap impedance | Combined conclusion |
|---|---|---|---|---|
| Pan removed, island free |Reject within bounds|Reject reload|Open/dry reject|Conditionally covered; physical latency unmeasured |
| Main guide/seal jam, island free |Reject within bounds|May reject actuator movement|Open/dry reject|Conditionally covered |
| Island/rod rigidly held loaded |Can pass|Reject constant signal|Open/dry reject|Bench methods address this injection, not all seizures |
| Compliant jam held without pan |Can pass|Can pass|Open/dry rejects absent bridge|Electrical diversity improves coverage only for dry isolated cases |
| Credible constant fresh reading |Can pass|Reject|Independent dry open rejects|Command-correlated/common software faults still open |
| Force-carrying insulating debris |Pass|Can pass|Often reject|Metal/ionic contamination defeats electrical condition |
| Conductive sliver supporting force |Pass|Can pass|Can pass|Thermal contact still unproven |
| Pickup short + mechanical jam |Pass|May pass|Pass|Residual combination; self-test needs end-to-end isolation coverage |
| Genuine pan with insulating coating |Pass|Pass|Reject|False negative; restricted bare-metal coupon applicability |
| Pressure biases island |Can pass|Can pass|Dry no-pan rejects|Pressure bounds and wet exposure independently needed |
| Blocked vent/top liquid pressure |May exceed force bounds|Not a pressure proof|Not a pressure proof|No wet/sealed operating release |

`challenge_counterexamples.csv` contains deliberately constructed histories, not a statistical fault campaign. No failure probabilities or safety integrity level follows from the counts. Keep the production backend unavailable. A product architecture decision requires either verified independent local thermal-contact evidence over the allowed cookware/contamination range, or a revised use envelope and qualified safety architecture. That decision is not closed by adding more filters to the same motion data.

## Evidence and next measurements

Run `./run.sh` to regenerate six CSVs and tests. Nine independent analytic/limiting/counterexample tests pass; rustfmt, warning-denying rustc and direct clippy-driver pass. All material, viscosity, heat rate, velocity and effective-area inputs are declared assumptions/screens. CAD fit and this math support **dry fixture preparation only**.

Before a sealed prototype release, demonstrate (1) actual hot/cleaned membrane force loops and area, (2) gas-path resistance and blocked/slug behavior, (3) top liquid-head behavior, (4) cold optics/window drift, (5) all jam/false-fresh/contact-contamination injections with raw traces, (6) heat shunt/force from any impedance pickup, and (7) complete electrical isolation and physical cutoff timing. Simulation has defined the experiments and rejected misleading shortcuts; it has not run these tests.
