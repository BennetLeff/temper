# Induction validation: simulation and test preparation

Status: **no physical measurement, no hardware energization, no EMC, sealing or endurance qualification performed.** This package screens sensitivities and prepares a traceable acquisition/evaluation workflow. The user limited this stage to simulation and test preparation on 2026-10-04.

## Reproduce

Run `bash run.sh` here. Rust physics and evaluators build with `rustc` into a disposable `/tmp` directory; no shared Cargo or pyo3 artifact is modified. It runs numerical tests, 540 cap sensitivities, 72 lead-coupling cases, paired coil-on/off synthetic checks, an intentionally missing-measurement rejection, and 840 synthetic hotspot channel rows using `../model.rs` read-only. Every output says SIMULATED or SYNTHETIC. `results/not_run.txt` must say missing required measurement.

For future measured files: `bash run.sh paired /absolute/data.csv /absolute/run.meta` or `bash run.sh endurance /absolute/data.csv /absolute/run.meta`. The wrapper verifies the full SHA-256 of raw CSV, then the evaluator rejects missing fields, nonfinite numbers, missing measurements, duplicate checks, wrong units/directions, negative uncertainties, invalid acquisition and unresolved provenance. A measured screen within a configured limit is **not** certification or design qualification. Required evidence beyond the summary values is specified in TEST-PLAN.md; a software evaluator cannot verify a technician's claimed provenance. CSV is a deliberately strict unquoted format. Raw high-rate samples and calibration evidence live separately under the record IDs; do not round or overwrite them.

## Artifact identity

| Artifact | Status and role |
|---|---|
| Study source `767f2fbae7a842e58afb288c5966453f10ab3d7a` | Frozen prior contact/thermal study and kernel; synthetic pan heating only |
| Legacy `pcb/temper.kicad_pcb`, `elec/src/main.ato`, RTDSensing | Existing design with MAX31865 and documented RTD hardware electrical fault path. No PCB modifications or remeasurement here |
| New user-local `zapote/power-stage-120v` | Full-bridge source concept, compiled/audited per its README; native schematic/PCB and physical tests open. Do not transplant legacy circuit/layout evidence |
| New `docs/hardware/power-section-120v/` | Assumed 70 µH coil, 0.54 µF resonant bank, 20–60 kHz exploration, ~33–39 kHz full-power screen and ~18.7 A RMS line-average current. These are model results, not measured field strength |
| Candidate cap from parts/CAD workstream | 316L EN1.4404, roof radius5/thickness0.15 mm; skirt outer radius5/inner4.6/height1.85 mm. Keeps full skirt mass. Custom manufactured part, not yet built |

The newer files were untracked inputs in `/Users/bennet/Desktop/temper`; their hashes are in `input-sha256.txt`. They are not asserted to belong to the study's Git revision. Neither coil turns/ferrite geometry nor cap-location field with real pans is known. Coil inductance/current alone cannot give local flux density; **none of the field values below is a Temper field prediction**.

## Cap self-heating sensitivity

For an imposed spatially uniform axial sinusoidal field with RMS amplitude B, Faraday gives RMS azimuthal `E(r)=ωBr/2`. Integrating `σE²` through the roof disc and cylindrical skirt separately yields:

`P_roof = π ω² B² t R⁴ / (8 ρ_e)`

`P_skirt = π ω² B² h (R_outer⁴ − R_inner⁴) / (8 ρ_e)`.

These are original elementary derivations; the model neglects field reaction, edge/concentration effects, joints, hysteresis and pan shielding. It assumes uniform current through wall thickness. Roof and skirt integrals use disjoint volumes; no wall volume is omitted or double counted. A transverse field requires a different three-dimensional current path and is not modeled. Using peak B in these RMS formulas doubles power; convert peak to RMS first. Harmonics may be summed as `Σ f_n² B_n,rms²` only when the linear low-reaction assumptions remain valid at every harmonic.

At 20°C the supplier table gives 316L resistivity0.75 µΩm, density8000 kg/m³, heat capacity500 J/kgK and conductivity15 W/mK. Higher resistivities1.125/1.5 µΩm and permeabilities1/1.05/2 in the sweep are **sensitivity cases, not temperature-property data or lot limits**. Supplier describes the annealed grade as not magnetizable; forming/welding effects still require testing. This model does not calculate hysteresis loss and cannot bound a magnetic cap.

Two dimensionless engineering screens are printed: wall thickness/skin depth, with `δ=sqrt(ρ_e/(π f μ))`, and thin-sheet reaction `μσω R max_wall`. Both must be≤0.3 and μr≤1.05 to receive SMALL_PARAMETER_SCREEN. These conservative heuristics identify where an unshielded calculation is plausible; they are **not validated error bounds**. Normal20–60kHz operation for the selected closed skirt lies outside this combined screen at room resistivity. OUTSIDE_SMALL_PARAMETER_REGIME rows are extrapolated sensitivities only, not accepted predictions or rigorous upper bounds. Pan/ferrite field redistribution can move losses either way.

