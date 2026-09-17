# PFC assurance final bounded review

Reviewed the frozen canonical checkout after the author’s final guard updates.
This was read-only; I did not run Cargo because the root run owns the shared
target. No remaining blocker was found in the owned model-assurance,
loss-budget, runner, registration, or fixture files.

The previously identified bypasses are closed:

- measured evidence now fails without a verified importer; independent
  references require a valid pinned SHA;
- NaN/non-finite values are rejected before tolerance comparisons;
- all 54 scenarios bind branch moments, overlap, Eoss exactly once, conduction,
  gate, subtotals, total, metadata grid, model version, quadrature flag, and
  fixed production bus/frequency/Qg/Qgd/plateau/driver/loop/timestep/Eoss
  inputs;
- self-consistent bus, frequency, and Qgd mutations have explicit regression
  tests;
- the nominal selection is explicitly 120 V, 10 V gate bias, 25 C, 0.05 ohm,
  and 10 nC;
- the 400 V / 10 A / 20 ns + 30 ns / 100 uJ anchor is field-pinned and
  byte-hash-pinned to the actual fixture;
- retained manufacturer sources require the expected SHA-256 and `%PDF-`
  header, with the existing exact part gate; physical applicability and
  hardware qualification remain indeterminate where structurally valid.

The review is independent source inspection only; it is not a CE, hardware,
or cross-model qualification receipt. Root’s full-suite results remain the
execution evidence.

## Frozen file hashes

```
6b6248b1e601037d8ef3680ed9c5a25989a521eccb51a4683dda43d9a5a9697e  zapote/packages/zapote-harness/src/model_assurance.rs
048315ddb5695df09895916494478eca62bf71169094121edb940035a4a1014b  zapote/packages/zapote-harness/src/pfc_loss_budget.rs
8b369d732c4d3f64313a88382e8191cab428b39b974dc6a0f3abbaea0b9369f2  zapote/packages/zapote-harness/src/runner.rs
8af69665042977fcd2b7aa4c93c4dc584820758d9b8a6432372eb98ca2b9eb71  zapote/packages/zapote-harness/src/lib.rs
a59dafc68342b497615a6a94eb806e4721b43fb9cb9f8feb62b4b2a90e289a70  zapote/power-entry/loss-budget/options/harness/triangle-anchor.json
c3174383a2f8dee7074a53363dff31fade6994eeda39e009744e292fd8ba3f27  zapote/power-entry/loss-budget/options/harness/TEST-EVIDENCE.md
```
