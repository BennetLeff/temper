# Glass sensor revision 2

The developed candidate uses a positively retained Ø8 × 0.15 mm 316L cap, a zirconia spider, three local X750 flexures, differential optical bench metrology, a Kalrez 6375 seal compound candidate and a specified M222/bond/fine-wire coupon stack. **This is a dry instrumented prototype definition, executable simulation and test preparation. Physical qualification is NOT_RUN.**

[Open the engineering report](report.html). [Thermal model and input derivations](thermal/README.md). [Verification](verification.md).

The assembled model predicts **3.05 s to 90% of its own final step response and 4.42°C underread at pan 200°C**, against the inherited 6.46 s / 5.92°C middle case. New-case force is 0.218182 N from the series spring model, not an assumed 0.25 N. Contact, heat leakage and temperature boundaries remain uncalibrated. At equal 0.25 N, R2 M222 gives 2.81 s / 4.11°C. The smaller IST coupon gives 2.19 s / 5.14°C at the coupled force: faster, but worse DC error. Neither closes the accuracy objective across cookware.

## What to build and why

1. Use M222 for the first dry cartridge. Remove the heavy skirt and retain the cap using three welded hooks, independent of adhesive. The full cap has 73% less modeled heat capacity than PR1.
2. Isolate the head from the finite support mass. Use long thin zirconia posts and a sparse spider; include gas, radiation and lead cooling. A cold support can erase the light head's advantage.
3. Place the local sensing flexure above the main guide and seal. Measure island motion relative to carrier motion. Main-guide jams are separable only within a tight calibrated measurement and parasitic-force budget.
4. Specify, assemble and measure the installed bond and harness. Reducing bond thickness alone scarcely improves the old design. Fine-wire heat loss, thermal gradients and shared nickel lead resistance remain significant.
5. Treat the small RTD, dielectric plate and ceramic cap as comparison coupons. The ceramic cap does not fit the metal-hook retention process without another mechanical revision; AlN also needs grade-specific cleaning evidence.

## Packages

| Package | Deliverable | Limit |
|---|---|---|
| [Mechanical](mechanical/README.md) | Five full STEP positions, section, geometry checks and candidate BOM | Custom hooks, posts, clamps, seal molds and harness need supplier acceptance; envelope geometry is not a released drawing |
| [Contact](contact/README.md) | Load-path design, threshold/error budget, series force model, fault sweeps | Island seizure, seized rods, frozen values and insulating debris remain blind faults; no production backend enabled |
| [Bond and leads](bond_leads/README.md) | Exact RTD/wire candidates, weld/strain-relief/cure coupons, fin-loss model | Catalog ratings do not verify the complete bond, harness or wet dielectric barrier |
| [Induction](induction/README.md) | Topology screening, cap mass reconciliation, material and coil-on test requirements | Imposed uniform-field comparisons; no actual cooker EM/EMI prediction |
| [Assembled thermal](thermal/README.md) | Four-node Rust network, 432 mechanical/thermal cases, ramps and leakage budget | Uncalibrated properties and contact; no spatial thermal/structural FEA or closed-loop control validation |
| [Test preparation](TEST_PREPARATION.md) | R2 additions to the existing bench/induction protocols | All physical result rows remain NOT_RUN |

## What remains open

Kalrez 6375's 275°C manufacturer rating resolves a **compound-temperature candidate**, not the sealed assembly. Witness and wire passages are open. A static optical chamber/feedthrough and a cap-to-carrier fluid barrier must be designed together with the force budget. The added barrier can invalidate contact and thermal predictions.

The contact model has 5.83 µm loaded and 3.75 µm unloaded margins only when total error≤15 µm, residual force≤10 mN, load≥0.12 N and stiffness lies between1.6 and2.4 N/mm. Raw two-head metrology does not achieve that automatically. Main-jam removal works in the bounded simulation; island jam, rod jam and credible frozen readings do not. Keep firmware unavailable until a detector implementation and independent fault evidence exist.

Cap weld distortion/strength, thin ceramic post side loads, flexure lot/heat treatment, clamp fixity, lead joint/cover geometry, bond cure/voids and hot/cold wet endurance are unqualified. Local beam screening is not a fatigue release. The full sealed product cannot be claimed complete within a simulation-only task.

## Reproduce and preserve identity

- `cd thermal && bash run.sh` verifies pinned inputs and runs 23 tests plus eight CSV outputs.
- Follow each sibling README/runner for its independent replay. The CAD generator requires CadQuery2.6.1; Rust studies use standalone rustc1.92.0, avoiding the shared Cargo/PyO3 cache.
- `MPLCONFIGDIR=/tmp/temper-r2-mpl python3 build_report.py` renders recorded CSVs using Matplotlib; it does not own physics.
- `source-provenance.json` hashes the complete local R2 package (excluding itself), plus inherited source identities. Historical files and firmware are preserved.
- The induction `mechanical-geometry.snapshot.json` predates the final spider revision. Its cap volume/dimensions match final CAD. Its old support is not authoritative for assembled thermal analysis. Final `mechanical/geometry.json` and the thermal input derivation supersede it for the support.

All four Astra workstreams were integrated locally. No hardware was energized, parts purchased, supplier messages sent or changes published.
