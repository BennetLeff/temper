# Integrated verification — 2026-10-04

All results below are software execution or geometry checks. Physical cartridge and induction tests remain **NOT_RUN**. Worktree: `/Users/bennet/.codex/worktrees/glass-sensor-simulation/temper`.

| Check | Integrated result | Evidence |
|---|---|---|
| Selected-part Rust models | 20 tests pass: 14 inherited solver/mechanics + 6 new part checks | `logs/parts.log` |
| Selected-part numerical replay | 21,870 mechanics + 5,832 thermal + 486 material cases; all three CSVs and summary exactly match committed bytes | `logs/parts-replay-hashes.txt` |
| CAD replay | Four states × 22 valid solids; STEP round-trip valid; zero rigid, spring/stem and spring/wire-envelope intersections; geometry JSON matches exactly | `logs/parts.log`, `logs/parts-replay-hashes.txt` |
| Cartridge harness | 17 Rust tests and 12 executable rejected-input controls pass; distinct analytical holdout fixtures | `logs/bench.log`, sibling `bench_validation/evidence/negative-controls.txt` |
| Induction harness | 22 Rust tests pass; 540 cap + 72 lead sensitivities; 840 synthetic hotspot rows | `logs/induction.log` |
| Host control suites | **15/15 registered CTest suites pass**, including newly registered fault-ID regression | `logs/ctest.log` |
| Real contact guard/control | 18 tests including 300 state/timing combinations; hardware outputs mocked | `logs/contact.log` |
| Persistent fault IDs | 6 tests pass; existing IDs 0–13 preserved and contact appended as 14 | `logs/fault-ids.log` |
| Fault-ID test-runner negative control | Wrong expected contact ID gives 1 failure and **process exit 1** | `logs/fault-runner-mutant.log` |
| Gate-removal negative control | Workstream isolated mutant fails 13 tests | sibling `contact_detection/evidence/gate-removal-mutant.txt` |
| SIL designed fault/state coverage | 23/23 covered, none missing | `logs/sil.log` |
| Original study input integrity | All 14 frozen input hashes still match; baseline study not silently repinned | `logs/baseline-inputs.log` |
| Import boundary gate | 5 contracts kept, 0 broken | `logs/import-gate.log` |
| Derived artifacts | `make regen` and `make regen-check` pass without generated-file drift | `logs/regen.log`, `logs/regen-check.log` |
| Presentation/source checks | New report renderer and CAD adapter pass Ruff; plot inspected; local links and SVG XML checked | `logs/artifact-checks.txt` |

Counts overlap: the contact and fault-ID executables are included in CTest, and selected-part tests reuse 14 original tests. Do not sum these rows into a unique-test total. The child's historical evidence records 14 CTest suites; integration adds the existing fault-list executable as the 15th and fixes its formerly unconditional zero exit status.

## Reproduction

From repository root; Python on PATH must provide PyYAML and Jinja2 for firmware generation. These commands do not build or install pyo3 extensions.

```sh
CAD_PYTHON=/path/to/cadquery-python bash packages/temper-thermal/studies/glass_sensor/parts_revision/run.sh
bash packages/temper-thermal/studies/glass_sensor/bench_validation/run.sh /tmp/temper-bench-replay
bash packages/temper-thermal/studies/glass_sensor/induction_validation/run.sh
cmake -S firmware/test -B /tmp/temper-glass-build
cmake --build /tmp/temper-glass-build --target test_runner test_state_machine_only test_max31865_only test_pid_only test_cascade_pid_only test_cascade_pid_integration_only test_thermal_mass_only test_low_temp_only test_safety_only test_pan_detection_only test_pll_only test_integration_only test_sil_fault_injection test_contact_interlock test_fault_list_only -j 4
ctest --test-dir /tmp/temper-glass-build --output-on-failure
python firmware/test/test_sil_coverage.py --gate
python packages/temper-thermal/studies/glass_sensor/audit.py packages/temper-thermal/studies/glass_sensor . /tmp/unused before
uv run python scripts/import_linter_gate.py
make regen
make regen-check
```

Saved log copies and presentation SVGs have trailing whitespace normalized; numerical values and test outcomes are unchanged.

The parent replayed CAD in a disposable copy at `/private/tmp/temper-glass-hardening-reproduce` so exporter timestamps would not rewrite the delivered STEP files. It compared numerical and geometry outputs by full SHA-256. Import sorting was subsequently cleaned up in the CAD adapter without changing construction logic. Matplotlib renders only the selected Rust output; it contains no physics implementation.

Tools used: rustc 1.92.0, CadQuery 2.6.1, Python 3.12.12 for analysis/rendering, the available Apple C toolchain and CMake. Exact workstream toolchain details are preserved beside their results. No Cargo shared build cache or installed Rust extension was modified.

## Limits and failed checks retained

The **all-target firmware build is not green**. Unchanged `firmware/test/test_profiles.c` passes pointers to integer `TEST_ASSERT_EQUAL` macros; AppleClang rejects two calls. The contact workstream reproduced this from byte-identical source at the baseline commit; see `contact_detection/evidence/baseline-profiles-build.txt`. The target is outside the registered CTest set. No ESP-IDF target build was performed.

The existing PAN_DET fan-interlock gap and commented production burst-control calls remain documented, unrelated integration limitations. Host command assertions do not prove electrical gate waveforms or timing, detector performance, seal safety, EMI immunity or thermal accuracy.

Automated browser preview of the local HTML was blocked by the browser's file-URL policy. No alternate browser route was attempted. Local HTML links and SVG structure were checked as files, and the generated chart was visually inspected directly; a rendered whole-page browser screenshot is not available.

The deliberately bad fixtures and mutants are successful negative controls, not unresolved production failures. Empty physical templates continue to fail import or report NOT_RUN.
