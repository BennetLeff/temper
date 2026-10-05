# R5 validation and manufacturing release package

Stage: controlled dry engineering-prototype preparation. Physical evidence: **NOT_RUN** for every gate. No cooking enablement or qualification claim. This package makes each remaining gate inspectable and records executable sensitivity analyses; it cannot turn planned measurements into closure.

## Requirement authority

Recent user-approved in-glass development targets are response <2 s and whole-system error <2°C; R4 proposes thermal steady-bias ≤1°C to leave an error reserve. These are development objectives, not demonstrated product requirements. Specify t90 against the actual pan step, not only the final biased sensor value. Dynamic accuracy during ramps needs a separate heating-rate envelope.

The original study's S01/S02 ±2°C at40–100°C and ±5°C at100–250°C, and S03 t90≤3s, are older planning targets. `docs/SENSOR_MOUNT_DESIGN.md` describes a different UNDER-glass design (≥2N,5mm travel,12×3mm aluminum and10k cycles). Those dimensions, loads and life targets do not transfer to this in-glass candidate. Cooking/cleaning media, temperature overshoot, duty, lifetime, leak limits and EMI allocations need a product-owner/qualified-lab decision before physical acceptance criteria are frozen. Never substitute a sample synthetic evaluator threshold for that decision.

## Error budget

Final reviewed R5 output: all36 scenarios miss the joint development screen after the proposed1°C reserve; the smallest full planning bound is2.442073°C. At uniform contact,0.218182N force and href2000, D8 gives3.44s t90-pan and3.437675°C planning bound; D6 gives2.94s and3.474231°C. These include the corrected finite anchor axial resistance. They remain simulated bounds with hypothetical allocations, not achieved whole-system accuracy.

`results/current_thermal_budget.csv` consumes every current R5 `../thermal/results/comparison.csv` row directly, preserving its candidate, contact pattern, force, loss and response assumptions. It adds the proposed1°C nonthermal reserve and screens steady bound<2°C and joint t90-pan<2s separately. The analysis fails when the required current thermal file is missing, empty or invalid; it never falls back to old output. Its input SHA256 is recorded with the CAD scalar input. The runner requires and verifies the thermal post-run `results/run-inputs.sha256` receipt, tying the current geometry, thermal source, kernel and comparison CSV together; absent or stale receipts fail before analysis. Even a passing allocation remains SIMULATED and unvalidated.

`results/error_budget.csv` provides illustrative historical/allocation examples and sums absolute bounds conservatively: thermal bias plus proposed0.25°C installed calibration,0.25°C frontend/current/reference resistor,0.20°C induction effect and0.30°C reference/pan spatial allowance. These allocations total the proposed1°C reserve; none is measured, supplier-guaranteed or uncertainty-certified. Avoid double counting: characterize installed calibration residual separately from frontend drift after calibration; reference uncertainty is part of a guarded verification result, not a second physical sensor error. RSS requires evidence for distribution and covariance and is not used here. A1.92°C nominal thermal error leaves insufficient reserve: this planning sum is2.92°C.

`ramp_scale.csv` is only the single-pole relation lag≈rate×t90/ln(10). It explicitly takes t90-own, not t90-pan. The real multi-node spatial model must provide dynamic predictions and independent holdout runs. No estimator is fitted or controller enabled.

## Induction scope

`main.rs` reads `../mechanical/thermal_geometry.csv` directly from the current CAD generator. It screens roof power using P=πω²B_rms²tR⁴/(8ρ), skin depth and thin-sheet reaction. This is the inherited elementary Faraday derivation from `../../induction_validation/README.md`; RMS field convention is maintained. It neglects field reaction, actual pan/coil shielding, hooks, welds, harness and magnetic hysteresis. Values of0.1/1/5mT are sensitivity inputs, not predicted Temper fields. Resistivity0.75µΩm is the inherited room-temperature316L assumption;1.125/1.5µΩm are sensitivity cases, not temperature data. Smaller roof radius improves this geometric screen at fixed field but does not predict actual cartridge self-heating. The earlier small-parameter screen (t/δ≤0.3 and reaction≤0.3 withµr≈1) is a heuristic, not a rigorous error bound.

Pickup uses V_rms=ωB_rms A_effective. Swept effective areas are hypothetical residual loop areas, not a CAD claim. A twisted harness's visible envelope is not its electrical loop area; capture both outgoing/return routing, pitch, terminal fanouts and common-mode coupling. Equivalent temperature uses the PT100 Callendar–Van Dusen derivative at200°C and illustrative0.3mA. It is unfiltered open-loop scale, never converter error. Preserve existing full-assembly paired dummy-RTD and real-cap test plan.

Source basis remains the pinned earlier study's Outokumpu316L and Analog Devices MAX31865 sources in `../../induction_validation/README.md`; no new part qualification is claimed. Actual wound/formed/welded permeability and hot resistance remain physical inputs.

## Reuse existing acquisition tools

Use `../../bench_validation/bench.rs` and `../../bench_validation/run.sh` for raw mechanical/thermal analysis and calibration/holdout separation. Use `../../induction_validation/run.sh paired RAW META` and `endurance RAW META` for induction evidence, with full hashes and actual measurement provenance. Existing scripts explicitly distinguish SYNTHETIC from MEASURED and reject incomplete physical records. Do not create a parallel importer or label its exit0 as qualification.

`templates/` extends the existing empty acquisition templates with gap-specific evidence and uncertainty attribution. All observation/result fields remain NOT_RUN. Keep raw high-rate traces; do not populate rows with simulation values. Review the proposed limit's origin and approver before measurement. Reproduction uses standalone rustc, no Cargo/pyo3 cache.

## Manufacturing walk-through

1. Incoming inspect exact sensor/lead lots, cap material/finish/flatness, seal compound/geometry and posts. Reject substitution by nominal dimensions alone.
2. Form/weld hooks with fixture access; inspect each capture gap and weld before bonding. Coupon-section the process; base-metal strength does not qualify weld peel or hot fatigue.
3. Locate sensor/bond using controlled spacers and cure fixture; record actual supplier cure schedule for the received lot. Measure cured bond thickness/voids on sacrificial articles. No invented cure temperature/time.
4. Join native terminals with a qualified weld method and exact Kelvin datum. The join covers and strain relief move with the cap; inspect tool access before immobilizing them. Covers must protect every exposed joint through cap lift and local/main stroke.
5. Install intact insulated extensions and full developed route with recorded slack/bend radii; inspect every motion pose and measure force contribution. Route geometry alone does not prove flex life or insulation.
6. Install the pressure/liquid boundary, optics and static feedthrough using supplier-approved gland compression. Measure final stiffness, friction, pressure bias and complete harness force; separate allocated force from measured result.
7. Inspect downstream cap-to-hook-to-island-to-upper-catch-to-housing load path. Run cap-only uplift and full-cartridge off-axis drag independently, then repeat shape/insulation/contact/thermal checks.
8. Archive article serial, BOM/CAD/source hashes, operator/process record and calibrated measurements. A build change affecting seal, wire route, anchor or weld invalidates associated thermal/force/induction results until retested.

Prototype quantities and production volume are unspecified. Custom thin-cap forming/weld quality, membrane tooling and repeatable bond placement require supplier process review before a pilot; this package supports neither process capability nor production release.