`deltaT_if_G` divides predicted unshielded power by explicitly assumed total conductances0.01/0.1 W/K. It is a steady incremental temperature sensitivity, not actual pan error. The initial adiabatic slope uses full cap volume and ignores heat flow. Resolve actual heating with instrumented calorimetry/paired cap-temperature measurements or validated 3-D field/thermal analysis using measured material and coil geometry. A thermal fit to coil-off data cannot identify induction heating.

## Lead and converter coupling

`lead_coupling.csv` computes open-loop differential pickup `V_rms=ω B A_effective`, and divides by current×0.385 Ω/K to display an **unfiltered low-temperature equivalent**. It is not ADC error: winding cancellation, converter filtering, common-mode rejection, rectification, nonlinear protection and thermal response are missing. At higher pan temperatures use the measured RTD sensitivity or the applicable Callendar–Van Dusen derivative. Capacitive common-mode injection follows `I=C_parasitic dV/dt`; actual capacitance and edge rates are missing. Tiny plausible parasitics can couple drive edges into RTDIN and the independent contact channel; measure both paths.

The MAX31865's 50/60 Hz filter does not prove immunity at20–60kHz. Its one-shot conversion takes approximately52/62.5ms; after enabling bias, its one-shot section specifies settling10.5 input-RC time constants plus1ms. Record real DRDY times and exact filter/bias settings. A millisecond PWM blanking interval cannot be assumed to contain a fresh, settled converter reading. Changing RC to reduce EMI changes settling and fault timing, so retest the complete inhibition latency.

## Paired measurement and uncertainty

Each CSV row is a window estimate, not an unfiltered sample. Three independent off→on→off bracket pairs are required. The algorithm linearly interpolates baseline `sensor−local_pan_reference` between off windows at the on-window time. Subtraction removes **linear error drift**; nonlinear thermal lag, cap self-heating and spatial heating changes remain confounders. For electronics-only tests replace the RTD with a calibrated dummy mounted in the same lead geometry; then test a real cartridge separately. Never subtract a real temperature rise as if it were noise.

The reference agreement check uses an independent second reference, ideally optical/fiber rather than another electrically similar thermocouple. Coherent EMI in two similar references can fool agreement, so record dissimilar technology and shield/routing trials. An allowed offset for spatial gradient must be supported by separate coil-off mapping. Invalid reference comparison invalidates the pair.

`paired_expanded_uncertainty_c` is a precomputed expanded bound covering calibration, temporal interpolation, window repeatability, reference placement, drift curvature and electrical reference susceptibility. Do not divide systematic calibration error by √N. Use covariance only when supported; otherwise sum correlated/unknown-correlation contributions conservatively. Each pair passes only if `abs(effect)+U <= approved budget`. Sample budgets in SYNTHETIC fixtures are solely software examples, not safety or accuracy allocations.

## Sources

* [Outokumpu Supra datasheet, PDF p.8 Table7, p.9 forming discussion](https://www.outokumpu.com/-/media/files/products/supra/outokumpu-supra-range-datasheet.pdf?modified=20251117111951&revision=7a909396-d1f3-4d36-9c1c-99606be41fd2): candidate316L physical properties and forming context.
* [Analog Devices MAX31865 datasheet, PDF pp.11,13,19](https://www.analog.com/media/en/technical-documentation/data-sheets/max31865.pdf): filter, conversion/bias settling, differential filtering and fault operation.
* [MIT6.622 Lecture38, PDF pp.1–3](https://ocw.mit.edu/courses/6-622-power-electronics-spring-2023/mit6_622_s23_lec382.pdf): current-loop geometry and capacitive coupling tradeoffs. Applied recommendations here are engineering inferences.
* [MIT6.622 Lecture35, PDF pp.1–3](https://ocw.mit.edu/courses/6-622-power-electronics-spring-2023/mit6_622_s23_lec352.pdf): resonant behavior depends on load; it supplies no local Temper coil field or certification limits.

Sources inspected2026-10-04. No standards clause, leakage current limit, insulation test voltage, cleaning-life count or certification scope has been invented; these remain product/lab requirements to approve before measurement.

Exit codes:0 means a completed sensitivity/synthetic run or a measured screen within its configured limits;1 means a measured screen exceeded a configured limit;2 means incomplete/invalid evidence. Always read the evidence label: a SYNTHETIC exit0 is never a physical pass. Both the Rust CLI and wrapper verify the raw CSV digest. See FINDINGS.md for quantitative scale and TEST-PLAN.md for acquisition, spatial mapping, endurance and fault-injection procedures.
