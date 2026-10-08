# Power-stage audit and source receipt

Captured 2026-10-03 on macOS, working directory `/Users/bennet/Desktop/temper/zapote/power-stage-120v`. The inputs were already present; no Atopile regeneration, shared Cargo build, pyo3 build, or product-file edit was performed. `rustc --version`: `rustc 1.92.0 (ded5c06cf 2025-12-08)`.

## Reproduced audit

Command:

```sh
rustc --edition=2021 -O audit.rs -o /private/tmp/temper_ps_audit && /private/tmp/temper_ps_audit build/default.net build/default.csv build/resolved-components.json
```

Process exit status: **0**. Output:

```text
components 91, nets 67
PASS: power-stage-120v connectivity audit
```

## Reproduced tests

Command:

```sh
rustc --edition=2021 --test audit.rs -o /private/tmp/temper_ps_audit_tests && /private/tmp/temper_ps_audit_tests
```

Process exit status: **0**. Output:

```text
running 17 tests
test tests::header_pin_swap_fails ... ok
test tests::non_default_low_isolator_fails ... ok
test tests::low_side_source_bypassing_shunt_fails ... ok
test tests::irm05_line_neutral_swap_fails ... ok
test tests::permit_gate_without_pulldown_fails ... ok
test tests::missing_dis_pullup_fails ... ok
test tests::bootstrap_diode_reversed_fails ... ok
test tests::built_netlist_passes ... ok
test tests::bom_alias_fails ... ok
test tests::isolator_output_on_hot_side_fails ... ok
test tests::fuse_bypass_fails ... ok
test tests::gate_supply_bypassing_tco_fails ... ok
test tests::selv_ground_tied_to_hot_fails ... ok
test tests::swapped_ocp_comparator_inputs_fail ... ok
test tests::resolved_identity_swap_fails ... ok
test tests::swapped_shunt_current_terminals_fail ... ok
test tests::resonant_capacitor_bypass_fails ... ok

test result: ok. 17 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
```

## Input hashes

SHA-256, computed with `shasum -a 256` from the source checkout; build-artifact values match `build-receipt.json`:

```text
64b944618d31eb58d5ecf811d234dd69be00d727ef24226074ed71d3f7837f0f  audit.rs
ecfbf62dcdd027110e5e8d15af29f0f6014f5e153d55268a283a2413caa1c5fb  elec/src/power_stage_120v.ato
2cd6619bf4ef98067f642814302e296278da5d47fd4dd61d8f88f3fcb57260f4  elec/src/parts.ato
c786caa297eaeaa957c80fa52794ff91f56d35acbdce36a7888be1870d824863  build/default.net
8f83aa127550526191d3025f93efd9f8d28f4b764520cc1d4fc0e0a6d2d5c7a1  build/default.csv
49200589ffd070d4375ffb0e8b0558233a031bae5d7795278ed7dd8e5e3f9190  build/resolved-components.json
```

## Manufacturer source for 942C rating

Downloaded the *entire* six-page PDF directly from manufacturer CDE using `curl -L --fail --silent --show-error` to `CDE-942C.pdf`; exit status **0**, size **306,629 bytes**, SHA-256 `f99395446ba25a0adcef85862ff9eaee90bac68fae6664decccab1ebea3e4310`. Source URL: <https://www.cde.com/resources/catalogs/942C.pdf>. PDF metadata reports Adobe InDesign 16.2, creation/modification **2021-11-16**; no printed revision identifier was found. `pdfinfo` reports six pages. The CDE page marked **3** (PDF page 3), saved as `CDE-942C-page3.txt` from `pdftotext -f 3 -l 3 -layout`, groups exact parts **942C12P1K-F** and **942C12P22K-F** under the printed **1200 Vdc (430 Vac)** heading. The first page says the catalog's AC voltage range is rated at **60 Hz**; page 4 has RMS-voltage-versus-frequency curves at 25°C, so 430 Vac is *not* a verified 35 kHz allowance. The two parts have catalog 100 kHz, 70°C RMS-current entries 9.2 A and 10.3 A on page 3, which are also not a full waveform/current-sharing validation.

The calculation in the review is `650 Vpk / sqrt(2) = 459.6 Vrms` **only if the capacitor waveform is sinusoidal**. This exceeds the catalog's 430 Vac, 60 Hz nameplate. The exact 35 kHz permissible waveform/voltage remains pending interpretation of the frequency curve and confirmation with CDE; the review flags the model's 650 Vpk pass criterion as unsupported, not a proven in-service overvoltage. The screenshot-like plot on page 4 should not be converted to a precise number by text extraction alone.
