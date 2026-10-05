# R5 through-glass sensor: complete cartridge comparison

**Simulation and test preparation are complete for this revision. Build the 6 mm head as the next dry comparison coupon and retain the 8 mm head as its control. Neither is released for cooking or manufacture.** No physical cartridge, induction or endurance measurements have been performed.

The [review page](report.html) brings together the CAD, model results and all nine open evidence gates. [The current CAD index](../CURRENT.md) identifies the files to use for prototype preparation; earlier revisions remain historical evidence.

## Thermal decision

The model now includes the cap, bond, cap-moving weld regions and protective covers, their attachment films, ceramic support and witness mass, thermal anchor, and all four 60 mm insulated wire routes. Both heads have a 0.15 mm roof. The 6 mm head has six recessed retention ears and independent axial compliance; it is not a gimbal. A 4 mm head cannot accommodate the current sensor, bond and protected joins.

| Nominal contact pattern | 8 mm t90 of pan step | 6 mm t90 of pan step | 8 mm underread at 200°C | 6 mm underread at 200°C |
| :-- | --: | --: | --: | --: |
| Uniform | 3.44 s | 2.94 s | 2.44°C | 2.47°C |
| Central 4 mm patch | 3.55 s | 3.00 s | 2.82°C | 2.88°C |
| Outer rim | 9.81 s | 7.35 s | 6.55°C | 5.74°C |

These are uncalibrated simulations at the same 0.218182 N force and assumed contact law. Contact conductance changes with area. Steady results use pan/glass/body boundaries of 200/80/60°C. They are thermal bias alone, before calibration, readout, induction and reference uncertainty. They must not be mixed with t90 relative to the sensor's own final reading or with older simplified model results.

A stronger assumed contact coefficient produces 1.96 s and 1.44°C thermal underread for D6, but still misses the proposed 1°C thermal allocation. Adding the explicitly hypothetical 1°C system reserve leaves **zero of 36 cases** meeting both whole-system error below 2°C and t90-pan below 2 s. Nominal D6 needs approximately 0.183 W/K effective contact conductance for the 2 s/1°C thermal pair; higher-loss assumptions need 0.420 W/K. Those are scenario-dependent design screens, not verified surface specifications. Rim cases find no solution through 0.5 W/K.

The next thermal lever is measured, repeatable face contact together with lower parasitic losses. Shrinking the head alone improves delay but does not cure steady underread. Finite ramps and spatial contact cases are included in [thermal results](thermal/RESULTS.md); no closed-loop overshoot has been established.

## Every open gate

| Gap | Work completed in R5 | Required evidence still outstanding |
| :-- | :-- | :-- |
| Spatial model | CAD-driven radial cap, full wire and support network; center/rim cases; convergence and independent limiting checks | Measured contact distribution and conductance, calibrated boundary losses, held-out response curves |
| Sealed pressure | Gas transient, blocked/restricted paths, liquid head and balanced-area screens; separate dry reference apparatus CAD | Complete connected gas/liquid boundary, actual effective areas and cavity volumes, hot/cold pressure-force measurements |
| 250°C seal | Compound candidate and supplier/test requirements; hot-side vent limitations recorded | Exact custom membrane/gland/feedthrough design, supplier acceptance, chemical/creep/leak and hot wet cycle evidence |
| Jam detection | Independent mechanical challenge and optional electrical-contact coupon; explicit fault counterexamples | An observable that detects local separation despite jams, debris and correlated sensor faults; end-to-end inhibition tests |
| Retention | Captured cap, six motion poses per head, interference checks and inspection/load-path package | Product-derived loads, hot pull/peel/fatigue and ceramic flaw tests; supplier-approved forming/weld process |
| Bond and leads | Moving joins/covers/films/anchor and full smooth routes; weld topology and wire-volume checks | Received lead identity, cure and section evidence, weld pull/insulation/cycling, installed harness force and anchor conductance |
| Whole-system accuracy | Current thermal results consumed with conservative proposed uncertainty reserve and strict stale-input rejection | Defined cookware/temperature/rate envelope, traceable installed calibration, holdout/drift and measured uncertainty |
| Induction | CAD-derived roof sensitivity, wire-loop pickup screens and physical acquisition plan | Actual field and formed-material data, independent self-heating/hotspot measurements, EMI, leakage and inhibition tests |
| Physical qualification | Serial/lot/hash requirements, empty acquisition templates, rejection of unmeasured evidence and retest triggers | Hardware, calibrated instruments, approved acceptance criteria and sample plan, raw results and review |

