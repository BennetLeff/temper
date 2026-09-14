# Physical-model workstream handoff

Completed in this worktree:

- U1: `contract.json` and the Rust `PhysicalModelContract`/`LeadPath` schema
  bind the board SHA, GBU2510A MPN, four pad/trace UUIDs, and every lead,
  barrel, solder, and copper property to units, provenance, and ranges.
- U2: `physical_model::evaluate` solves one package node plus four shared
  paths, injects the 40 W allowance once, computes conductor Joule heat once
  per path, and checks the global residual. Invalid or incomplete geometry is
  rejected. Unknown assembly/package paths keep applicability indeterminate.
- U3: `bridge_thermal::run_with_physical_model` and optional runner fields bind
  retained assessments to the live PFC waveform. Replays recompute diode loss,
  reject changed waveform/branch RMS/curve/contract/board evidence, and add
  three mandatory physical-model rule IDs when the manifest opts in.

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
the baseline/3 mm comparison with solver evidence. No candidate is promoted
or considered fabrication-qualified by this handoff.
