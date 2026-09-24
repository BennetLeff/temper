# Service interface gate receipt — 2026-09-23

- Source revision: `afb8b9e31cf03ef12b1cb246a89803f333dee6e0`.
- Runtime: local `rustc 1.92.0 --edition=2021` plus macOS `shasum -a 256`.
- Model/provider: none; the verdict is deterministic Rust execution.
- Inputs: `sources.sha256`, `pin-ledger.tsv`, `service-cases.tsv` and the six
  pinned repository files. The source lock rechecks exact bytes and key source
  claims; no Rev38 moving checkout is read.
- Input identities: ledger SHA-256
  `9e7cdca6902c48234aabce2c1118957aa4085044cc337f22c73ca832f0b173ac`;
  cases SHA-256
  `f89f4a56372485ed49e6190682628245cf4522a86c160ce1aa44bc5bf9a24978`;
  gate SHA-256
  `6035bcd8e026a085202e51c1d20027d4d8ba3b2e196f3a88e88273df4200874c`.
- `rustc --test ... && /tmp/zapote-ui-tests`: **6 passed**. The test-first
  baseline failed because the implementation file did not yet exist.
- `rustfmt --check`: passed. `git diff --check`: passed.
- CLI: `SOURCE_LOCK PASS: 6 files`; GPIO 0/16/17/19/20 have competing role
  claims; 11 cases rejected, four indeterminate. The CLI exits **2** with
  `BASELINE BLOCKED` by design. A passing matrix run is not a passing service
  interface.
- No Atopile/netlist fixture: a selected service connector and pin order do
  not exist in the pinned source. No electrical or physical acceptance was
  inferred from the UART0 symbol pins or the unadopted Rev38 pin-fit screen.

The gate is a source and scenario check. Its two positive-looking physical
claims stay indeterminate because they carry no independently reviewed raw
discharge or reset/stop record. A future owner must supply the actual MCU
assembly, SELV service connector/ESD/off-state protection, access rule, and
measured PFC plus inverter stop/rearm behavior before physical qualification.
