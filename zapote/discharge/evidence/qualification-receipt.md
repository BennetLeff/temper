# Discharge U3 qualification-readiness receipt — 2026-09-23

Status: **INDETERMINATE for hardware qualification; standalone construction not accepted**. This is a digital preparation milestone. No native discharge circuit, assembled article, energized test, adopted product criterion, or independent physical review was created in this run.

## Identity and replay

- Source revision: `afb8b9e31cf03ef12b1cb246a89803f333dee6e0` (`codex/zapote-discharge-u3-readiness` base).
- Rev38 source lock: `source-inputs.sha256` SHA-256 `787ac3cd4348ffaa84c090c2c520533f89df42b7229f2c10e922052446b84f9a`. Its five committed Atopile files pass `shasum -a 256 -c`.
- Base scenario: `isolated-illustrative.case` SHA-256 `7acf2ffde0f4c905b28fc3b08acf4207518a29fe9d48e4ba0adf00889458882f`. Its 80 V / 120 s values are illustrative, not adopted.
- Manifest: `qualification-manifest.txt` SHA-256 `83da2b8ef464d5b2ce416b380f509ef7f0398e2316f246bf862537cfbb208b16`. Ten required roles are explicitly `UNKNOWN`; the article identity is `UNKNOWN`.
- Saved sweep: `qualification-sweep.csv` SHA-256 `9e1dedd26ad14a0f3dc5486bb815c16fd67b784927cdd436c00b1b9c97c3b676`.

Run from the repository root:

```sh
shasum -a 256 -c zapote/discharge/evidence/source-inputs.sha256
rustfmt --check zapote/discharge/evidence/discharge_screen.rs zapote/discharge/evidence/qualification.rs
rustc --edition=2021 --test zapote/discharge/evidence/discharge_screen.rs -o /tmp/zapote-discharge-u3-tests
/tmp/zapote-discharge-u3-tests
rustc --edition=2021 zapote/discharge/evidence/discharge_screen.rs -o /tmp/zapote-discharge-u3-gate
/tmp/zapote-discharge-u3-gate --sweep zapote/discharge/evidence/isolated-illustrative.case zapote/discharge/evidence/qualification-manifest.txt /tmp/discharge-sweep.csv
cmp /tmp/discharge-sweep.csv zapote/discharge/evidence/qualification-sweep.csv
```

The sweep command returns exit 2 for indeterminate hardware status. The saved CSV contains 45 cases plus header: ten faults, including none, crossed with F2 open/closed and mains isolated/attached (40); and five explicit adverse controls. Model verdicts are 9 rejected and 36 indeterminate. Qualification verdicts remain 9 rejected and 36 indeterminate. Mains-attached cases have no isolated-RC decay time. The CSV power column is a resistor-path load **if VB is held at the entered maximum voltage**; F2-open cases do not imply mains can maintain VB. The 450 V fan-off stress remains an external cooling/chassis input, not a temperature pass.

## Fail-closed controls

The focused suite has 26 passing tests, including five new qualification tests. It checks: booleans alone cannot yield a hardware conditional result; source-lock and case digest mismatch; duplicate and omitted evidence roles; a syntactically complete self-authored record bundle cannot promote a hardware verdict; and all 45 sweep rows and adverse rejections. The adverse rows reject a 15.75 V direct feed to the 12 V / 15 V-maximum coil, detached inverter capacitance with no path, an RC deadline while mains can replenish the bus, a restart from equal charged VD/VB, and restart with F2 open plus a sense fault. In a separate scratch-copy negative control, appending one line to `pfc_power.ato` made `--case` exit 1 with `REJECT: Rev38 source hash drift or missing source` before calculation. The live source-lock replay passed unchanged.

The manifest parser checks identity fields and raw-record SHA-256 when actual paths are present. Those checks do **not** prove that the claimed parameter range covers the experiment, that the article was the assembled product, that instruments were calibrated, or that the reviewer was independent. The CLI has no trusted physical-review authority, so even a filled manifest with invented but hash-consistent records is indeterminate. A later independent review must examine the raw data, coverage, installation and adopted requirement before a physical qualification verdict can be issued.

## Remaining gates

Select and independently adopt the service and restart voltage/time criterion; bound maximum VD, VB and directly/detached inverter capacitance; freeze exact resistor/contact/coil and mounted heat path; capture loaded coil pickup, hold, dropout, bounce and DC contact life; measure fan-off sustained heat with mains attached; verify F2, sense-open, service measurement and deliberate rearm behavior; then construct and validate the native standalone circuit before U3 acceptance. The protocol in `../bench-qualification.md` remains unperformed.