All nine retain `physical_result: NOT_RUN` in the [machine-readable ledger](validation/gaps.json). These are completed simulation/preparation work packages, not nine closed product qualification gates.

The dry pressure concept uses an open 10 mL remote reference and an ID 1.5 mm × 100 mm tube. The separate [apparatus STEP](mechanical/R5-pressure-reference.step) is **unconnected and unmounted**. The 1 mL hot cavity and 8 mm effective diaphragm diameter remain modeling allocations. A 6.08 mm water head alone consumes the proposed 3 mN pressure budget, so this concept does not establish a spill seal.

The retract challenge and pan-cap electrical coupon do not prove thermal contact: a thin conductive whisker can pass an electrical screen with negligible thermal conductance. Sealed autonomous cooking remains blocked. No production control backend is enabled.

## CAD and build package

- [6 mm assembly, rest](mechanical/R5-D6-rest.step) and [cap](mechanical/R5-D6-cap.step): comparative dry coupon candidate.
- [8 mm assembly, rest](mechanical/R5-D8-rest.step) and [cap](mechanical/R5-D8-cap.step): control.
- [Mechanical package](mechanical/README.md): six poses each, sections, pressure reference and dimensional records.
- [Assembly/process package](mechanical/BUILD_PACKAGE.md) and [physical test package](validation/TEST_PACKAGE.md): preparation instructions and remaining acceptance decisions.
- [CAD scalar contract](mechanical/thermal_geometry.csv) and [independent exported STEP checks](cad-parity.json): cap area/volume matching. Other network capacities and lengths are derived from the geometry contract; scalar parity is not proof of the thermal model.

Nominal CAD checks found no modeled rigid/wire interference across 12 poses, including a separate wire-to-witness check. Seal shapes remain envelopes. Clearances do not establish thermal growth, manufacturing variation, optical line of sight or flexure force. Four of 30 severe D6 tilt/curvature screens permit ear contact and invalidate the face-only thermal assumption. Proposed 0.5 mm static and 2 mm dynamic wire radii are not supplier-qualified forming or fatigue limits.

## Reproduce

From this directory, run the standalone Rust simulations in order:

```sh
./thermal/run.sh
./safety/run.sh
./validation/run.sh
```

They use `rustc`, `rustfmt` and `clippy-driver` directly; no Cargo extension build is involved. The thermal runner verifies its source, inherited kernel and CAD scalar hashes before running. Validation requires the resulting four-path receipt and rejects stale geometry/results. A deliberate geometry change requires reviewed input-pin updates before rerunning, not an automatic re-pin.

For CAD regeneration, use Python with CadQuery 2.6.1 (the prepared environment here is `/private/tmp/temper-center-sensor-env/bin/python`):

```sh
python mechanical/build.py
python mechanical/audit_routes.py
python mechanical/build_pressure_reference.py
python check_cad_parity.py
python check_witness_clearance.py
```

`build.py` verifies its inherited R2 source hash. STEP export timestamps may differ on regeneration; compare geometry and scalar inputs, and retain full byte identities for each issued artifact. Presentation uses Matplotlib via `render_cad.py` and `build_report.py`. `check_runner_failures.py` verifies test-failure propagation in isolated runner copies.

See [executed verification](verification.md) and [full artifact identities](source-provenance.json). No physical evidence, supplier approval or certification is inferred from these checks.
