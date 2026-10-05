# R4 closure contract and next coupon release

Stage supported: **dry controlled engineering prototype preparation**. This document makes each remaining gap decidable. Values called allocations or screening loads are proposals within the simulation study, not supplier-approved tolerances, certification limits or claimed service loads. All physical outcomes are NOT_RUN.

## 1. Thermal contact: test the map as well as total heat flow

Retain C0/C1/C2 from [R3](../revision3/TEST_PREPARATION.md). Add three pan-interface fixtures: full-face contact, a centralØ4 mm contact land and an annular r3–4 mm contact land. Relieve the remainder so it cannot accidentally carry the intended contact load; record gas-gap conduction and fixture mass. These are test fixtures, not a recommendation to put a raised boss on every product cap. Inspect free and loaded hot/cold face shape. A force-transmitting insulating film must be a separate negative-control coupon.

Measure cap center and rim, pan local reference, carrier and anchor temperatures. Record instrumentation heat shunts and local force. Fit total interface conductance on an independent calibration run; keep contact pattern, other losses and bond properties independently constrained. Test holdout runs across force, pan curvature, tilt and surface condition without refitting. The axisymmetric model does not cover one-sided contact; include that fixture in eventual spatial-model validation.

Acceptance is joint: measured t90-pan, bias and contact pattern must meet the declared use envelope, including uncertainty. Never accept from fittedG alone. The earlier0.13 W/K rule is superseded as a sufficient general screen. R4's inverse thresholds exclude seal capacitance and unmodeled azimuthal effects, so they are planning numbers.

For a whole-system±2°C claim, propose a **≤1°C thermal steady-bias development target**, reserving the other1°C for assembly calibration, frontend/current/reference effects and pan spatial/reference uncertainty. Do not assume that reserve has been allocated or demonstrated. At high wire cooling plus seal loss, uniform contact does not meet1°C thermal bias withinG≤0.5 W/K; center contact needs≈0.2381 W/K. That is a demanding unverified interface, not a selected solution. If it cannot be demonstrated, reduce lead/support loss, move the sensor closer to the actual contact patch, or relax the accuracy/use envelope.

Specify dynamic accuracy separately. Heating-rate limits or a calibrated estimator may be needed near setpoint; the current model provides neither a validated compensation algorithm nor independent evidence of contact. No controller is tuned from the optimistic lumped result.

## 2. Seal: choose a complete pressure and liquid boundary

Keep Kalrez6375 as an inherited compound candidate, not an approved assembly. Its catalog temperature rating does not select a gland, rolling diaphragm, adhesion process or food-contact status. The existing inner seal would connect the sensing island to the carrier; it enters the local force budget directly.

The design brief for supplier review is now:

| Boundary/interface | Required behavior and evidence |
|---|---|
| Glass to fixed cartridge | Static gasket with supplier-agreed compression endpoints; glass clamp load, extrusion space and thermal mismatch included |
| Main carrier to housing |1.2 mm travel without sticking; main spring force remeasured with seal and harness installed |
| Island to carrier |0.20 mm normal local motion,0.25 mm stop, upward capture and cap-lift compatibility; measured stiffness1.6–2.4 N/mm after installation |
| Cap/hook region | Top entry path closed without covering the pan-contact surface or bridging the sensing motion; catches remain functional when wet/dirty |
| Optics | Static window in the cold region with transmission/fogging/thermal drift included in the15µm total differential-error bound; no sliding witness-rod seal |
| Electrical exit | Qualified static feedthrough; uninterrupted dielectric protection to the exposed join pockets; no glue-only assumption of hermeticity |
| Pressure | Effective diaphragm area, gas volumes, temperature field and vent/compliance transfer function defined; differential force included at every motion/temperature state |

Use a preliminary **3 mN pressure /3 mN seal hysteresis /4 mN complete harness-and-witness parasitic allocation**, summed worst-case within10 mN. The old10 mN must not be allocated in full to each subsystem. Linear seal stiffness belongs in measured1.6–2.4 N/mm; pressure bias, friction and hysteresis belong in the residual budget.

Compare two concepts before supplier drawing release: (A) a pressure-balanced flexible boundary, including imbalance from unequal effective areas; (B) protected pressure equalization into a controlled dry volume with a validated liquid/cleaning barrier. A sealed rigid cavity with an unbalanced diaphragm is rejected as the default. No vendor-qualified250°C vent or balanced membrane has been selected. Do not substitute an unqualified porous vent and call the cartridge sealed.

Provide the seal supplier the actual cooking/cleaning media, hot duty, overshoot bound, pressure/cooling transients, installation tolerances and service cycle requirements. Those use conditions require product definition; this package does not invent lifetime cycles or leak limits. Obtain compression-set/creep and dimensional data for the actual molded geometry, not only a compound table. No RFQ has been sent.

## 3. Contact detection: explicitly separate detectable and blind faults

