# Historical shunt transfer review

Scope: read-only review of the new `historical_shunt_input` boundary in
`zapote/packages/zapote-harness/src/shunt_thermal.rs` at the current
`zapote-pfc-loss-correction` worktree. No implementation or build was run.

## What is correct

- The transfer is isolated from the retained solver artifacts. It reads the
  historical `run-15/native.json`, keeps that byte stream unchanged for both
  local and assembly replay, and leaves the original replay checks in place.
- The old board is pinned to the reviewed SHA, and the current board must be
  exactly the historical saved board after one `Value` and one `MPN` property
  replacement (`STW65N65DM2` -> `STW65N65DM2AG`). The normalized native JSON
  comparison changes only `components[id=q_boost].mpn`; geometry, nets,
  traces, vias, stackup, and all other component data must remain equal.
- The mutation matrix rejects board, trace, component, identity, stackup, and
  extra-field changes. The transfer note says it is shunt-only and leaves
  applicability unqualified, so the result does not claim a current MOSFET or
  whole-board thermal solve.
- The bridge path is unaffected. Bridge selection and replay remain keyed to
  `bridge` / `GBJ2510-F`; the boost identity transfer does not alter that
  model.

## Follow-up review

The transition path now recomputes SHA-256 for both embedded boards before
the equality fast path, pins the historical board and extractor identities,
keeps `extractor_sha256` in the normalized comparison, and adds hash-only,
extractor-only, and tampered-retained tests. The bridge path additionally
requires manufacturing hashes to match the old/current native captures and
compares all remaining manufacturing geometry after the reviewed envelope
normalization. Equal-board inputs still use the original strict native and
manufacturing replay. No residual binding gap was found in this final read.
