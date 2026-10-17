# Native layout integration review

Scope: `e7302c48fc2a5263bd3e7b0494b3cbe1f926ad7c` through this working tree,
including new Rust modules, native transport, Make integration, tests and evidence.
Intent: make the existing layout work useful on the actual 120 V PCB and audit
which other Rust checks really execute. Board source files are unchanged.

## Coverage

The ce-simplify-code and ce-code-review rubrics were applied sequentially in the
main context under the user's AGENTS tool mapping. This is an implementing-agent
review; there were no independent reviewers or cross-model pass. The full scope
was used: correctness, maintainability, testing, project standards, adversarial,
API-contract, reliability and performance concerns. This receipt does not claim
independent review or qualify the hardware.

- Traced `check` -> `check-layout` -> live KiCad capture -> Rust evaluator ->
  comparison/report, and separately traced existing unit/standalone callers.
- Checked captured external schema, board and extractor hashes, required exact
  endpoint identities, declared layers, native contacts and mutation evidence.
- Examined geometry units, copper holes/union, dielectric series separation,
  nanometre graph keys, via spans and excluded resistance/return effects.
- Exercised missing inputs, bad dimensions/layers/contacts, duplicate UUIDs and
  logical pins, changed profiles, graph disconnection, removed measurements,
  physical track-width edits, object iteration order and invalid CLI options.
- Confirmed original JSON mode remains available with its prior exit semantics;
  native mode's zero exit means measurement success and always reports model gaps.
- Root AGENTS and zapote/AGENTS criteria apply. New engineering logic is Rust;
  Python calls native KiCad and transports facts. No native source board or legacy
  ceiling, firmware manifest, workflow, oracle pin or donor package was changed.

## Fixes made before final validation

1. Request an explicit 1 micrometre pad polygonization error; cached effective
   polygons do not establish the tolerance reported by the transport.
2. Preserve removed metrics as missing instead of zero, and reject comparisons
   across different evaluator/extractor identities.
3. Normalize graph/copper input ordering, require exact profile endpoint nets,
   and reject duplicate physical-pad claims that disagree on a logical pin's net.
4. Use typed route witnesses, a structured measurement record, and separate
   route/copper/assembly/thermal helpers. Reuse existing resistance and plate-C
   kernels and the existing stackup parser; no new Python engineering authority.
5. Retain unsupported copper graphics and absent profile-net populations as gaps;
   zero-overlap witnesses point to real copper rather than a fabricated origin.
6. Remove repeated full-board cloning from the property-test graph generator.

Simplification: one reuse improvement (shared plate-C calculation), three quality
improvements (typed routes, structured metrics, named measurement helpers), one
execution-efficiency improvement (small PBT graph fixtures). No safety guards
were removed. Broad polygon-engine replacement and full conductor meshing were
not attempted under a behavior-preserving simplification pass.

## Validation

- Full Zapote workspace: 387 passed, 0 failed, 1 environment-dependent live test
  ignored by default. PBT count set to 2,048 per property.
- Explicit KiCad CLI tests: 2 passed, including the real saved-board width edit.
- Standalone 120 V source audit: PASS; 53 tests passed. Fresh native parity PASS.
- Fresh five-unit common runner: all five indeterminate, none failed; missing
  model/operating/interface inputs remain visible. This is not a green board suite.
- Rust Clippy completed; no diagnostics in the new native-layout files. Existing
  unrelated workspace warnings remain. Targeted rustfmt and Python Ruff pass.
- `make regen` and `make regen-check`: all derived artifacts consistent.
- Import-boundary gate: 5 contracts kept, 0 broken; final result retained in the evidence logs.

## Residual limits

The native mode computes useful geometric feedback, not every physical input to
all nine original kernels. Thirteen native-17 paths need fuller zone/junction/
pad-barrel reconstruction; physical current, field, thermal and 3D models remain
missing. The 120 V board still lacks its own combined acceptance specification
in the maintained-unit runner. Exact ownership and next integrations are recorded
in `zapote/layout-quality/INTEGRATION-AUDIT.md` and issue #1628.

## Actionable Findings

No unresolved implementation defect found in the delivered native geometric
feedback path. Remaining integration/model work above is explicitly unimplemented;
do not use this review to claim full-board acceptance or all-nine-model integration.

## Verdict

Ready for native geometric feedback with documented coverage limits. Full 120 V
engineering acceptance remains unfinished.
