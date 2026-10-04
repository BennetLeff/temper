# Verification record — 2026-10-04

All edits belong to the MIT guidance checkout. `ps-oracle` was read only. No shared Cargo target, installed extension, firmware output, native board or external service was changed.

| Check | Result |
| --- | --- |
| Current source identity | `ps-oracle` HEAD `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`; no tracked changes. Candidate starts at `dea4649ff466cf36b49a0523d8232c94c317b163`. Full input hashes in adjacent JSON. |
| Threshold model source compatibility | Existing `thresholds.py::validate_inputs` passes **24 exact MPNs and 12 required net groups** on native-18 frozen source and HOT5 frozen candidate. This covers the threshold inputs; it does not qualify added HOT5 output timing. |
| Conditional static replay | `exact_corners(-10, 50)` and `exact_corners(85, 50)` exactly equal the stored two temperature-corner objects. No Monte Carlo or SPICE was rerun. |
| Independent shunt arithmetic | KCL calculation from the stored adverse component vertices reproduces +85 °C min/max within `1e-9 A`: 38.43818403436644 and 85.5510328644967 A. This is an algebraic cross-check, not an external physical oracle. |
| Existing Rust arithmetic regressions | **11/11 pass**, standalone `rustc --edition=2021 --test`; no Cargo build. |
| Before/after emitted results | Optimized pre-edit executable reproduces the saved output exactly. Corrected executable retains **all non-comment lines byte-for-byte**. Only qualification text changes. Common rows SHA-256 `e0d9b51c6424f62a4d182d3eb4c132743a997c1ae42d348ff7d388494bd098fa`. |
| Warning regression | Pre-edit output lacks `CURRENT ENVELOPE UNRELEASED` and the independent shunt warning. Corrected output contains both detector bands, the unreleased status and explicit limitation on `model_full_power` fields. |
| Physical tests | **NOT RUN.** No coil, capacitor, fault-delay, cooling, emissions or energized prototype evidence was created. |

Reproduction of Rust runs from the repository root:

```sh
mkdir -p /private/tmp/temper-astra-power-20261004
git show dea4649ff466cf36b49a0523d8232c94c317b163:docs/hardware/power-section-120v/coil_mc.rs > /private/tmp/temper-astra-power-20261004/coil_mc_before.rs
rustc --edition=2021 --test docs/hardware/power-section-120v/coil_mc.rs -o /private/tmp/temper-astra-power-20261004/coil_tests
/private/tmp/temper-astra-power-20261004/coil_tests
rustc --edition=2021 -O /private/tmp/temper-astra-power-20261004/coil_mc_before.rs -o /private/tmp/temper-astra-power-20261004/coil_before
rustc --edition=2021 -O docs/hardware/power-section-120v/coil_mc.rs -o /private/tmp/temper-astra-power-20261004/coil_after
/private/tmp/temper-astra-power-20261004/coil_before > /private/tmp/temper-astra-power-20261004/before.txt
/private/tmp/temper-astra-power-20261004/coil_after > /private/tmp/temper-astra-power-20261004/after.txt
```

Compare output lines after removing only lines beginning with `#`; preserve blank lines, headers and every numeric row. The corrected full output is committed as `docs/hardware/power-section-120v/coil-mc-output.txt`. This is a warning/interpretation correction, not a new physical model or numeric operating limit.

The threshold replay loaded the existing `ps-oracle/zapote/power-stage-120v/validation-results/02-protection-timing/round3/thresholds.py` with `importlib.util.spec_from_file_location`, with `PYTHONDONTWRITEBYTECODE=1` and without calling its file-writing `main()`. It assigned the module's `UNIT` to each frozen source root for `validate_inputs()`, then called the pure corner functions. The script SHA and the complete results are pinned in [identity-and-threshold-check.json](identity-and-threshold-check.json). There is no copied Python model or competing source of truth in this package.

Manufacturer sources checked live: TI TLV3201 Rev C and Vishay WSK2512. CDE's manufacturer URL returned 403; the saved manufacturer PDF was inspected locally and hashed. Supplier questions explicitly request a current document and application-specific limits. No raw vendor PDFs were copied into this deliverable.