| Physical state | Existing fresh differential reading | Existing conclusion | Closure requirement |
|---|---|---|---|
| Pan removed, free local island |Below25µm within error/parasitic bounds|Release detectable|Measure end-to-end release including physical rebound and control cutoff |
| Main guide/seal held, island free |Below25µm within bounds|Main jam can be rejected|Hot/wet jam injection with final membrane/harness |
| Island held at loaded position after pan removal |Credible25–220µm|False contact possible|Independent observable sensitive to actual separation or qualified physical proof of local freedom |
| Witness rod held or sensor synthesizes plausible fresh samples |Credible25–220µm with advancing timestamps|False contact possible|End-to-end diagnostic that changes the physical measurement; freshness alone is insufficient |
| Insulating debris carries pan force |Credible loaded movement|Force without useful thermal contact|Independent thermal-contact evidence across relevant surfaces, without treating a warm sensor as proof |
| Liquid pressure biases diaphragm |May remain in loaded interval|False contact possible|Pressure-force budget and pressure/temperature fault tests |

An identical input history cannot distinguish two different physical states. Threshold tuning, a second laser on the same mechanism, more samples or an estimator trained on the same trace cannot close those blind cases. An unloaded startup check only covers startup; a jam can occur later. Periodic dither may be worth a separate actuator study, but elastic debris/compliant jams can reproduce a plausible response, and no actuator is fitted here.

Keep the production backend unavailable. The next detector design must identify the added observable and demonstrate, by deliberately held island/rod/frozen-data/debris/pressure injections, that each required fault causes inhibition. Define residual common-cause failures and detection latency explicitly; do not infer a safety integrity level from this table. Existing induction pan-presence detection can support overall protection but does not prove local thermal contact.

## 4. Retention: qualify unequal loading and the load path

Retain three welded hooks and0.20 mm nominal free capture gap. Hooks retain the cap independently of the sensor bond. Inspect the three gaps separately, hot/cold and after cleaning/cycling; do not use their average. R3's0.15–0.25 mm sensitivity range remains an analysis window, not a production tolerance.

R4 screens the toe as a straight cantilever,0.30 mm lever,0.80 mm width and0.15 mm thickness. Under1 N total lift, equal three-hook sharing gives33.3 MPa nominal bending; a single hook carrying it gives100 MPa. Under2 N the single-hook screen reaches200 MPa. **Neither load is an accepted requirement and neither stress is an allowable.** Formed bends, weld peel, residual stress and high-temperature fatigue are omitted. Do not approve from a base-metal yield number.

A separate0.1 N transverse load on oneØ0.30×2 mm post gives75.5 MPa nominal root bending; sharing across three gives25.2 MPa. Ceramic fracture depends on flaws, fillets and process. The prototype must include side drag, rocking, caught-cap uplift and a particle under the thin roof. Release loads and cycles must derive from the cookware/handling envelope, then include an agreed margin and measurement uncertainty.

Fixture cap-only pull, full-cartridge pull and off-axis drag separately. The island's upper catch and its attachment must carry the captured cap load downstream; strong cap hooks alone do not complete the load path. Inspect welds and post roots after loading, and remeasure cap flatness/temperature response. Assign mechanical design to define loads and supplier quality to establish weld/post process evidence before fabrication release.

## 5. Bond and leads: freeze the installed article, not just part numbers

Keep M222,0.10 mm nominal Resbond coupon and TFCP-003 copper/PFA as the baseline. R4's0.075/0.10/0.15 mm sweep atG0.13, h15 and sealG0.0002 gives uniform t90-pan2.000/2.110/2.325 s and bias2.296/2.372/2.518°C. Thinning bond alone does not recover the complete target. Use measured cured thickness and void/coverage data, not dispensed volume.

Before a full cartridge build, the assembly drawing must show both native-terminal weld regions, their insulating covers, the cap-side anchor and the complete60 mm developed flexible route in all main/local/cap-lift states. The R3 short anchor solids and R2 bundle envelope are insufficient. The two3×1×1 mm join pockets proposed in R2 have not been verified as a completed assembly. Do not release those as installed hardware.

Resolve the apparent strain-relief conflict explicitly: cap, RTD and hot anchor can lift0.20 mm relative to the island before capture, so any island-mounted native-lead relief must allow that motion without loading the factory fixing drop. Prefer locating rigid native joins and their cover on the cap-moving assembly, then flexing only insulated extensions downstream; that adds moving mass and space and must be included in the next CAD/thermal revision. This is a proposed layout decision, not a verified fit. No joint cover is silently massless.

Preserve intact PFA at the anchor,0.003 W/K remains a demanding measured target, and its real force counts inside the4 mN proposed harness/witness allocation. Section sacrificial bonds/anchors, qualify weld sections/pull and actual Kelvin datum, and measure hot/cold insulation and route force after cycling. Use the supplier's current cure instructions and received-part lead limits. The260°C wire rating leaves little nominal temperature headroom; an assembly overshoot requirement is still needed.

## 6. Induction and release

The [prepared induction plan](../induction_validation/TEST-PLAN.md) remains NOT_RUN. Final cap, hooks, flexures, welds and lead route must be tested together for self-heating, pickup, rectification and spatial pan temperature. Thermal-reference measurements must distinguish actual cap heating from electrical readout error. Seal pressure/force and insulation checks must be repeated after thermal/cleaning stresses.

Release evidence must include revision/hash, cartridge serial/lot, inspection records, calibrated instruments, individual raw runs, predefined fit/holdout split, uncertainty and fault-injection outcomes. A local simulation pass cannot populate a physical PASS. No cooking enablement, procurement, supplier communication or hardware operation is authorized or performed by this package.
