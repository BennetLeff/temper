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
# Prototype closure follow-up — 2026-10-04

- **Production behavior changed:** no. No PCB, trip resistor, firmware, coil data or operating limit was changed by this power workstream. Added a conditional SPICE experiment and source-grounded component/chain findings.
- `bash zapote/power-stage-120v/prototype-closure/power/run-conditional.sh /Users/bennet/Desktop/temper/worktrees/ps-oracle`: historical instrument baseline exact; 72 nominal cases, 3 time-step refinements and 6 temperature probes complete with all seven required measures and no aborts. Refinement and temperature extensions were executed as the matching isolated loops after the initial 72-case run; the final script incorporates them for subsequent reproduction.
- Original `i(Bload)` smoke measurement was unavailable. The inherited runner recorded that failure; the result-acceptance predicate rejects it. The implemented measurement derives the imposed source current at the measured first gate crossing and labels it as imposed current, not device current. No failed result entered the matrix.
- `bash -n .../run-conditional.sh`: PASS. No new Python source, package installation, shared Rust build, git/index mutation or source-checkout write occurred. Initial imports of `run_d2` failed because NumPy was unavailable; the experiment reuses the standard-library `run_ngspice.py` runner and verified explicit matrix coefficients instead.
- Re-read all 81 result records: exit/abort status, required measures, and data counts passed. Thermal run logs confirm the specified temperatures. Three 0.2→0.1 ns refinements changed reported VDS by ≤0.718 V, gate metrics by ≤2.771 mV and first crossing by ≤0.19 ns.
- `raw-evidence.tar.gz`: all 332 regular members re-read and SHA-256 verified against `evidence-manifest.json`. No vendor library, datasheet, symlink or hardware measurement is included. Local ignored outputs retain the simulator's copied model.
- Physical coil/capacitor/fault/thermal tests remain **NOT RUN**. Missing interlock/receiver/harness bounds, actual operating envelope and complete D17 device-survival/energy cases remain open.

## Reproduction preflight review fix — 2026-10-04

**Harness behavior changed; circuit behavior and measured evidence did not.** Previously the reproduction script executed the external runner before checking its input identity, and accepted any first falling crossing. It now runs `preflight.sh` before output creation or simulation, validating seven owned inputs and the archived hashes of the external runner, vendor model and options. An unsupported ngspice version fails closed. The shared jq acceptance predicate requires a first crossing after the pinned deck's `T1=2 µs` plus explicit `TD`; an unexpected `T1` override is rejected.

Focused verification, recorded in ignored `output/temper-prototype-closure/power/preflight-verification/`:

- `bash -n .../run-conditional.sh .../preflight.sh`: passed.
- Seven independent copied-input negative controls appended one comment to each of the two decks, matrix file, matrix parameters, external runner, vendor library and options file. Each invocation of the actual `run-conditional.sh` exited 1 at the appropriate hash mismatch. A sentinel `ngspice` on PATH recorded **zero invocations**, including zero version queries; no output directory was created. Original files were not modified.
- With unmodified copied inputs and a sentinel reporting `ngspice-99.0`, the actual script exited 1 for unsupported simulator. The only invocation was `--version`; no simulation ran.
- `bash .../preflight.sh /Users/bennet/Desktop/temper/worktrees/ps-oracle` passed against the real source and ngspice 45.2. The baseline command from `run-conditional.sh`, with the same matrix and `VBUS=170 IL=37 DIR=0 DT=348n TRMAX=0.2n LESL=1.06n`, was run in `preflight-verification/positive-baseline`. Its exact existing assertion passed again: VDS 203.6704 V and off-gate VGS 2.234341 V; no abort or failed measurement. This remains a historical instrument check.
- Every one of the **81 archived** conditional JSON records passed `jq -e -f .../accept-conditional.jq`; minimum/maximum first-crossing offsets were 352.66/407.81 ns. A synthetic 1 µs pre-command crossing and an unexpected `T1` override both failed the same predicate (exit 1). No new circuit sweeps were necessary.
- All 332 original archived member hashes, the archive hash, deck/matrix pins, numerical CSV and summary pins remain unchanged. Only authored harness hashes were refreshed; external pins and expected simulator identity were added from the archived original record. The negative-control outcomes are in `preflight-verification/verification.json`; the positive result, simulator log and assertion output are adjacent.
