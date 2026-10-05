# R9: quantify the cost of a supported bond process

This Rust adapter answers a limited question: how much would changing bond thickness or conductivity matter in the existing R7 thermal network? It does not supply a process approval, an enclosed successor CAD model, or a thermal prediction for Ceramabond 569. The separate P9 open material witness has different geometry and no RTD; these scores do not apply to it.

## Run and identity

Run `sh run.sh` from this folder after installation in `revision9/thermal`. For a scratch copy, set `TEMPER_GLASS_STUDY_ROOT` to the repository's `packages/temper-thermal/studies/glass_sensor`. Optional `TEMPER_R9_GEOMETRY` must match the pinned R7 geometry hash.

The runner hashes and snapshots the inherited R5 network, R6 package adapter, R7 geometry/adapter and this unit before compiling. It verifies the consumed copies, runs Rust tests, formatting and Clippy, and uses standalone `rustc`; no Cargo/shared Python extension build occurs. It invalidates any old success receipt before work and publishes a new receipt only on success. Failed runs can leave old CSVs; without a matching `results/run-inputs.sha256`, those are stale outputs.

Run `sh check_runner.sh` with the same environment to exercise bad source pins, bad geometry pins, an injected failing test and a corrupted consumed source snapshot. Each must fail and remove a seeded prior success receipt without writing new physics results.

## What changes

The inherited implementation fixes bond conductivity at 2.163418635 W/mK. This adapter supplies an equivalent resistance thickness `t_equivalent = t_actual × k_reference / k_scenario`, then restores the actual bond volume's heat capacity. This reuses both existing half-bond resistances without a second physics implementation. Tests check both resistance paths against their closed-form values, unchanged reference matrices, invalid/overflow inputs and equilibrium conservation.

All other geometry, contact, native-lead metallurgy, film location, thermal properties and boundary assumptions remain inherited. Changed thicknesses are parametric scenarios, not collision-checked cartridge geometry. Bond volumetric heat capacity stays at the explicitly assumed 2 MJ/m³K; it is not a measured property of an alternative adhesive. These sweeps do not explore all capacity uncertainty and are not confidence intervals.

`process_sensitivity.csv` contains 168 cases: two R7 package geometries × seven gaps (75, 100, 127, 150, 200, 254, 508 µm) × four hypothetical conductivities (0.5, 1, 2.163418635, 4 W/mK) × three contact scenarios (uniform href 2000/4000, rim href 2000 W/m²K). The thickness grid includes generic guidance endpoints and experimental choices; none is a declared minimum or manufacturing tolerance. No tested k is assigned to Ceramabond 569 or EP126.

The definitions of pan-relative t90, own-final t90, steady 200°C underread and finite 5°C/s ramp error are unchanged from R7. Glass/body are 25/25°C during the step and ramp; steady underread uses pan/glass/body 200/80/60°C. Boundary contributions are computed from the exact linear steady solution: glass contributes `120 × w_glass`; body contributes `140 × w_body`. Their sum must reproduce underread before rounding. These are contributions of the model's boundary temperatures, not uniquely identified physical conduction paths.

## Decision supported by the calculation

At the inherited k, uniform href 2000, nominal losses:

| Package | Bond | Pan-step t90 | Thermal underread at 200°C |
| :-- | --: | --: | --: |
| M222 | 75 µm | 2.78 s | 2.441°C |
| M222 | 100 µm | 2.91 s | 2.474°C |
| M222 | 127 µm | 3.04 s | 2.510°C |
| M222 | 200 µm | 3.40 s | 2.607°C |
| M222 | 254 µm | 3.68 s | 2.678°C |
| IST308 | 75 µm | 2.05 s | 2.577°C |
| IST308 | 100 µm | 2.16 s | 2.637°C |
| IST308 | 254 µm | 2.80 s | 2.991°C |

Reducing the M222 bond from 100 to 75 µm buys about 0.13 s and 0.034°C here. A 100 µm process therefore deserves characterization before aggressive thinning. At the same 100 µm M222 geometry, changing hypothetical k from 0.5 to 4 W/mK moves response from 4.09 to 2.73 s; choosing a material on its cure schedule alone is insufficient.

For the M222 100 µm nominal case, the 60°C body boundary contributes 2.263°C of the 2.474°C underread, versus 0.211°C from the 80°C glass boundary. That supports separately varying body temperature in the bench campaign. It does not prove which physical wire, seal or support path dominates, or that moving the body temperature in a model is a buildable fix.

Eight refinement rows compare coarse/fine discretizations at fast thin/high-k and slow thick/low-k endpoints. Maximum observed changes are 0.110 s in pan t90 and about 0.0345°C in steady underread. These bound the sampled numerical change only, not material/contact uncertainty. Baseline CSV reproduces all three nominal R7 results.

All physical results remain **NOT_RUN**. No compensation or control backend is enabled by this study.
