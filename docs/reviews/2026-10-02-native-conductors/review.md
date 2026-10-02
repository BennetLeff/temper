# Native conductor/contact integration review

Scope: `de2cad955fdaecaaa411414a1dbb717d3c305b31` through the reviewed working
tree. Intent: close actual native graph gaps and make the existing Rust contact
kernel execute on saved 120 V copper, preserving honest incomplete coverage.

## Coverage and limits

Review and simplification were performed sequentially in the implementing
context under the user's AGENTS tool mapping. There was no independent reviewer
or cross-model review. Correctness, adversarial, testing, API, performance and
project-standard concerns were examined against the code and retained evidence.

- Traced the production Make/CLI/extractor/evaluator/report path. Python adds
  only native plating and contact facts; Rust owns graph construction and metrics.
- Checked same-net/same-layer nanometre topology, partial-track resistance,
  mid-track vias, physical pad UUIDs and plated-only cross-layer connectivity.
- Checked multi-island copper and per-shell hole ownership. Empty witnesses are
  retained as incomplete measurements, never declared opens or ampacity passes.
- Required v2 snapshot fields and report schema make the format change explicit.
  Old reports need recapture; public single-drill `entry` delegates to the same
  kernel and its existing tests remain active. No parallel Python implementation.
- Checked negative inputs, ordering, gaps, reversed/oblique tracks, missing
  contact copper, native identity mismatches, transformed numeric overflow and
  tolerance behavior for subnanometre widths.
- Tests use closed-form lengths/R/intervals plus native KiCad connectivity and
  scratch-board edits. The real route oracle covers C16's transitions; barrel
  geometry has analytic tests and native plating facts, not a field-solver oracle.
- Native report replay costs 321.10 ms averaged over 25 release iterations;
  end-to-end live run took 2.100 s. No performance guarantee or new bottleneck claim.
- Root and Zapote AGENTS apply. No production PCB, donor module, firmware
  manifest, workflow or pinned Python oracle changed.

## Fixes and simplification

1. Preserve holes per copper island before unioning sampled intervals.
2. Split resistance proportionally at exact junctions, including via anchors.
3. Reject unrepresentable transformed geometry; require a positive witness before
   declaring a full-width chord. The old absolute tolerance could accept zero for
   a tiny width; the new tolerance scales down with width.
4. Share vertical-link construction between vias and plated pads. Reuse the
   existing entry kernel rather than add a separate native-only calculation.
5. Query native connected pads once per track and reuse the result for endpoint
   and full-contact exports. This replaces two calls and supplies all candidates.
6. Extend the existing ordering test after live captures demonstrated different
   contact enumeration orders. Serialized metrics/routes/contact witnesses agree.

Simplification applied one reuse improvement and one native-query efficiency
improvement; broad graph and polygon rewrites were not needed. No guards removed.

## Verification

396 workspace tests passed with `PROPTEST_CASES=2048`; the environment-dependent
live test was separately run and both live CLI tests passed. The final recaptured
fixture/order test selection passed all 17 tests. Five-unit native validation ran
to completion: five indeterminate, zero failed. Clippy completed with existing
warnings outside the change; formatting, Ruff, import boundaries and regeneration
checks passed. Full receipts are in `zapote/layout-quality/conductor-evidence/`.

## Verdict

No unresolved defect found in the delivered graph/contact integration. This is
useful layout feedback, not completed 120 V acceptance. Twelve paths still lack
full conductor reconstruction; branch-current and physical-model integration
remain explicit follow-ups in issue #1628 and the integration audit.
