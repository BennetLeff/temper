# Physical-model workstream handoff

Completed in this worktree:

- U1: `contract.json` and the Rust `PhysicalModelContract`/`LeadPath` schema
  bind the board SHA, GBU2510A MPN, four pad/trace UUIDs, and every lead,
  barrel, solder, and copper property to units, provenance, and ranges.
- U2: `physical_model::evaluate` solves one package node plus four shared
  paths, injects the 40 W design allowance once, computes conductor Joule heat
  once per path with a lumped series screening resistance, and checks the
  global residual. Invalid or incomplete geometry is rejected. Unknown
  assembly/package paths keep applicability indeterminate; the lumped
  resistance is not a joint electrical acceptance result.
- U3: `bridge_thermal::run_with_physical_model` binds retained assessments to
  the live PFC waveform. Replays recompute diode loss, reject changed
  waveform/branch RMS/curve/contract/board evidence, and add three mandatory
  physical-model rule IDs for PowerEntry runs. Missing contract, assessment,
  or native geometry evidence fails closed.

Verification:

```
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml -p zapote-thermal --locked
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml -p zapote-harness --test bridge_thermal --locked
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo clippy --manifest-path zapote/Cargo.toml -p zapote-thermal -p zapote-harness --all-targets --no-deps --locked -- -D warnings
```

The thermal package suite (26 tests) and physical-model harness test passed;
the full harness compile/test suite passed. Existing broad clippy warnings in
unchanged DRC/ERC crates are outside this workstream.

U4 remains pending coordinator integration: consume the frozen 3 mm
same-package candidate from the connections worktree, generate a
source-bound PFC waveform assessment through the production runner, and run
the baseline/3 mm comparison with solver evidence. The current series path
resistance is a screening approximation; only the joint-terminal FEM can
replace it for electrical/thermal acceptance. No candidate is promoted or
considered fabrication-qualified by this handoff.
