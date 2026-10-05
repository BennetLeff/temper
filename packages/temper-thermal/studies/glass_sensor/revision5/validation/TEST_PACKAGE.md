# Physical test preparation — NOT_RUN

This is a future acquisition package, not authorization to operate hardware. Freeze the candidate and approve missing use-envelope/limit fields before executing. A qualified operator/lab owns hazardous electrical/thermal testing and product compliance limits.

| ID | Discriminating comparison | Record | Acceptance rule and origin | Result |
|---|---|---|---|---|
| V01 | Identical cap tested with full face, center patch, rim ring and one-sided contact at matched total force | independent local pan, cap center/rim, anchor and body temperatures; heat-shunt estimate; force; surface map | joint steady guarded error and t90-pan over declared envelope; development target<2°C/<2s, not fitted-G alone | NOT_RUN |
| V02 | Heat cavity while cap/pan reference stays controlled; repeat with pressure balancing path deliberately obstructed | both cavity pressures, effective area, local displacement, residual force and temperatures vs time | proposed3mN pressure allocation; approved final bounds pending | NOT_RUN |
| V03 | Actual seal/glass/feedthrough assembly in cooking/cleaning media before/after hot wet cycling | exact material lots, compression endpoints, leak method, stiffness and hysteresis; fogging |250°C compatibility requested; overshoot, duty, leak limit, media and cycles require product/lab definition | NOT_RUN |
| V04 | Remove pan with main guide held, then local island held, then witness held; inject advancing frozen samples; add insulating load-bearing debris | true independent pan separation, both detector channels, sample timestamps and inhibition timing | every claimed covered fault must inhibit within declared latency; remaining blind equivalence states prevent qualification | NOT_RUN |
| V05 | Cap-only pull versus full-cartridge pull and off-axis drag; force one hook to engage first | each gap, cap deformation, weld/post/catch inspections and force-displacement curves | loads/cycles from handling envelope;1N/2N historical screens are not acceptance limits | NOT_RUN |
| V06 | Sacrificial bond/anchor sections and terminal-weld sections alongside installed-article thermal tests | cured bond thickness/voids, received cure revision, coverage, joint/cover location, resistance/Kelvin datum | supplier process specification plus measured performance; nominal dispensed volume insufficient | NOT_RUN |
| V07 | Move full harness through rest/load/stop/full-stroke/cap-lift hot/cold states | developed length, minimum bend radius, cover clearances, force/hysteresis, insulation and post-cycle cracks | proposed4mN harness/witness residual allocation; supplier wire constraints and approved insulation/cycle limits pending | NOT_RUN |
| V08 | Calibrate on one declared subset; evaluate untouched cookware/force/surface/boundary combinations | raw curves, reference calibration, fit identities and independent held-out errors | abs(error)+expanded uncertainty within final declared limit; do not refit holdout or offset away changing contact bias | NOT_RUN |
| V09 | Calibrated dummy RTD on installed harness under coil-off/on/off, then real cap with dissimilar temperature reference | electrical pickup/rectification, actual cap self-heating, pan hotspot map, independent reference agreement and contact-channel behavior | approved induction budget and complete inhibition timing; dummy pass does not establish real-cap thermal pass | NOT_RUN |
| V10 | Repeat V01/V03/V04/V07/V09 after declared environmental/cleaning/thermal stresses | original and final article hashes/serials, drift, leakage/insulation and fault coverage | product/lab-approved stress schedule and guarded bounds; no universal life/certification claim | NOT_RUN |

## Trace and data discipline

Before each run record exact CAD and BOM/source hashes, serial and lots, installation inspection, calibration certificates/expiry, reference technology/placement, clock synchronization, acquisition gaps, boundary temperatures, pan material/thickness/curvature/surface, force, and raw file SHA256. Keep photos and unedited high-rate files under the same record ID. `templates/gap_measurements.csv` is the summary; link the complete record rather than replacing raw data with a scalar.

Include uncertainty of force, displacement, pressure and elapsed time as well as temperature. Reference drift, placement and calibration are systematic terms and do not shrink with more samples. Actual cap induction heating must not be subtracted as electronics noise. Data taken with inadequate reference bandwidth or coherent EMI does not qualify the thermal response.

Negative controls must remain in the record: insulating film carrying force, a plausible frozen contact trace, pressure-biased no-pan state, unbalanced thermal field and unequal-hook loading. An unexplained good result is not evidence that these challenges were achieved; capture independent ground truth.

## Existing evaluator invocation

Build `../../bench_validation/bench.rs` with standalone `rustc` and use `thermal`, `mechanical`, `budget` or `calibrate` as documented in its README. Its original empty acquisition template was rechecked for R5 and rejected with "at least five acquired samples required; empty templates are NOT_RUN". Our gap table is review metadata and is not an alternate raw-data schema. Use the existing raw templates for those tools.

For induction use the existing `../../induction_validation/run.sh paired RAW.csv RUN.meta` or `endurance RAW.csv RUN.meta`. Its numerical acceptance only applies to explicitly configured limits and provenance, not all nine release gates. Use the existing bench uncertainty input schema for executable uncertainty aggregation; our expanded uncertainty worksheet is a human-reviewed source mapping, not directly importable.
