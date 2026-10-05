# R5 thermal result and decision

**Keep D8 as the reference and build D6 as a comparative dry coupon. Neither design clears the complete target.** D6 reduces the retained face's spreading distance and thermal mass, but smaller contact area also reduces the conductance predicted by the assumed pressure law. Covers, bond films and complete routes consume some of the previously optimistic response margin.

| Same0.218182N force, href2000 hypothesis | t90 own, s | t90 pan, s | Underread at200°C |
|---|---:|---:|---:|
| D8 uniform |3.17|3.44|2.438°C|
| D6 uniform |2.69|2.94|2.474°C|
| D8 centralØ4mm |—|3.55|2.816°C|
| D6 centralØ4mm |—|3.00|2.881°C|
| D8 rim |—|9.81|6.552°C|
| D6 rim |—|7.35|5.742°C|

Unlike R4's controlled equal-G location comparison, these cases recompute G from force and contact area. Central contact therefore does not automatically improve the assembled result: its smaller area decreases G under the uncalibrated law. The model is not evidence that an actual surface follows this law.

D6 uniform with the higher href4000 hypothesis gives1.96s t90-pan and1.442°C thermal underread. That is conditional, fails a1°C thermal allocation and does not establish whole-system±2°C. Nominal D6 uniform needs about0.182711W/K for2s and1°C together. Higher-loss assumptions require0.420021W/K. Rim-contact cases find no solution up to0.5W/K for either bias budget. See the exact scenario assumptions in requirements.csv; these are not universal conductance specifications.

At the end of a5°C/s35-second ramp to200°C with glass/body held25°C, D8 uniform reads189.270°C and D6 reads190.216°C. These include cold-boundary heat loss and transient lag. They cannot be compared directly with the200/80/60°C steady table and do not predict closed-loop overshoot.

The rigid-pan screen contains216 cases:150 within the stated spring/travel/support-hull screen,36 without reach,30 requesting more spring force than the pan tipping threshold. These counts are deterministic scenarios, not reliability probabilities. The requested spring force in rocking rows is not an equilibrium force prediction.

Of30 D6 geometric ear-clearance cases,4 severe tilt/curvature combinations permit recessed-ear contact. In those cases the face-only thermal assumptions are invalid. Positive clearance alone does not establish a contact patch.

## Verification

The final standalone runner passed25 tests:14 inherited kernel tests and11 R5 tests. It passed rustfmt, rustc-Dwarnings and direct clippy-driver-Dwarnings. New checks cover upper-stop/series-spring balance, independent cylinder volume, cylindrical thermal resistance, contact-area integration, equal boundaries, step energy, analytical wire conduction, complete Cu/PFA/weld capacity, the independently collapsed isothermal-cap limit and spatial/wire/time refinement.

Eight CSV files contain784 rows. The full SHA256 input manifest is checked before every run; results/run-inputs.sha256 records the actual final source, kernel, CAD scalar and comparison bytes. That receipt is consumed by the validation package to reject stale geometry results.

No physical result, supplier acceptance, seal qualification, contact-fault coverage, induction test or firmware enablement is implied. The CAD is a dry engineering prototype candidate, not a released product cartridge.

Review correction: the anchored1mm copper segment now contributes half its axial resistance to each adjacent wire link. A full60mm axial-path test reads the assembled network edges and matches the independent conductor-length resistance. Restoring both omitted half-lengths as a mutation makes that test fail. The runner captures test output before formatting, so a failing test exits before producing results.
